# Live setup and measurement trials

## Current laptop: real measurements

Use Windows with Wi-Fi connected. From the project directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Push-Location frontend
npm ci
npm run build
Pop-Location
.\scripts\start-live.ps1
```

Open **http://127.0.0.1:8000**. Keep the laptop and router fixed and the room quiet
for the initial 20 seconds. The badge must read **LIVE HARDWARE**. The sidebar
should identify your adapter. `http://127.0.0.1:8000/api/health` should report
`native_rssi` and `is_simulation: false`.

RSSI mode detects changes in the link, not people. A person walking through the
link may change it, but so can interference, a door, a fan, or moving the laptop.
A stationary person may create no detectable change. The dashboard intentionally
does not draw human targets or display a person count or distance.

If Windows returns error 5, check **Settings → Privacy & security → Location**
and access for desktop applications. Connect to Wi-Fi, not only Ethernet.
Software startup errors remain errors; they never silently select a demo.

## Optional ESP32 CSI source

Use a CSI-capable ESP32-family board with a USB data cable, a supported firmware
target, and a suitable Wi-Fi link. Follow Espressif's current
[csi_recv_router example](https://github.com/espressif/esp-csi/tree/master/examples/get-started/csi_recv_router)
and ESP-IDF instructions to configure the router, build, and flash the board.
The project does not flash hardware automatically.

This adapter expects the example's **CSV output**, beginning with its `type,...`
header and followed by `CSI_DATA,...` rows. It is not an adapter for the separate
esp-radar / esp_wifi_sensing event format. The parser uses header names so the
older ESP32 and newer C5/C6 layouts can differ. See the
[upstream emitting code](https://github.com/espressif/esp-csi/blob/master/examples/get-started/csi_recv_router/main/app_main.c).

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-csi.txt
$env:WIWAVE_SOURCE = 'esp32_csi'
$env:WIWAVE_CSI_PORT = 'COM3' # Replace with the board's actual serial port
$env:WIWAVE_CSI_BAUD = '115200' # Must match the flashed firmware
$env:SIMULATION_MODE = 'false'
.\.venv\Scripts\python.exe server.py
```

On Windows, use `scripts/start-csi.ps1` after installing the optional reader and
flashing compatible firmware. The script detects COM ports, sets CSI mode explicitly
and stops with a clear error if the requested port is missing.

Close any other serial monitor before connecting. If the header was printed
before WiWave opened the port, reset the board so it emits the header again.
Both board and host must use the same baud rate. Large CSI frames at high packet
rates require a higher firmware UART baud rate; increasing only the host rate
does not solve that problem. Observe the reported frame rate and invalid-frame
counter instead of assuming a requested rate was achieved.

The motion score uses normalized subcarrier amplitudes, not a trained presence
classifier. Its state is **Possible motion**, and human identification remains
unavailable. Phase processing, antenna calibration, validated classification,
and spatial localization are future work.

### Collect a labelled CSI pilot trial

After CSI hardware is connected and the CSI stream reports fresh frames, open
**Workspace → CSI data**. Choose a non-identifying trial name, select the room
condition you are observing and a 30–180 second limit, then start capture. Change
the label and select **Apply label to new frames** before each room condition
change. Stop between conditions if you are unsure about the exact transition time.
Record one condition at a time where possible.

Collection is opt-in. The local database stores at most 10 amplitude vectors per
second, 512 amplitude bins per vector, 180 seconds per trial and 15,000 samples
across all retained trials. Captures preserve the first 512 subcarriers in their
original order and mark truncated frames. RSSI, channel, timestamps, sample
sequence and manual room labels accompany the vectors. The trial does not store
BSSID, Wi-Fi network name or participant identity. It stores magnitude `hypot(I,Q)`,
not signed I/Q samples or phase. A trusted RuView runtime or trained CSI model is
not part of this release.

Download trials as JSON Lines. Each file begins with trial metadata, followed by
one labelled CSI frame per line. Download and move a copy to your research data
folder before deleting a trial; deletion permanently removes local sample frames.
Include empty-room baselines and repeat conditions across sessions before training.

## A useful first experiment

1. Put the receiver and router in fixed positions. Let WiWave calibrate in a
   quiet room; record two minutes and export the CSV as the baseline trial.
2. Keep the layout identical, start another recording, and walk across the
   transmitter–receiver region at known times. Note those times separately.
3. Repeat with an empty room while running a fan and ordinary network traffic.
   Compare the score and state transitions with the walking trial.
4. Test a stationary person, movement outside the link, and a different room.
5. Disconnect and reconnect Wi-Fi. The dashboard should report the outage and
   recalibrate after recovery, with no cached positive detection.

Do not interpret a stable signal as proof of an empty room. Report both missed
trials and false alarms. There is no established range or accuracy yet.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `WIWAVE_SOURCE` | `native_rssi` | `native_rssi`, `esp32_csi`, or `simulation` |
| `SIMULATION_MODE` | false | Explicit true overrides the source with a demo |
| `SAMPLE_RATE_HZ` | 10 | Native driver read ceiling, 1–100 Hz |
| `WIWAVE_CALIBRATION_SECONDS` | 20 | Quiet baseline duration, 5–120 seconds |
| `WIWAVE_CSI_PORT` | unset | Required serial port for CSI |
| `WIWAVE_CSI_BAUD` | 115200 | Serial baud matching the firmware |
| `WIWAVE_HOST` | 127.0.0.1 | Local bind address |
| `PORT` | 8000 | Server port |
| `WIWAVE_DB_PATH` | project/wiwave_sessions.db | SQLite session database |
| `WIWAVE_ALLOWED_ORIGINS` | unset | Additional comma-separated frontend origins |

`AUTO_SIM_FALLBACK` and `MULTI_PERSON_EVERY_N` no longer control the v5 pipeline.
The historical Python DSP modules are not invoked by the live server.

Demo-only mode is explicit:

```powershell
$env:WIWAVE_SOURCE = 'simulation'
.\.venv\Scripts\python.exe server.py
```

For frontend development, run the backend at port 8000, then `npm run dev` inside
`frontend`. Vite proxies the API, sessions, and WebSocket routes. Optional
`VITE_API_URL` and `VITE_WS_URL` configure another backend; allow that frontend's
origin on the backend as well.

Existing sessions and the old telemetry table remain intact. New recordings use
the `sensing_telemetry` table; exports preserve the legacy columns for old sessions.
The current recorder samples snapshots at up to 5 Hz. It does not retain raw CSI
arrays, so raw CSI model-training datasets must be collected separately.

The service is intended for local use. Cloud hosts have no access to your laptop's
radio; the Render configuration is an explicitly labelled demo and requires a
persistent database volume if recordings must survive a restart. Network-wide or
internet deployment needs authentication, TLS, and an explicit data-retention plan.
