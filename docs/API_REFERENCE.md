# WiWave API Reference

## Base URL

```
http://localhost:8000        (development)
https://your-domain.com      (production)
```

---

## REST Endpoints

### GET /

Returns the React SPA (`index.html`) when the frontend is built.  
Returns `{"message": "WiWave API is running..."}` otherwise.

---

### GET /api/poll

Stateless polling fallback for environments that cannot use WebSockets
(Vercel, Netlify, etc.).

**Response** — same schema as the `radar_update` WebSocket message.

```json
{
  "type": "radar_update",
  "timestamp": "2025-01-15T12:00:00.000Z",
  "signal": 75.2,
  "rtt": 31.4,
  "variance": 1.23,
  "status": "HUMAN DETECTED: BREATHING (0.25Hz) (88%)",
  "learning_progress": 1.0,
  "motion_detected": false,
  "distance": 3.2,
  "bpm": 72.1,
  "is_simulation": false,
  "person_count": 1,
  "persons": [...],
  "zone_congestion": {"left": false, "center": false, "right": false},
  "multi_person_mode": "multi_person"
}
```

---

### GET /api/multi-person/stats

Live performance and detection statistics for the multi-person subsystem.

**Response**

```json
{
  "frame_id": 1042,
  "is_calibrated": true,
  "mode": "multi_person",
  "max_capacity": 5,
  "person_count": 2,
  "zone_person_counts": {
    "center": 2
  },
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

---

### POST /zones

Update the BSSID → room-name mapping used by the zone classifier.

**Request body**

```json
{
  "mappings": {
    "Living Room": "AA:BB:CC:DD:EE:FF",
    "Bedroom":     "11:22:33:44:55:66",
    "Kitchen":     "77:88:99:AA:BB:CC"
  }
}
```

**Response**

```json
{
  "message": "Zone mappings updated",
  "active_zones": ["Living Room", "Bedroom", "Kitchen"]
}
```

---

### POST /session/start

Start a new recording session.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | No | Human-readable session name |

**Response**

```json
{
  "message": "Recording started",
  "session_id": 42
}
```

---

### POST /session/stop

Stop the current recording session.

**Response**

```json
{
  "message": "Recording stopped"
}
```

---

### GET /sessions

List all recorded sessions, newest first.

**Response**

```json
[
  {
    "id": 42,
    "start_time": "2025-01-15T12:00:00",
    "end_time": "2025-01-15T12:30:00",
    "name": "Morning test"
  }
]
```

---

### GET /session/{session_id}/export

Export telemetry for a session as CSV.

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `session_id` | integer | Session ID from `/sessions` |

**Response** — `text/csv` download

```
id,session_id,timestamp,rssi,rtt,breathing_hz,walking_energy,status,active_zone
1,42,2025-01-15T12:00:00,75.2,31.4,0.25,0.12,HUMAN DETECTED: BREATHING,Living Room
```

---

## WebSocket

### Connection

```
ws://localhost:8000/ws/radar
```

The server broadcasts to **all** connected clients on every frame (~10 Hz).  
Clients do not need to send any messages (the server ignores incoming text).

---

### Message: `radar_update`

Sent every frame (~100 ms).

```typescript
interface RadarUpdate {
  type: "radar_update";
  timestamp: string;          // ISO-8601
  signal: number;             // RSSI (0–100 normalised)
  rtt: number;                // Round-trip time (ms)
  variance: number;           // RTT jitter
  status: string;             // Human-readable detection status
  learning_progress: number;  // 0.0 – 1.0 (calibration progress)
  motion_detected: boolean;
  distance: number;           // Estimated distance (metres)
  bpm: number | null;         // Heart rate (BPM) when still
  is_simulation: boolean;
  active_zone: string;        // Zone from /zones mapping
  // Multi-person fields
  person_count: number;       // 0 – 5
  persons: Person[];
  zone_congestion: ZoneCongestion;
  multi_person_mode: "single_person" | "multi_person";
}

interface Person {
  person_id: number;          // 1 – 5
  position_zone: "left" | "center" | "right" | "unknown";
  activity: "walking" | "breathing" | "still" | "gesture" | "unknown";
  confidence: number;         // 0 – 100
  signal_strength: number;    // dBm
}

interface ZoneCongestion {
  left: boolean;
  center: boolean;
  right: boolean;
}
```

---

### Message: `multi_person_update`

Sent **only** when `person_count > 1`.  
Same schema as `radar_update` but `type` is `"multi_person_update"`.

---

### Message: `fall_alert`

```typescript
interface FallAlert {
  type: "fall_alert";
  confidence: number;   // 0.0 – 1.0
  timestamp: string;    // ISO-8601
}
```

---

### Message: `gesture`

```typescript
interface GestureEvent {
  type: "gesture";
  gesture: "wave" | "still";
  confidence: number;   // 0.0 – 1.0
}
```

---

### Message: `system_status`

```typescript
interface SystemStatus {
  type: "system_status";
  status: "hw_disconnected" | "no_signal";
}
```

---

## Python SDK (internal)

### MultiPersonDetector

```python
from multi_person.modules.orchestrator import MultiPersonDetector

detector = MultiPersonDetector(
    max_capacity=5,
    mode="multi_person",          # or "single_person"
    target_latency_ms=100.0,
)

# Process one frame
result = detector.detect({
    "rssi": 75.0,
    "rtt": 30.0,
    "timestamp": "2025-01-15T12:00:00",
})

print(result.success)                  # True
print(result.processing_time_ms)       # e.g. 8.3
print(result.stage_timings.to_dict())  # per-stage breakdown

# Get WebSocket payload
payload = detector.get_output_payload()

# Performance stats
stats = detector.get_performance_stats()
print(stats.p95_ms)   # P95 latency over last 100 frames

# Combined stats dict (for /api/multi-person/stats)
stats_dict = detector.get_detection_stats()

# Mode switching
detector.set_mode("single_person")

# Event callbacks
def on_event(event):
    print(event)

detector.add_event_callback(on_event)
detector.remove_event_callback(on_event)

# Reset
detector.reset()
```

### DetectionResult

```python
@dataclass
class DetectionResult:
    success: bool
    persons: list[PersonState]
    processing_time_ms: float
    stage_timings: StageTimings | None
    error_message: str | None
```

### StageTimings

```python
@dataclass
class StageTimings:
    calibration_ms: float
    preprocessing_ms: float
    separation_ms: float
    feature_extraction_ms: float
    tracking_ms: float
    zone_update_ms: float

    @property
    def total_ms(self) -> float: ...

    def to_dict(self) -> dict[str, float]: ...
```

### PerformanceStats

```python
@dataclass
class PerformanceStats:
    frame_count: int
    avg_ms: float
    min_ms: float
    max_ms: float
    p95_ms: float
    p99_ms: float
    latency_violations: int
    stage_avg: dict[str, float]

    def to_dict(self) -> dict[str, Any]: ...
```

---

*WiWave v4 · API Reference v1.0*
