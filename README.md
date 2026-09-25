# WiWave · Live Wi-Fi Sensing Observatory

A local sensing workspace with a [RuView](https://github.com/ruvnet/RuView)-derived
3D Observatory, real Wi-Fi measurements, calibrated signal changes, recordings,
replay and optional ESP32 channel-state-information (CSI) experiments.

**Current capability:** a Windows laptop measures its Wi-Fi link's signal strength
in real time. Changes are shown relative to a quiet baseline. These measurements
do not identify humans, count people, locate objects, or measure vital signs.
ESP32 CSI provides richer motion measurements but still requires physical testing
and a validated classifier before making human-presence claims.

## Start with your Windows laptop

Connect to Wi-Fi. Use Python 3.10+ and a Node version supported by the project's
Vite release (Node 24 was used for this build).

```powershell
python -m venv .venv # Skip if already created
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Push-Location frontend
npm ci
npm run build
Pop-Location
.\scripts\start-live.ps1
```

Open **http://127.0.0.1:8000**. Keep the room quiet and the equipment stationary
for the initial 20-second calibration. Confirm the **LIVE WI-FI** badge. Use
**Workspace → Operations** to calibrate or record, and **Live Monitor** for detailed
charts at `/monitor.html`.

Alternatively, set `WIWAVE_SOURCE=native_rssi`, `SIMULATION_MODE=false`, and run
`.\.venv\Scripts\python.exe server.py`. For frontend development, keep the backend
running and run `npm run dev` in `frontend`.

## What is implemented

- RuView Observatory room, orbit camera, visual settings and six style presets.
- All twelve reference scenarios, explicitly labelled synthetic demonstrations.
- Operations, devices, recordings, research links and feature-status workspace.
- Replay with pause, seek and speed controls, preserving original data provenance.
- Optional connection to a separate RuView sensing server for compatible estimates.
- Direct Windows Native Wi-Fi RSSI queries, outside the async request loop.
- Robust baseline calibration, sustained-change detection, and reconnection.
- Explicit hardware, stale, disconnected, calibrating, and simulation states.
- WebSocket updates with bounded client queues and HTTP polling fallback.
- Live charts, activity log, calibration control, recording, and CSV export.
- Optional serial input for Espressif `csi_recv_router` CSV output.
- No automatic simulation fallback or invented targets, ranges, or heartbeats.

The circular field is an activity illustration, not a measured spatial map.
The change score is a statistic, not a confidence percentage. The displayed read
rate measures driver polling; the underlying adapter may refresh RSSI more slowly.

## Research and hardware setup

- [Current implementation and remaining work](docs/PROJECT_STATUS.md)
- [RuView feature comparison and connection protocol](docs/RUVIEW_PARITY.md)
- [Research datasets, model sources and integration sequence](docs/DATASETS_AND_MODELS.md)
- [Research findings, hardware comparison, and validation boundaries](docs/REALTIME_RESEARCH.md)
- [Live setup, ESP32 connection, configuration, and room trials](docs/LIVE_SENSING_GUIDE.md)

CSI mode needs `requirements-csi.txt`, compatible flashed hardware, a matching
serial baud rate, and `WIWAVE_CSI_PORT`. No CSI hardware was attached during this
implementation. Native laptop RSSI is currently supported on Windows; ESP32 serial
input can be used on Windows, Linux, or macOS.

## API

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Process and sensor health, provenance, read rate, data age |
| `GET /api/poll` | Latest live snapshot with source capability flags |
| `WS /ws/radar` | Same snapshot schema, published up to 10 Hz |
| `GET /api/capabilities` | What the selected measurement source supports |
| `POST /api/calibrate` | Restart quiet-room calibration |
| `POST /session/start` | Start recording measurements |
| `POST /session/stop` | Stop recording |
| `GET /sessions` | Most recent recording sessions |
| `GET /session/{id}/export` | CSV export, including existing legacy sessions |
| `GET /session/{id}/frames?limit=10000` | Bounded recorded snapshots for replay |

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
Push-Location frontend
npm test
npm run lint
npm run build
Pop-Location
```

Tests use deterministic samples and an explicitly simulated local test server.
They verify software behavior, not human-detection accuracy. Real sensing must
also be evaluated with labelled room trials.

Existing `motion_detector.py`, `multi_person/`, and 3D components remain as
historical research code. They do not drive the v5 live monitor. Existing database
records are retained; new measurements use an additional `sensing_telemetry` table.

Cloud hosts cannot measure your laptop's Wi-Fi. `render.yaml` runs a labelled demo.
See the live guide for deployment and persistence constraints.

The Observatory includes MIT-licensed RuView code with its
[license and provenance](frontend/observatory/PROVENANCE.md). This release does
not claim complete RuView platform parity or validated real-time human/object
detection. Refer to the status document for the remaining hardware and model work.
