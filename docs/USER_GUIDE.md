# WiWave user guide

WiWave v6 is a local Wi-Fi sensing workspace. This guide covers everyday use;
[PROJECT_STATUS.md](PROJECT_STATUS.md) tracks what is implemented and verified.

## Everyday workflow (Windows laptop mode)

1. **Start**: `.\scripts\start-live.ps1`, then open http://127.0.0.1:8000.
2. **Calibrate**: leave the room quiet for ~20 seconds, or press
   *Calibrate quiet room* in the Live Monitor (or Workspace → Operations).
3. **Watch**: the Live Monitor (`/monitor.html`) shows live RSSI, the change
   score, measured neighbor links, spectral statistics and the event journal.
4. **Record**: Workspace → Operations → *Start recording*; export or replay
   recordings from Workspace → Recordings.
5. **Events**: every sustained signal change is journaled with before/after
   context — click an entry in *Event journal* for its sparklines.
6. **Alerts** (optional): press *Alert me on changes* in the Live Monitor to
   get a local Windows notification when a sustained change starts.

## Trying it without hardware

- `SIMULATION_MODE=true` — synthetic RSSI demo.
- `WIWAVE_SOURCE=csi_simulation` — synthetic multi-subcarrier CSI stream that
  drives the waterfall and the trial tooling. Always labeled as synthetic.

## Adding an ESP32 CSI receiver

Follow [HARDWARE_GUIDE.md](HARDWARE_GUIDE.md): buy an ESP32-DevKitC (~$5–10),
flash Espressif's `csi_recv_router` example, set `WIWAVE_SOURCE=esp32_csi` and
`WIWAVE_CSI_PORT`, and restart. The CSI waterfall, labelled trials and trial
analysis activate automatically once live frames arrive.

## Collecting labelled CSI trials

Workspace → CSI data: name the trial, pick the room condition
(empty room / person still / person moving / fan / door change / pet), start,
create the condition, stop. Then *Analyze* for per-label statistics, or export
JSONL for offline research. Storage is local and bounded (15,000 frames).

## What the readings mean — and don't

- **Change score** is a baseline-deviation statistic, not a probability that
  anyone is present.
- **Neighbor links** refresh on the driver's scan cadence; treat them as slow
  environment channels.
- **Spectral bands** describe the signal only; band energy is not breathing or
  footsteps.
- WiWave never identifies, counts, or locates people. See
  [REALTIME_RESEARCH.md](REALTIME_RESEARCH.md) for why.
