# WiWave Deployment Guide

## Architecture overview

```
┌──────────────────────────────────────────────────────────┐
│  Browser / Mobile                                        │
│  React + Three.js dashboard                             │
└────────────────────┬─────────────────────────────────────┘
                     │  WebSocket  ws://host:8000/ws/radar
                     │  REST       http://host:8000/api/*
┌────────────────────▼─────────────────────────────────────┐
│  FastAPI server  (server.py)                             │
│  ├─ MotionDetector          (single-person DSP)          │
│  ├─ MultiPersonDetector     (multi-person pipeline)      │
│  ├─ SessionRecorder         (SQLite telemetry)           │
│  └─ ZoneClassifier          (BSSID → room mapping)       │
└────────────────────┬─────────────────────────────────────┘
                     │  RSSI / RTT
┌────────────────────▼─────────────────────────────────────┐
│  Wi-Fi hardware layer  (wifi_reader.py)                  │
│  Linux: iw / iwconfig   Windows: netsh   macOS: airport  │
└──────────────────────────────────────────────────────────┘
```

---

## Hardware requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores, 1.5 GHz | 4 cores, 2.5 GHz |
| RAM | 1 GB | 4 GB |
| OS | Linux / Windows / macOS | Ubuntu 22.04 LTS |
| Wi-Fi adapter | 802.11n (Wi-Fi 4) | 802.11ac (Wi-Fi 5) |
| Access points | 1 | 2–3 in different rooms |
| Python | 3.10 | 3.11+ |
| Node.js | 18 | 20 LTS |

---

## Local development

### 1 — Clone and install

```bash
git clone <repo-url>
cd "WiWave 2"

# Python dependencies
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt

# Frontend dependencies
cd frontend
npm install
cd ..
```

### 2 — Build the frontend

```bash
cd frontend
npm run build
cd ..
```

### 3 — Run the server

```bash
# Simulation mode (no Wi-Fi hardware needed)
set SIMULATION_MODE=true        # Windows CMD
# export SIMULATION_MODE=true   # Linux / macOS

python server.py
```

Open `http://localhost:8000` in your browser.

### 4 — Run tests

```bash
# All unit + integration tests
python -m pytest multi_person/tests/ -v

# With coverage
python -m pytest multi_person/tests/ --cov=multi_person --cov-report=term-missing
```

---

## Production deployment

### Option A — Single server (Raspberry Pi / VPS)

```bash
# Install dependencies
pip install -r requirements.txt

# Build frontend
cd frontend && npm run build && cd ..

# Run with production settings
set ENVIRONMENT=prod
set PORT=8000
python server.py
```

Use a process manager to keep it running:

```bash
# Using PM2 (Node.js process manager, works for Python too)
npm install -g pm2
pm2 start "python server.py" --name wiwave
pm2 save
pm2 startup
```

Or systemd on Linux:

```ini
# /etc/systemd/system/wiwave.service
[Unit]
Description=WiWave Motion Detection Server
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/wiwave
Environment=ENVIRONMENT=prod
Environment=PORT=8000
ExecStart=/home/pi/wiwave/.venv/bin/python server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable wiwave
sudo systemctl start wiwave
```

### Option B — Render.com (cloud)

A `render.yaml` is included in the repository:

```yaml
# render.yaml (already in repo)
services:
  - type: web
    name: wiwave
    env: python
    buildCommand: "pip install -r requirements.txt && cd frontend && npm install && npm run build"
    startCommand: "python server.py"
    envVars:
      - key: ENVIRONMENT
        value: prod
      - key: SIMULATION_MODE
        value: "true"   # real hardware not available in cloud
```

Deploy:

```bash
# Install Render CLI
npm install -g @render-com/cli

render deploy
```

### Option C — Docker

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build frontend
COPY frontend/package*.json frontend/
RUN cd frontend && npm ci
COPY frontend/ frontend/
RUN cd frontend && npm run build

COPY . .

ENV ENVIRONMENT=prod
ENV PORT=8000
EXPOSE 8000

CMD ["python", "server.py"]
```

```bash
docker build -t wiwave .
docker run -p 8000:8000 -e SIMULATION_MODE=true wiwave
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SIMULATION_MODE` | `false` | Use simulated Wi-Fi data (no hardware) |
| `PORT` | `8000` | HTTP / WebSocket port |
| `ENVIRONMENT` | `dev` | `prod` disables Uvicorn hot-reload |

---

## Database

WiWave uses SQLite (`wiwave_sessions.db`) for session telemetry.

- Created automatically on first run
- Located in the project root
- Backed up by copying the `.db` file

To reset the database:

```bash
del wiwave_sessions.db    # Windows
# rm wiwave_sessions.db   # Linux / macOS
```

---

## Logging

Structured logs are written to stdout.  
Log level is controlled by the Python `logging` module.

To enable debug logs for the multi-person pipeline:

```python
import logging
logging.getLogger("WiWave.MultiPerson.Orchestrator").setLevel(logging.DEBUG)
```

Log format:

```
[frame=42] Detection OK | persons=2 latency=8.3ms
[frame=43] Latency violation: 112.4ms > 100ms target | stages={...}
[frame=44] Separated into 2 signal(s) | mode=multi_person
```

---

## Performance tuning

### Reduce latency

1. Lower `max_capacity` (e.g. `3` instead of `5`)
2. Increase CPU clock speed or add cores
3. Run on a dedicated machine (no other heavy processes)
4. Use a wired Ethernet connection to the AP for lower RTT variance

### Improve detection accuracy

1. Add a second or third AP in different rooms
2. POST zone mappings via `/zones` so the classifier knows your layout
3. Keep the server machine stationary (its own Wi-Fi activity adds noise)
4. Avoid microwave ovens and cordless phones (2.4 GHz interference)

### Memory

The rolling performance history is capped at 100 frames (~10 seconds at 10 Hz).  
Total memory footprint is typically < 100 MB.

---

## Security notes

- The API has no authentication by default — suitable for local / home use.
- For public deployments, add an API key middleware or put Nginx in front.
- The SQLite database contains motion telemetry — treat it as personal data.
- CORS is set to `allow_origins=["*"]` — restrict this in production.

---

## Updating

```bash
git pull
pip install -r requirements.txt   # pick up new Python deps
cd frontend && npm install && npm run build && cd ..
# restart the server
```

---

*WiWave v4 · Deployment Guide v1.0*
