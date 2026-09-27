# Sets up and flashes an ESP32 CSI receiver for WiWave.
# Usage:
#   .\scripts\setup-esp32.ps1                        # detect port, install esptool, show next steps
#   .\scripts\setup-esp32.ps1 -Port COM3 -BinDir C:\path\to\bin   # flash prebuilt binaries
param(
    [string]$Port = '',
    [string]$BinDir = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements first. See README.md.' }

# esptool lives in the optional CSI requirements.
& $python -m pip show esptool > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing esptool (ESP32 flashing tool)...'
    & $python -m pip install -r requirements-csi.txt
}

if (-not $Port) {
    Write-Host 'Looking for a likely ESP32 serial port...'
    $ports = [System.IO.Ports.SerialPort]::GetPortNames()
    if (-not $ports) { throw 'No serial ports found. Plug the board in with a DATA USB cable, then retry.' }
    Write-Host "  Available ports: $($ports -join ', ')"
    $Port = if ($ports -contains 'COM3') { 'COM3' } else { $ports[0] }
    Write-Host "  Using $Port (override with -Port)."
}

$chipInfo = & $python -m esptool --port $Port chip_id 2>&1
Write-Host $chipInfo

if (-not $BinDir) {
    Write-Host @'

Board responded. To flash WiWave-compatible CSI firmware you need the
csi_recv_router binaries from Espressif's esp-csi project:
  https://github.com/espressif/esp-csi/tree/master/examples/get-started/csi_recv_router

Either build them with ESP-IDF (idf.py build) or pass prebuilt binaries:
  .\scripts\setup-esp32.ps1 -Port $Port -BinDir <folder with .bin files>

Expected files in the folder: bootloader.bin, partition-table.bin, csi_recv_router.bin
'@
    exit 0
}

$bootloader = Join-Path $BinDir 'bootloader.bin'
$partition = Join-Path $BinDir 'partition-table.bin'
$app = Get-ChildItem -Path $BinDir -Filter '*.bin' |
    Where-Object { $_.Name -notmatch 'bootloader|partition' } |
    Select-Object -First 1
foreach ($file in @($bootloader, $partition, $app.FullName)) {
    if (-not ($file -and (Test-Path -LiteralPath $file))) { throw "Missing required binary: $file" }
}
Write-Host "Flashing bootloader, partition table and $($app.Name) to $Port ..."
& $python -m esptool --chip esp32 --port $Port --baud 460800 write_flash `
    0x1000 $bootloader 0x8000 $partition 0x10000 $app.FullName
Write-Host 'Done. Start WiWave with:'
Write-Host "`$env:WIWAVE_SOURCE = 'esp32_csi'; `$env:WIWAVE_CSI_PORT = '$Port'"
Write-Host '  .\.venv\Scripts\python.exe -B server.py'
