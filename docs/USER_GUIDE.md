# WiWave Multi-Person Detection — User Guide

## What it does

WiWave uses the Wi-Fi signals already present in your home or office to detect
and track up to **5 people simultaneously** — no cameras, no wearables, no
specialist hardware required.

The multi-person detection layer sits on top of the existing single-person
motion detector and adds:

| Feature | Detail |
|---|---|
| Person count | 1 – 5 people detected at once |
| Per-person activity | walking · breathing · still · gesture |
| Zone positioning | left · center · right (configurable) |
| Zone congestion | alert when ≥ 2 people share a zone |
| Real-time updates | WebSocket push at 10 Hz |
| Backward compatibility | single-person clients unaffected |

---

## Quick start

### 1 — Start the backend

```bash
# From the project root
python server.py
```

The server starts on `http://localhost:8000` by default.  
Set `PORT=8080` (or any port) via environment variable if needed.

### 2 — Open the dashboard

```bash
cd frontend
npm install        # first time only
npm run dev        # development server on http://localhost:5173
```

Or serve the pre-built bundle:

```bash
cd frontend && npm run build
# then open http://localhost:8000 (served by FastAPI)
```

### 3 — Watch the radar

- The 3-D radar scene shows one coloured silhouette per detected person.
- The **Multi-Person Panel** (right sidebar) appears automatically when
  `person_count > 1` and shows per-person cards.
- Zone congestion badges appear at the top of the panel when a zone is crowded.

---

## Configuration

All configuration is done through environment variables or by editing
`server.py` directly.

| Variable | Default | Description |
|---|---|---|
| `SIMULATION_MODE` | `false` | Force simulation (no real Wi-Fi hardware) |
| `PORT` | `8000` | HTTP / WebSocket port |
| `ENVIRONMENT` | `dev` | Set to `prod` to disable hot-reload |

### Multi-person detector options

Pass keyword arguments when constructing `MultiPersonDetector` in `server.py`:

```python
multi_detector = MultiPersonDetector(
    max_capacity=5,          # max people to track (1–5)
    mode="multi_person",     # or "single_person"
    target_latency_ms=100.0, # latency budget for warnings
)
```

### Zone mapping

POST to `/zones` to map room names to AP BSSIDs:

```bash
curl -X POST http://localhost:8000/zones \
  -H "Content-Type: application/json" \
  -d '{"mappings": {"Living Room": "AA:BB:CC:DD:EE:FF", "Bedroom": "11:22:33:44:55:66"}}'
```

---

## Understanding the dashboard

### Radar scene

- Each coloured sphere / silhouette represents one detected person.
- Colour is consistent per person ID for the duration of the session.
- Position on the radar corresponds to the estimated zone.

### Multi-Person Panel

Appears on the right when `person_count > 1`.

```
┌─────────────────────────────┐
│ 👥 MULTI-PERSON DETECTION 2 │
│ ⚠ Center congested          │
├─────────────────────────────┤
│ P1  🚶 walking              │
│     📍 center   ⚡ 87%      │
│     ████████░░░░            │
├─────────────────────────────┤
│ P2  🫁 breathing            │
│     📍 left     ⚡ 72%      │
│     ███████░░░░░            │
└─────────────────────────────┘
```

- **P1 / P2** — person ID (1–5), colour-coded
- **Activity icon** — 🚶 walking · 🫁 breathing · 🧍 still · 👋 gesture
- **Zone** — left / center / right
- **Confidence bar** — signal quality indicator (0–100 %)

---

## REST API

### GET /api/multi-person/stats

Returns live detection statistics.

```json
{
  "frame_id": 1042,
  "is_calibrated": true,
  "mode": "multi_person",
  "max_capacity": 5,
  "person_count": 2,
  "zone_person_counts": {"center": 2},
  "performance": {
    "frame_count": 100,
    "avg_ms": 8.3,
    "min_ms": 4.1,
    "max_ms": 22.7,
    "p95_ms": 15.2,
    "p99_ms": 19.8,
    "latency_violations": 0,
    "stage_avg": {
      "calibration_ms": 0.0,
      "preprocessing_ms": 1.2,
      "separation_ms": 2.8,
      "feature_extraction_ms": 2.1,
      "tracking_ms": 1.9,
      "zone_update_ms": 0.3
    }
  }
}
```

### GET /api/poll

Stateless polling endpoint (for serverless / Vercel deployments).  
Returns the same payload as the WebSocket `radar_update` message.

---

## WebSocket messages

Connect to `ws://localhost:8000/ws/radar`.

### radar_update (every frame)

```json
{
  "type": "radar_update",
  "timestamp": "2025-01-15T12:00:00.000Z",
  "signal": 75.2,
  "rtt": 31.4,
  "status": "HUMAN DETECTED: WALKING (1.5Hz) (87%)",
  "person_count": 2,
  "persons": [
    {
      "person_id": 1,
      "position_zone": "center",
      "activity": "walking",
      "confidence": 87.0,
      "signal_strength": -65.0
    },
    {
      "person_id": 2,
      "position_zone": "left",
      "activity": "breathing",
      "confidence": 72.0,
      "signal_strength": -72.0
    }
  ],
  "zone_congestion": {
    "left": false,
    "center": false,
    "right": false
  },
  "multi_person_mode": "multi_person"
}
```

### multi_person_update (only when person_count > 1)

Same structure as above but `type` is `"multi_person_update"`.

### fall_alert

```json
{
  "type": "fall_alert",
  "confidence": 0.91,
  "timestamp": "2025-01-15T12:00:05.000Z"
}
```

### gesture

```json
{
  "type": "gesture",
  "gesture": "wave",
  "confidence": 0.85
}
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `person_count` always 0 | No Wi-Fi signal / simulation mode | Check hardware or set `SIMULATION_MODE=true` |
| Multi-Person Panel never appears | `person_count` ≤ 1 | Panel only shows for 2+ people |
| High latency warnings in logs | CPU overloaded | Reduce `max_capacity` or upgrade hardware |
| Persons flickering in/out | Weak or unstable signal | Move closer to AP or add a second AP |
| Zone always "unknown" | No zone mappings configured | POST to `/zones` with your BSSID map |

---

## Hardware recommendations

| Setup | APs | Expected accuracy |
|---|---|---|
| Minimum | 1 AP | Zone-level (left/center/right) |
| Recommended | 2–3 APs | Sub-zone, better separation |
| Optimal | 3+ APs in different rooms | Room-level positioning |

Any 802.11n (Wi-Fi 4) or later access point works.  
Mesh systems (Eero, Google Nest, TP-Link Deco) work well due to multiple nodes.

---

*WiWave v4 · Multi-Person Detection · User Guide v1.0*
