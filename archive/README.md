# Archive: WiWave v3/v4 research prototypes

This directory preserves the early WiWave engines exactly as they were, for
reference and because their 294 unit tests still pass. **None of it runs in the
live v6 system** — the live pipeline lives in `sensing/`, `server.py`, and
`frontend/src`.

| Path | What it was |
| --- | --- |
| `motion_detector.py` | v4 "Intelligence Engine": FFT band analysis, gesture detector, RTT-jitter distance estimates. It inferred human activity, heartbeats, and range from ordinary ping timing — an invalid measurement model, which is why it was retired. See `docs/REALTIME_RESEARCH.md`. |
| `wifi_reader.py` | Multi-OS netsh/ping/iwconfig readers with multi-AP snapshots (netsh+ping era hardware layer). The live source is `sensing/windows.py` (native WLAN API). |
| `multi_person/` | A complete multi-person detection pipeline (signal separation, position zones, activity recognition, person tracking) with 294 passing tests — all verified only against synthetic signals. Never validated against real radio data; never wired into the live backend. |
| `main.py`, `demo_real_wifi.py`, `demo_simple.py`, `data_logger.py` | v3/v4 command-line demos. |
| `MULTI_PERSON_IMPLEMENTATION_STATUS.md` | The original (over-optimistic) status document. |
| `frontend-components/` | Radar panel React components from the pre-Observatory dashboard; no longer imported. |

Run their tests (from the repository root):

```powershell
.\.venv\Scripts\python.exe -B -m pytest archive/legacy-v4/tests archive/legacy-v4/multi_person/tests -q
```

These modules are kept frozen: they will not receive updates. Do not connect
them to the live server without the validation work described in
`docs/REALTIME_RESEARCH.md`.
