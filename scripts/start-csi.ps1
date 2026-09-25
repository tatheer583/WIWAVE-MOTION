param(
    [ValidatePattern('^COM[0-9]+$')]
    [string]$Port,
    [int]$Baud = 115200
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install requirements.txt first. See README.md.'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend/dist/index.html'))) {
    throw 'Build the dashboard first: cd frontend; npm ci; npm run build.'
}
& $pythonPath -c 'import serial'
if ($LASTEXITCODE -ne 0) {
    throw 'Install the optional CSI reader first: .\.venv\Scripts\python.exe -m pip install -r requirements-csi.txt'
}
$ports = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
if (-not $Port) {
    if ($ports.Count -eq 1) {
        $Port = $ports[0]
    }
    elseif ($ports.Count -gt 1) {
        Write-Host ('Available serial ports: ' + ($ports -join ', '))
        $Port = Read-Host 'Enter the CSI receiver COM port (for example COM3)'
    }
    else {
        throw 'No serial ports are connected. Connect a programmed CSI receiver and open Device Manager > Ports (COM & LPT).'
    }
}
if ($ports -notcontains $Port) {
    throw "Port $Port is not present. Available ports: $($ports -join ', ')"
}
if ($Baud -lt 9600 -or $Baud -gt 2000000) {
    throw 'Baud must be between 9600 and 2000000 and match the firmware.'
}

$env:WIWAVE_SOURCE = 'esp32_csi'
$env:SIMULATION_MODE = 'false'
$env:WIWAVE_CSI_PORT = $Port
$env:WIWAVE_CSI_BAUD = [string]$Baud
$env:WIWAVE_HOST = '127.0.0.1'
Write-Host "WiWave CSI receiver: $Port at $Baud baud. Open http://127.0.0.1:8000 and choose Workspace > CSI data."
Write-Host 'CSI collection remains off until you explicitly start a labelled trial.'
& $pythonPath -B (Join-Path $projectRoot 'server.py')
exit $LASTEXITCODE
