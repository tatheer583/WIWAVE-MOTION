import aiosqlite
import json
import asyncio
import csv
import io
import re
import os
import random
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from wifi_reader import create_wifi_reader, get_network_devices, HardwareError
from motion_detector import MotionDetector

app = FastAPI(title="WiWave 3D Radar v4 (Full Persistence + Zoning)")

# Use environment variable for simulation mode, or auto-detect
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "false").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class ZoneMap(BaseModel):
    mappings: dict[str, str] # Room Name -> BSSID

# --- DATABASE SETUP ---
DB_PATH = "wiwave_sessions.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT, end_time TEXT, name TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER,
                timestamp TEXT, rssi REAL, rtt REAL, breathing_hz REAL,
                walking_energy REAL, status TEXT, active_zone TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
        """)
        await db.commit()

# --- SIMULATION ENGINE ---
class SimulationEngine:
    def __init__(self):
        self.base_rssi = 75
        self.base_rtt = 30
        self.counter = 0

    def get_data(self):
        self.counter += 1
        # Create a "walking" pattern every 20 seconds
        is_walking = (self.counter % 200) > 150 
        
        rssi_noise = random.uniform(-1, 1)
        rtt_noise = random.uniform(-5, 5)
        
        if is_walking:
            rssi_noise += random.uniform(-5, 5)
            rtt_noise += random.uniform(20, 100)
            
        return {
            "signal": max(0, min(100, self.base_rssi + rssi_noise)),
            "rtt": max(1, self.base_rtt + rtt_noise),
            "aps": [{"bssid": "SIM:01:02:03", "signal": 80}, {"bssid": "SIM:04:05:06", "signal": 45}],
            "devices": 3
        }

# --- ZONE CLASSIFIER ---
class ZoneClassifier:
    def __init__(self):
        self.mappings = {} # BSSID -> Room Name

    def update_mappings(self, new_map: dict[str, str]):
        self.mappings = {bssid.upper(): room for room, bssid in new_map.items()}

    def get_zone(self, visible_aps: list[dict]):
        if not visible_aps: return "Unknown"
        sorted_aps = sorted(visible_aps, key=lambda x: x["signal"], reverse=True)
        for ap in sorted_aps:
            bssid = ap["bssid"].upper()
            if bssid in self.mappings:
                return self.mappings[bssid]
        return "Unknown"

# --- SESSION RECORDER ---
class SessionRecorder:
    def __init__(self):
        self.current_session_id = None
        self.is_recording = False

    async def start(self, name: str = None):
        async with aiosqlite.connect(DB_PATH) as db:
            now = datetime.now().isoformat()
            cursor = await db.execute("INSERT INTO sessions (start_time, name) VALUES (?, ?)", (now, name or f"Session {now}"))
            self.current_session_id = cursor.lastrowid
            await db.commit()
        self.is_recording = True
        return self.current_session_id

    async def stop(self):
        if not self.is_recording: return
        async with aiosqlite.connect(DB_PATH) as db:
            now = datetime.now().isoformat()
            await db.execute("UPDATE sessions SET end_time = ? WHERE id = ?", (now, self.current_session_id))
            await db.commit()
        self.is_recording = False
        self.current_session_id = None

    async def log(self, payload: dict, breathing_hz: float, walking_energy: float):
        if not self.is_recording: return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO telemetry (session_id, timestamp, rssi, rtt, breathing_hz, walking_energy, status, active_zone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (self.current_session_id, payload["timestamp"], payload["signal"], payload["rtt"], breathing_hz, walking_energy, payload["status"], payload["active_zone"]))
            await db.commit()

# --- APP STATE ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections: self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try: await connection.send_text(message)
            except: pass

manager = ConnectionManager()
detector = MotionDetector()
reader = None
simulator = SimulationEngine()
recorder = SessionRecorder()
zones = ZoneClassifier()
data_queue = asyncio.Queue(maxsize=200)
device_count = 0
is_motion_active = False
active_aps = []

# --- SENSOR LOOPS ---
async def adaptive_sensor_loop():
    global is_motion_active, reader, SIMULATION_MODE, active_aps, device_count
    
    # Initialize hardware reader if not in simulation mode
    if not SIMULATION_MODE:
        try:
            reader = create_wifi_reader()
        except Exception:
            print("!!! Hardware access failed. Falling back to SIMULATION MODE.")
            SIMULATION_MODE = True

    while True:
        try:
            start_time = asyncio.get_event_loop().time()
            rate = 10.0 if is_motion_active else 2.0
            
            if SIMULATION_MODE:
                sim_data = simulator.get_data()
                rtt, signal = sim_data["rtt"], sim_data["signal"]
                active_aps = sim_data["aps"]
                device_count = sim_data["devices"]
            else:
                rtt = await reader.get_rtt()
                signal = reader.get_rssi()
            
            await data_queue.put({"rtt": rtt, "signal": signal, "ts": datetime.now()})
            elapsed = asyncio.get_event_loop().time() - start_time
            await asyncio.sleep(max(0, (1.0/rate) - elapsed))
        except HardwareError:
            await manager.broadcast(json.dumps({"type": "system_status", "status": "hw_disconnected"}))
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Sensor Loop Error: {e}")
            await asyncio.sleep(1)

async def network_scan_loop():
    global active_aps, device_count, reader, SIMULATION_MODE
    while True:
        if not SIMULATION_MODE and reader:
            try:
                active_aps = reader.get_all_aps()
                device_count = get_network_devices()
            except: pass
        await asyncio.sleep(10)

async def processing_loop():
    global is_motion_active
    consecutive_none_count = 0
    while True:
        data = await data_queue.get()
        rtt, signal, ts = data["rtt"], data["signal"], data["ts"]
        if rtt is None:
            consecutive_none_count += 1
            if consecutive_none_count == 30:
                detector.reset_rtt_state()
                await manager.broadcast(json.dumps({"type": "system_status", "status": "no_signal"}))
        else:
            consecutive_none_count = 0
            detector.add_rtt(rtt, timestamp=ts)
        detector.add_rssi(signal)
        status, jitter, fall_event, learn_progress, gesture_event = detector.get_motion_status()
        distance = detector.get_estimated_distance()
        is_motion_active = "DETECTED" in status
        active_zone = zones.get_zone(active_aps)
        freqs = detector._analyze_frequencies()
        b_energy, w_energy, b_hz, w_hz = freqs["breathing_energy"], freqs["walking_energy"], freqs["breathing_hz"], freqs["walking_hz"]

        payload = {
            "type": "radar_update", "timestamp": ts.isoformat(),
            "active_zone": active_zone, "signal": signal or 0, "rtt": rtt or 0,
            "variance": round(jitter, 3), "status": "NO SIGNAL" if consecutive_none_count >= 30 else status,
            "learning_progress": round(learn_progress, 2), "motion_detected": is_motion_active,
            "distance": round(distance, 2),
            "is_simulation": SIMULATION_MODE
        }
        await manager.broadcast(json.dumps(payload))
        
        # Handle Fall Alert
        if fall_event:
            print(f"[!!!] FALL DETECTED (Confidence: {fall_event.confidence:.2f})")
            alert_payload = {
                "type": "fall_alert",
                "confidence": round(fall_event.confidence, 2),
                "timestamp": fall_event.timestamp.isoformat()
            }
            await manager.broadcast(json.dumps(alert_payload))
            
        # Handle Gesture Event
        if gesture_event:
            await manager.broadcast(json.dumps({
                "type": "gesture",
                "gesture": gesture_event.type,
                "confidence": round(gesture_event.confidence, 2)
            }))
            
        if recorder.is_recording: await recorder.log(payload, b_hz, w_energy)
        data_queue.task_done()

# --- API ENDPOINTS ---
@app.on_event("startup")
async def startup_event():
    await init_db()
    asyncio.create_task(adaptive_sensor_loop())
    asyncio.create_task(processing_loop())
    asyncio.create_task(network_scan_loop())

@app.post("/zones")
async def update_zones(zone_map: ZoneMap):
    zones.update_mappings(zone_map.mappings)
    return {"message": "Zone mappings updated", "active_zones": list(zone_map.mappings.keys())}

@app.post("/session/start")
async def start_session(name: str = None):
    session_id = await recorder.start(name)
    return {"message": "Recording started", "session_id": session_id}

@app.post("/session/stop")
async def stop_session():
    await recorder.stop()
    return {"message": "Recording stopped"}

@app.get("/sessions")
async def get_sessions():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM sessions ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

@app.get("/session/{session_id}/export")
async def export_session(session_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM telemetry WHERE session_id = ?", (session_id,))
        rows = await cursor.fetchall()
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["id", "session_id", "timestamp", "rssi", "rtt", "breathing_hz", "walking_energy", "status", "active_zone"])
        writer.writeheader()
        writer.writerows([dict(row) for row in rows])
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=wiwave_session_{session_id}.csv"})

@app.websocket("/ws/radar")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
