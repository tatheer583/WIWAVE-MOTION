"""WiWave live sensing server. Neither RSSI nor untrained CSI identifies people."""
import asyncio
from contextlib import asynccontextmanager, suppress
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import time

import aiosqlite
from fastapi import FastAPI, HTTPException, Request, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn
from sensing.detector import ChangeDetector
from sensing.sources import create_source

ROOT = Path(__file__).resolve().parent
DB_PATH = os.getenv('WIWAVE_DB_PATH', str(ROOT / 'wiwave_sessions.db'))
READ_RATE = float(os.getenv('SAMPLE_RATE_HZ', '10'))
CALIBRATION_SECONDS = float(os.getenv('WIWAVE_CALIBRATION_SECONDS', '20'))
if not 1 <= READ_RATE <= 100 or not 5 <= CALIBRATION_SECONDS <= 120:
    raise ValueError('SAMPLE_RATE_HZ must be 1-100; WIWAVE_CALIBRATION_SECONDS must be 5-120')
ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000', 'http://localhost:5173', 'http://127.0.0.1:5173']
ORIGINS += [x.strip() for x in os.getenv('WIWAVE_ALLOWED_ORIGINS', '').split(',') if x.strip()]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Runtime:
    def __init__(self, source):
        self.source = source
        self.detector = ChangeDetector(CALIBRATION_SECONDS)
        self.last_received = None
        self.latest = {}
        self.error = None
        self.sequence = 0
        self.invalid_frames = 0
        self.subscribers = set()
        self.session_id = None
        self.recording_error = None
        self.db_lock = asyncio.Lock()
        self.started = utc_now()

    def snapshot(self):
        age = time.monotonic() - self.last_received if self.last_received is not None else None
        fresh = age is not None and age < 3 and self.error is None
        state = self.latest.get('state', 'waiting') if fresh else 'disconnected' if self.error else 'stale' if age is not None else 'waiting'
        result = {'type': 'radar_update', 'sequence': self.sequence, 'timestamp': None,
                  'signal': None, 'rssi_dbm': None, 'rtt': None, 'variance': 0,
                  'learning_progress': 0, 'change_score': 0, 'motion_detected': False,
                  'read_rate_hz': 0, 'event_count': 0, **self.latest}
        result.update({
            'state': state, 'status': state.replace('_', ' ').upper(),
            'system_status': 'ok' if fresh else state, 'source': self.source.source,
            'is_simulation': self.source.source == 'simulation',
            'sample_age_ms': round(age * 1000) if age is not None else None,
            'error': self.error, 'invalid_frames': self.invalid_frames,
            'distance': None, 'bpm': None, 'person_count': None, 'persons': [],
            'multi_person_mode': 'unavailable', 'active_zone': 'Unknown',
            'capabilities': {'signal_monitoring': self.source.source != 'unavailable',
                             'csi': self.source.source == 'esp32_csi', 'human_detection': False,
                             'person_count': False, 'localization': False,
                             'object_classification': False, 'vital_signs': False},
            'recording': self.session_id is not None, 'session_id': self.session_id,
            'recording_error': self.recording_error,
        })
        if not fresh:
            result.update(motion_detected=False, change_score=0, read_rate_hz=0, signal=None, rssi_dbm=None)
        return result

    async def acquire(self):
        while True:
            tick = time.monotonic()
            try:
                sample = await asyncio.to_thread(self.source.read)
                if sample is not None:
                    now = time.monotonic()
                    detection = self.detector.update(sample, now)
                    self.sequence += 1
                    self.latest = {k: v for k, v in sample.items() if k != 'amplitudes'}
                    self.latest.update(detection, sequence=self.sequence, timestamp=utc_now())
                    self.last_received = now
                    self.error = None
            except ValueError as exc:
                self.invalid_frames += 1
                self.error = str(exc)
            except Exception as exc:
                self.error = str(exc)
                self.detector.reset()
                with suppress(Exception):
                    await asyncio.to_thread(self.source.close)
                await asyncio.sleep(1)
            delay = 0 if self.source.source == 'esp32_csi' else max(0, 1 / READ_RATE - (time.monotonic() - tick))
            await asyncio.sleep(delay)

    async def publish(self):
        while True:
            message = json.dumps(self.snapshot(), allow_nan=False)
            for queue in tuple(self.subscribers):
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(message)
            await asyncio.sleep(0.1)

    async def record(self):
        last_sequence = -1
        while True:
            await asyncio.sleep(0.2)
            async with self.db_lock:
                payload = self.snapshot()
                if self.session_id is None or payload['system_status'] != 'ok' or payload['sequence'] == last_sequence:
                    continue
                try:
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute('INSERT INTO sensing_telemetry (session_id,timestamp,payload) VALUES (?,?,?)',
                                         (self.session_id, payload['timestamp'], json.dumps(payload, allow_nan=False)))
                        await db.commit()
                    last_sequence = payload['sequence']
                    self.recording_error = None
                except Exception as exc:
                    self.recording_error = str(exc)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, start_time TEXT, end_time TEXT, name TEXT)')
        await db.execute('CREATE TABLE IF NOT EXISTS sensing_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, timestamp TEXT, payload TEXT, FOREIGN KEY(session_id) REFERENCES sessions(id))')
        await db.execute('CREATE INDEX IF NOT EXISTS sensing_session_idx ON sensing_telemetry(session_id)')
        await db.commit()


