# WiWave implementation status

Updated 2026-09-25.

## Delivered software

- RuView-derived Observatory as the default page, with licensed local rendering assets.
- Twelve explicitly synthetic scenarios, six presets, camera and rendering controls.
- Separate detailed live monitor, native Windows WLAN capture and calibrated changes.
- Source-aware WebSocket connection with stale-data expiry and reconnection.
- Operations workspace, device view, recording, CSV export and timed replay.
- Compatible RuView sensing-output adapter; unknown outputs remain unavailable.
- ESP32 CSV source, parsers, API tests, UI logic tests and research documentation.
- Opt-in labelled CSI pilot collection, with bounded local retention, JSONL export and deletion.

The Windows Intel Wireless-AC 8265 hardware stream was verified after deployment.
A 30-second capture produced 279 distinct driver reads, approximately
9.29 reads/s, with no simulation and a maximum observed sample age of 109 ms.
The Observatory, Live Monitor, license file and replay API are served successfully
from the restarted local server. This establishes connectivity and software timing;
it does not establish human-detection accuracy or independent radio frame rate.

## Remaining work

1. **Physical CSI capture:** connect and flash compatible ESP32 hardware or another
   CSI-capable platform; use **Workspace → CSI data** to collect pilots and validate
   the capture pipeline against real packets.
2. **Room trials:** collect labelled quiet/motion/interference cases and measure
   false alarms and missed events. No person was observed or inferred during the
   unattended RSSI verification.
3. **Models:** select a compatible model, match preprocessing, train/adapt where
   needed and validate on held-out room data. No weights or datasets are installed.
4. **Advanced detection:** human count, pose, falls, vitals and object identification
   are not locally validated features. Some can be displayed from a separate CSI
   engine; displaying an estimate is not validation.
5. **Full upstream parity:** firmware provisioning, training, multi-node management,
   edge modules and RuView's other dashboards are not integrated. See the detailed
   [feature comparison](RUVIEW_PARITY.md).
6. **Visual/GPU testing:** no browser was exposed by this session's browser tool.
   DOM interaction, scene helpers and production builds are tested; desktop/mobile
   screenshots, layout inspection and real WebGL rendering remain to be checked.

## Validation commands

The previous published baseline passed 30 backend tests and 7 frontend tests,
lint, and a production build. This CSI capture update imports as a server module
and the Observatory production build succeeds. Real collection still needs CSI
hardware. The installed frontend dependency audit reported zero vulnerabilities.

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests -q
Push-Location frontend
npm ci
npm test
npm run lint
npm run build
Pop-Location
.\.venv\Scripts\python.exe -B scripts\verify-stream.py --seconds 30
```

The automated API server explicitly uses simulation for reproducibility. The last
command reads the running server and reports its real source; it fails if no healthy
stream is observed. Demos and unit tests do not measure sensing accuracy.

Recordings stay in the local SQLite database and are excluded from Git. The public
repository contains source, tests, documentation and the dependency lockfile.
