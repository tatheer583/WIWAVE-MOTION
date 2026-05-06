import asyncio
import json
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from wifi_reader import get_wifi_signal, get_network_devices, get_ping_latency
from motion_detector import MotionDetector

app = FastAPI(title="WiWave 3D Radar v3 (Dual-Sensor)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()
detector = MotionDetector()
device_count = 0

@app.websocket("/ws/radar")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect messages from client, but we must receive to keep alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def network_scan_loop():
    global device_count
    while True:
        device_count = get_network_devices()
        await asyncio.sleep(10)

async def radar_loop():
    print("Started Dual-Sensor Radar loop...")
    while True:
        # 1. Macro Sensor (RSSI)
        signal = get_wifi_signal()
        # 2. Micro Sensor (RTT)
        rtt = get_ping_latency()
        
        timestamp = datetime.now().isoformat()
        
        detector.add_rssi(signal)
        detector.add_rtt(rtt)
        
        status, jitter = detector.get_motion_status()
        distance = detector.get_estimated_distance()
        
        payload = {
            "timestamp": timestamp,
            "signal": signal or 0,
            "rtt": rtt or 0,
            "variance": round(jitter, 3),
            "status": status,
            "motion_detected": "DETECTED" in status,
            "device_count": device_count,
            "distance": round(distance, 2)
        }
        
        await manager.broadcast(json.dumps(payload))
        print(f"B-cast: RTT={rtt}ms, Jitter={jitter:.2f}, Status={status}")
        await asyncio.sleep(0.1)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(radar_loop())
    asyncio.create_task(network_scan_loop())

@app.get("/")
def read_root():
    return {"message": "WiWave v3 Backend Active (Dual-Sensor Mode)"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