@asynccontextmanager
async def lifespan(app):
    await init_db()
    runtime = Runtime(create_source())
    app.state.runtime = runtime
    tasks = [asyncio.create_task(runtime.acquire()), asyncio.create_task(runtime.publish()), asyncio.create_task(runtime.record())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.to_thread(runtime.source.close)
        if runtime.session_id is not None:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute('UPDATE sessions SET end_time=? WHERE id=?', (utc_now(), runtime.session_id))
                await db.commit()


app = FastAPI(title='WiWave Live Sensing', version='5.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@app.middleware('http')
async def control_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    own_origin = str(request.base_url).rstrip('/')
    if request.method == 'POST' and origin and origin not in ORIGINS and origin != own_origin:
        return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
    return await call_next(request)


@app.get('/api/health')
async def health():
    runtime = app.state.runtime
    snapshot = runtime.snapshot()
    return {'status': 'ok' if snapshot['system_status'] == 'ok' else 'degraded',
            'version': '5.0.0', 'engine': runtime.source.source,
            'is_simulation': snapshot['is_simulation'], 'sensor_state': snapshot['state'],
            'sample_age_ms': snapshot['sample_age_ms'], 'read_rate_hz': snapshot['read_rate_hz'],
            'started_at': runtime.started, 'has_payload': runtime.sequence > 0,
            'ws_clients': len(runtime.subscribers), 'error': runtime.error}


@app.get('/api/poll')
async def poll_data():
    return app.state.runtime.snapshot()


@app.get('/api/capabilities')
async def capabilities():
    return app.state.runtime.snapshot()['capabilities']


@app.post('/api/calibrate')
async def calibrate():
    runtime = app.state.runtime
    runtime.detector.reset()
    runtime.latest.update(state='calibrating', learning_progress=0, motion_detected=False,
                          change_score=0, event_count=0, baseline_rssi_dbm=None)
    return {'message': 'Calibration restarted. Keep the room quiet and the receiver stationary.', 'seconds': CALIBRATION_SECONDS}


@app.get('/api/multi-person/stats')
async def multi_person_stats():
    return {'supported': False, 'person_count': None, 'reason': 'No validated person-count model is connected.'}


class ZoneMap(BaseModel):
    mappings: dict[str, str] = Field(default_factory=dict)


@app.post('/zones')
async def update_zones(zone_map: ZoneMap):
    app.state.zone_mappings = zone_map.mappings
    return {'message': 'Access point labels saved for this run; person localization is unavailable.', 'active_zones': list(zone_map.mappings)}


@app.post('/session/start')
async def start_session(name: str = 'Live sensing session'):
    runtime = app.state.runtime
    async with runtime.db_lock:
        if runtime.session_id is not None:
            raise HTTPException(409, 'A session is already recording')
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute('INSERT INTO sessions (start_time,name) VALUES (?,?)', (utc_now(), name[:200]))
            await db.commit()
            runtime.session_id = cursor.lastrowid
    return {'message': 'Recording started', 'session_id': runtime.session_id}


@app.post('/session/stop')
async def stop_session():
    runtime = app.state.runtime
    async with runtime.db_lock:
        if runtime.session_id is not None:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute('UPDATE sessions SET end_time=? WHERE id=?', (utc_now(), runtime.session_id))
                await db.commit()
            runtime.session_id = None
    return {'message': 'Recording stopped'}


@app.get('/sessions')
async def sessions():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM sessions ORDER BY id DESC LIMIT 200') as cursor:
            return [dict(row) for row in await cursor.fetchall()]


@app.get('/session/{session_id}/export')
async def export_session(session_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT id FROM sessions WHERE id=?', (session_id,)) as cursor:
            if await cursor.fetchone() is None:
                raise HTTPException(404, 'Session not found')
        async with db.execute('SELECT 1 FROM sensing_telemetry WHERE session_id=? LIMIT 1', (session_id,)) as cursor:
            has_new_data = await cursor.fetchone() is not None
        async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='telemetry'") as cursor:
            legacy_table_exists = await cursor.fetchone() is not None
        # Preserve CSV exports from pre-v5 sessions without altering their rows.
        if not has_new_data and legacy_table_exists:
            async with db.execute('SELECT * FROM telemetry WHERE session_id=? ORDER BY id', (session_id,)) as cursor:
                legacy_rows = await cursor.fetchall()
                if legacy_rows:
                    output = io.StringIO()
                    writer = csv.writer(output)
                    writer.writerow([column[0] for column in cursor.description])
                    writer.writerows(legacy_rows)
                    return StreamingResponse(iter([output.getvalue()]), media_type='text/csv',
                                             headers={'Content-Disposition': f'attachment; filename=wiwave_session_{session_id}.csv'})
    async def rows():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute('SELECT timestamp,payload FROM sensing_telemetry WHERE session_id=? ORDER BY id', (session_id,)) as cursor:
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                writer.writerow(['timestamp', 'source', 'rssi_dbm', 'state', 'change_score', 'read_rate_hz', 'is_simulation'])
                yield buffer.getvalue()
                async for ts, raw in cursor:
                    payload = json.loads(raw)
                    buffer.seek(0)
                    buffer.truncate(0)
                    writer.writerow([ts] + [payload.get(key) for key in ['source', 'rssi_dbm', 'state', 'change_score', 'read_rate_hz', 'is_simulation']])
                    yield buffer.getvalue()
    return StreamingResponse(rows(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename=wiwave_session_{session_id}.csv'})


@app.get('/session/{session_id}/frames')
async def session_frames(session_id: int, limit: int = Query(10000, ge=1, le=10000)):
    """Bounded replay of recorded snapshots, preserving original provenance."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT id FROM sessions WHERE id=?', (session_id,)) as cursor:
            if await cursor.fetchone() is None:
                raise HTTPException(404, 'Session not found')
        async with db.execute('SELECT payload FROM sensing_telemetry WHERE session_id=? ORDER BY id LIMIT ?', (session_id, limit + 1)) as cursor:
            rows = await cursor.fetchall()
    return {'session_id': session_id, 'frames': [json.loads(row[0]) for row in rows[:limit]],
            'truncated': len(rows) > limit, 'is_replay': True}


@app.websocket('/ws/radar')
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get('origin')
    own_origins = {f'http://{websocket.headers.get("host")}', f'https://{websocket.headers.get("host")}'}
    if origin and origin not in ORIGINS and origin not in own_origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    runtime = app.state.runtime
    queue = asyncio.Queue(maxsize=1)
    runtime.subscribers.add(queue)

    async def send():
        await websocket.send_json(runtime.snapshot())
        while True:
            await asyncio.wait_for(websocket.send_text(await queue.get()), timeout=2)

    async def receive():
        while True:
            await websocket.receive_text()

    sender, receiver = asyncio.create_task(send()), asyncio.create_task(receive())
    try:
        await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        runtime.subscribers.discard(queue)
        for task in (sender, receiver):
            task.cancel()
        await asyncio.gather(sender, receiver, return_exceptions=True)
        with suppress(Exception):
            await websocket.close()


frontend = ROOT / 'frontend' / 'dist'
if (frontend / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')


@app.get('/{path:path}')
async def frontend_page(path: str):
    if path.startswith(('api/', 'session/', 'ws/')):
        raise HTTPException(404)
    if not (frontend / 'index.html').exists():
        return {'message': 'WiWave API is running. Build frontend with npm run build.', 'health': '/api/health'}
    candidate = (frontend / path).resolve()
    if not candidate.is_relative_to(frontend.resolve()):
        raise HTTPException(404)
    return FileResponse(candidate if path and candidate.is_file() else frontend / 'index.html')


if __name__ == '__main__':
    uvicorn.run('server:app', host=os.getenv('WIWAVE_HOST', '127.0.0.1'), port=int(os.getenv('PORT', '8000')), reload=False)
