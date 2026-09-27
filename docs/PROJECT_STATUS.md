# WiWave implementation status

Updated 2026-09-27 (v6.0.0).

## Delivered software

- RuView-derived Observatory as the default page, with licensed local rendering assets.
- Twelve explicitly synthetic scenarios, six presets, camera and rendering controls.
- Separate detailed live monitor, native Windows WLAN capture and calibrated changes.
- **v6 — Multi-link monitoring:** neighbor access points from the driver's cached
  network list (background netsh read, ~30 s cadence by default, configurable with
  `WIWAVE_LINK_POLL_SECONDS`) act as extra, slow environment channels. The detector
  fuses primary and neighbor channels; a single noisy neighbor cannot trigger alone.
  Verified live on the Intel AC 8265 with multiple visible neighbors.
- **v6 — Spectral statistics:** rolling 30 s Welch analysis of the primary signal on a
  uniform grid, reported as descriptive band shares (0.1–0.5 / 0.5–2 / 2–4 Hz),
  dominant frequency and spectral entropy. Bands are named by frequency range, not
  by claimed cause.
- **v6 — Event journal:** sustained signal changes are recorded with bounded
  pre/post frame context (up to 300 frames each side), stored in local SQLite and
  reviewable in the Live Monitor with sparklines. Interrupted events are finalized
  with a stop reason.
- **v6 — Optional local alerts:** opt-in Windows toast notification when a sustained
  change starts (`POST /api/alerts`, or the bell button in the monitor).
- **v6 — CSI waterfall:** Live Monitor renders a rolling subcarrier-amplitude heatmap
  whenever a CSI stream is present, including the clearly-labelled `csi_simulation`
  demo source for development without hardware.
- **v6 — Trial analysis:** `GET /api/csi/trials/{id}/analysis` computes per-label
  frame counts, mean frame-to-frame activity, mean subcarrier spectra and a per-
  subcarrier one-way F-statistic across labels; rendered in the workspace.
- Source-aware WebSocket connection with stale-data expiry and reconnection.
- Operations workspace, device view, recording, CSV export and timed replay.
- Compatible RuView sensing-output adapter; unknown outputs remain unavailable.
- ESP32 CSV source, parsers, API tests, UI logic tests and research documentation.
- Opt-in labelled CSI pilot collection, with bounded local retention, JSONL export
  and deletion, plus `scripts/setup-esp32.ps1` and a full hardware guide
  (`docs/HARDWARE_GUIDE.md`).
- Historical v3/v4 prototypes (multi-person pipeline, motion detector, netsh
  hardware layer) moved to `archive/legacy-v4/` with an honest README; they are
  not part of the live system.

## Hardware verification

The Windows Intel Wireless-AC 8265 stream was re-verified during the v6 build
(2026-09-27): live reads at ~9.3–9.7 Hz through the native WLAN API, neighbor-link
telemetry populated from the driver's scan cache, a real sustained signal change
captured by the event journal end-to-end, and the CSI waterfall validated against
the labelled `csi_simulation` source. This establishes connectivity and software
timing; it does not establish human-detection accuracy or independent radio frame
rate. The ESP32 CSI path still awaits physical hardware.

## Remaining work

1. **Physical CSI capture:** connect and flash compatible ESP32 hardware;
   use **Workspace → CSI data** plus `scripts/setup-esp32.ps1` and
   [the hardware guide](HARDWARE_GUIDE.md).
2. **Room trials:** collect labelled quiet/motion/interference cases and measure
   false alarms and missed events.
3. **Models:** train/adapt a task-specific model on held-out labelled sessions
   before treating any output as a people-detection result.
4. **Advanced detection:** human count, pose, falls, vitals and object
   identification remain unvalidated research targets.
5. **Platform breadth:** Linux/macOS native sources are not implemented; the live
   source is Windows-only.
6. **Visual/GPU testing:** the Observatory was screenshot-verified in a real
   browser during the v6 build (scene, demo scenarios, monitor pages); automated
   visual regression tests remain to be added.

## Validation commands

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

The v6 baseline: 47 backend tests and 7 frontend tests pass, lint and the
production build succeed. The automated API server explicitly uses simulation
for reproducibility; the last command reads the running server and reports its
real source. Demos and unit tests do not measure sensing accuracy.

Recordings, events and CSI trials stay in the local SQLite database and are
excluded from Git. The public repository contains source, tests, documentation
and the dependency lockfile.
