# WiWave hardware guide: adding an ESP32 CSI receiver

WiWave's laptop mode reads RSSI, which is one number per link. Channel State
Information (CSI) is far richer: amplitude (and phase) across dozens of
subcarriers, per packet. An ESP32 board acting as a CSI receiver unlocks the
CSI waterfall, labelled trials, and the trial analysis tools already built into
WiWave. This guide covers buying, flashing, and connecting — no experience with
embedded hardware required.

> Honesty note, in WiWave's tradition: CSI makes *motion research* possible.
> It does not turn WiWave into a people detector. Treat every output as an
> experiment to be validated in your own room.

## 1. What to buy

| Item | Recommendation | Typical price |
| --- | --- | --- |
| CSI receiver board | **ESP32-DevKitC** (original ESP32, WROOM-32 module) — best-documented CSI support | ~$5–10 |
| USB cable | Micro-USB **data** cable (many cheap cables are charge-only) | ~$2 |
| Optional second board | A second ESP32 can act as a dedicated traffic transmitter for stable CSI packets | ~$6 |

Any board with the **original ESP32 chip** (ESP32-D0WD / WROOM-32 / WROVER)
works with Espressif's `esp-csi` examples. Newer C-series boards (C3/C5/C6)
have CSI support of varying maturity; if you buy one, verify its example
support in the esp-csi repository first.

Where to buy: any major electronics retailer (Espressif keeps an official
[buying options page](https://www.espressif.com/en/buy)); search for
"ESP32-DevKitC WROOM-32".

## 2. Install the USB driver

Most DevKitC boards use a Silicon Labs CP210x USB-to-serial chip.

1. Download the **CP210x VCP driver** from Silicon Labs' site and install it.
2. Plug the board in with a data USB cable.
3. Open Device Manager → **Ports (COM & LPT)** and note the new port, e.g. `COM3`.
   If nothing appears, try another cable first — charge-only cables are the
   single most common cause of "board not found".

## 3. Flash the CSI firmware

WiWave parses the CSV output of Espressif's
[`csi_recv_router`](https://github.com/espressif/esp-csi/tree/master/examples/get-started/csi_recv_router)
example. Two paths:

### Path A — build it yourself (recommended, ~30 minutes)

1. Install **ESP-IDF** (Espressif's official framework) via their Windows
   installer: <https://dl.espressif.com/dl/esp-idf/>. Version 5.x is current —
   check the esp-csi repository README for the version it supports.
2. Clone and build the example:

   ```powershell
   git clone --recursive https://github.com/espressif/esp-csi.git
   cd esp-csi/examples/get-started/csi_recv_router
   # open an ESP-IDF PowerShell, then:
   idf.py set-target esp32
   idf.py build
   idf.py -p COM3 flash monitor
   ```

3. You should see scrolling CSV lines starting with `CSI_DATA,...`. Press
   `Ctrl+]` to exit the monitor.

### Path B — I already have a `.bin` file

`scripts/setup-esp32.ps1` flashes any provided `csi_recv_router` binaries
(`bootloader.bin`, `partition-table.bin`, `csi_recv_router.bin`) with the
correct offsets, after checking that `esptool` is available:

```powershell
.\scripts\setup-esp32.ps1 -Port COM3 -BinDir C:\path\to\binaries
```

First run installs `esptool` into WiWave's virtual environment.

## 4. Connect the board to WiWave

1. The board needs Wi-Fi traffic to observe. Connect it to your router by
   editing the SSID/password in the example's menuconfig, or follow the
   esp-csi `csi_recv_router` README for the router-based setup where the
   board listens to packets on your network.
2. Start WiWave with the CSI source:

   ```powershell
   $env:WIWAVE_SOURCE = 'esp32_csi'
   $env:WIWAVE_CSI_PORT = 'COM3'
   .\.venv\Scripts\python.exe -B server.py
   ```

   or set those variables and use `scripts/start-live.ps1`.

3. Open **http://127.0.0.1:8000** — the sidebar should show **ESP32 · CSI**
   and the **CSI SPECTRUM** waterfall panel appears on the Live Monitor.

## 5. Collect labelled trials

With the CSI stream connected, open **Workspace → CSI data**:

1. Name the trial, choose the room label (`empty_room`, `person_still`,
   `person_moving`, `fan_interference`, `door_change`, `pet_or_other_motion`).
2. Start the trial, create the room condition, and let it run (up to 3 minutes).
   Change labels mid-trial with **Apply label to new frames**.
3. Stop, then **Analyze** to see per-label statistics, or **Download JSONL**
   to export raw frames.

Storage is bounded: 10 frames/s, 512 amplitude bins/frame, 15,000 frames
total, local SQLite only. Nothing leaves your machine until you export.

## 6. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| No `COM3`-style port appears | Charge-only USB cable; missing CP210x driver |
| `Waiting for CSI CSV header` | Reset the board after connecting; firmware must print its CSV header first |
| `CSI row does not match firmware header` | Firmware version emits a different CSV layout — rebuild from current esp-csi |
| Frames stall after a while | Serial buffer overflow; lower the traffic rate or baud, check `dropped` counters in the UI |
| Waterfall looks like flat noise | Normalize gain: the parser scales each frame; check that packets actually flow (read rate > 0) |
| Trial start rejected | WiWave must show `LIVE CSI` with fresh frames before trials can start |

## 7. Doing research properly

See [DATASETS_AND_MODELS.md](DATASETS_AND_MODELS.md) for the full sequence:
collect an empty-room baseline, record failures as well as successes, split
trials by session/day (never by adjacent frames), and validate on held-out
rooms before believing any detection claim.
