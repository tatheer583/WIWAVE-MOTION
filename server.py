"""WiWave live sensing server. Neither RSSI nor untrained CSI identifies people."""
import asyncio
from contextlib import asynccontextmanager, suppress
import csv
from collections import deque
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import time
from typing import Literal

import aiosqlite
from fastapi import FastAPI, HTTPException, Request, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import numpy as np
import uvicorn
from sensing.detector import ChangeDetector
from sensing.sources import create_source
from sensing.spectral import SpectralAnalyzer

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
        self.spectral = SpectralAnalyzer(rate_hz=READ_RATE)
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
        self.csi_queue = asyncio.Queue(maxsize=100)
        self.csi_trial = None
        self.csi_trial_error = None
        self.recent_frames = deque(maxlen=300)
        self.event_frames = []
        self.pending_event = None
        self.event_started_mono = None
        self.prev_motion = False
        self.event_queue = asyncio.Queue(maxsize=20)
        self.alerts_enabled = os.getenv('WIWAVE_ALERTS', '0').lower() in {'1', 'true', 'yes'}

    def snapshot(self):
        age = time.monotonic() - self.last_received if self.last_received is not None else None
        fresh = age is not None and age < 3 and self.error is None
        state = self.latest.get('state', 'waiting') if fresh else 'disconnected' if self.error else 'stale' if age is not None else 'waiting'
        synthetic = self.source.source in ('simulation', 'csi_simulation')
        result = {'type': 'radar_update', 'sequence': self.sequence, 'timestamp': None,
                  'signal': None, 'rssi_dbm': None, 'rtt': None, 'variance': 0,
                  'learning_progress': 0, 'change_score': 0, 'motion_detected': False,
                  'read_rate_hz': 0, 'event_count': 0, **self.latest}
        result.update({
            'state': state, 'status': state.replace('_', ' ').upper(),
            'system_status': 'ok' if fresh else state, 'source': self.source.source,
            'is_simulation': synthetic,
            'sample_age_ms': round(age * 1000) if age is not None else None,
            'error': self.error, 'invalid_frames': self.invalid_frames,
            'links': self.latest.get('links', []),
            'spectral': self.latest.get('spectral') if fresh else None,
            'csi_preview': self.latest.get('csi_preview') if fresh else None,
            'distance': None, 'bpm': None, 'person_count': None, 'persons': [],
            'multi_person_mode': 'unavailable', 'active_zone': 'Unknown',
            'capabilities': {'signal_monitoring': self.source.source != 'unavailable',
                             'csi': self.source.source in ('esp32_csi', 'csi_simulation'),
                             'multi_link': self.source.source == 'native_rssi',
                             'human_detection': False,
                             'person_count': False, 'localization': False,
                             'object_classification': False, 'vital_signs': False},
            'recording': self.session_id is not None, 'session_id': self.session_id,
            'recording_error': self.recording_error,
            'alerts_enabled': self.alerts_enabled,
            'csi_trial': ({'id': self.csi_trial['id'], 'active': self.csi_trial['active'],
                           'label': self.csi_trial['label'], 'samples': self.csi_trial['samples'],
                           'dropped': self.csi_trial['dropped']}
                          if self.csi_trial else None),
        })
        if not fresh:
            result.update(motion_detected=False, change_score=0, read_rate_hz=0, signal=None, rssi_dbm=None)
        return result

    def observe_event(self, detection, now):
        """Track detector transitions into bounded pre/post event records."""
        motion = bool(detection.get('motion_detected'))
        frame = {'ts': self.latest.get('timestamp'), 'r': self.latest.get('rssi_dbm'),
                 's': detection.get('change_score'), 'st': detection.get('state')}
        self.recent_frames.append(frame)
        if motion and not self.prev_motion:
            links = self.latest.get('links') or []
            self.pending_event = {
                'started_at': self.latest.get('timestamp'), 'source': self.source.source,
                'channel': self.latest.get('channel'), 'baseline_dbm': detection.get('baseline_rssi_dbm'),
                'peak_change_score': detection.get('change_score', 0),
                'neighbor_links': len(links),
                'pre_frames': [dict(f) for f in tuple(self.recent_frames)[:-1]],
                'post_frames': [],
            }
            self.event_frames = [frame]
            self.event_started_mono = now
            if self.alerts_enabled:
                asyncio.create_task(self.fire_alert())
        elif motion and self.pending_event:
            self.pending_event['peak_change_score'] = max(self.pending_event['peak_change_score'],
                                                          detection.get('change_score', 0))
            if len(self.event_frames) < 300:
                self.event_frames.append(frame)
        elif not motion and self.prev_motion and self.pending_event:
            event = self.pending_event
            event['ended_at'] = self.latest.get('timestamp')
            event['duration_s'] = round(now - self.event_started_mono, 2) if self.event_started_mono else None
            event['post_frames'] = self.event_frames[1:]
            self.pending_event = None
            self.event_frames = []
            with suppress(asyncio.QueueFull):
                self.event_queue.put_nowait(event)
        self.prev_motion = motion

    def interrupt_event(self):
        """Close an open event record when the sensor fails mid-event."""
        if not self.pending_event:
            return
        event = self.pending_event
        event['ended_at'] = self.latest.get('timestamp')
        event['duration_s'] = round(time.monotonic() - self.event_started_mono, 2) if self.event_started_mono else None
        event['stop_reason'] = 'sensor_interrupted'
        event['post_frames'] = self.event_frames[1:]
        self.pending_event = None
        self.event_frames = []
        with suppress(asyncio.QueueFull):
            self.event_queue.put_nowait(event)

    async def fire_alert(self):
        script = ROOT / 'scripts' / 'alert.ps1'
        if not script.exists():
            return
        with suppress(Exception):
            await asyncio.create_subprocess_exec(
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                '-Title', 'WiWave signal change', '-Body', 'A sustained Wi-Fi signal change was detected.',
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)

    async def write_events(self):
        while True:
            event = await self.event_queue.get()
            await self.write_one_event(event)

    async def write_one_event(self, event):
        async with self.db_lock:
            try:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        'INSERT INTO events (started_at,ended_at,duration_s,peak_change_score,source,channel,baseline_dbm,neighbor_links,stop_reason,pre_frames,post_frames) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (event.get('started_at'), event.get('ended_at'), event.get('duration_s'),
                         event.get('peak_change_score'), event.get('source'), event.get('channel'),
                         event.get('baseline_dbm'), event.get('neighbor_links'),
                         event.get('stop_reason'), json.dumps(event.get('pre_frames', [])[-300:], allow_nan=False),
                         json.dumps(event.get('post_frames', [])[-300:], allow_nan=False)))
                    await db.commit()
            except Exception:
                pass

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
                    self.latest.update(detection, sequence=self.sequence, timestamp=utc_now(),
                                       amplitudes_ready=sample.get('amplitudes') is not None,
                                       subcarrier_count=len(sample['amplitudes']) if sample.get('amplitudes') is not None else None)
                    stats = self.spectral.update(now, sample.get('rssi_dbm'))
                    if stats is not None:
                        self.latest['spectral'] = stats
                    if sample.get('amplitudes'):
                        step = max(1, round(len(sample['amplitudes']) / 64))
                        self.latest['csi_preview'] = [round(float(v), 2) for v in sample['amplitudes'][::step][:64]]
                    self.last_received = now
                    self.error = None
                    self.observe_event(detection, now)
                    trial = self.csi_trial
                    if trial and trial['active'] and sample.get('amplitudes') is not None:
                        if now >= trial['deadline']:
                            trial['active'] = False
                            trial['stop_reason'] = 'time_limit'
                        elif trial['accepted'] >= trial['limit']:
                            trial['active'] = False
                            trial['stop_reason'] = 'storage_limit'
                        elif now >= trial['next_capture']:
                            trial['next_capture'] = now + 0.1
                            frame = {'timestamp': self.latest['timestamp'], 'sequence': self.sequence,
                                     'label': trial['label'], 'rssi_dbm': sample.get('rssi_dbm'),
                                     'channel': sample.get('channel'),
                                     'subcarrier_count': len(sample['amplitudes']),
                                     'amplitudes': sample['amplitudes'][:512],
                                     'truncated': len(sample['amplitudes']) > 512}
                            try:
                                self.csi_queue.put_nowait((trial['id'], frame))
                                trial['accepted'] += 1
                            except asyncio.QueueFull:
                                trial['dropped'] += 1
            except ValueError as exc:
                self.invalid_frames += 1
                self.error = str(exc)
                self.interrupt_event()
            except Exception as exc:
                self.error = str(exc)
                self.detector.reset()
                self.interrupt_event()
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

    async def record_csi_trials(self):
        while True:
            trial = self.csi_trial
            if trial and trial['active']:
                if time.monotonic() >= trial['deadline']:
                    trial['active'] = False
                    trial['stop_reason'] = 'time_limit'
                elif self.last_received is None or time.monotonic() - self.last_received > 3:
                    trial['active'] = False
                    trial['stop_reason'] = 'sensor_disconnected'

            batch = []
            try:
                batch.append(await asyncio.wait_for(self.csi_queue.get(), timeout=0.25))
            except asyncio.TimeoutError:
                pass
            while len(batch) < 25:
                try:
                    batch.append(self.csi_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if batch:
                by_trial = {}
                for trial_id, _ in batch:
                    by_trial[trial_id] = by_trial.get(trial_id, 0) + 1
                try:
                    async with self.db_lock:
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.executemany(
                                'INSERT INTO csi_trial_samples (trial_id,timestamp,sequence,label,rssi_dbm,channel,subcarrier_count,amplitudes,truncated) VALUES (?,?,?,?,?,?,?,?,?)',
                                [(trial_id, frame['timestamp'], frame['sequence'], frame['label'], frame['rssi_dbm'],
                                  frame['channel'], frame['subcarrier_count'], json.dumps(frame['amplitudes']), frame['truncated'])
                                 for trial_id, frame in batch])
                            for trial_id, count in by_trial.items():
                                await db.execute('UPDATE csi_trials SET sample_count=sample_count+? WHERE id=?', (count, trial_id))
                            await db.commit()
                    if self.csi_trial and self.csi_trial['id'] in by_trial:
                        self.csi_trial['samples'] += by_trial[self.csi_trial['id']]
                except Exception as exc:
                    self.csi_trial_error = str(exc)
                    trial = self.csi_trial
                    if trial and trial['id'] in by_trial:
                        trial['dropped'] += by_trial[trial['id']]

            trial = self.csi_trial
            if trial and not trial['active'] and self.csi_queue.empty():
                try:
                    async with self.db_lock:
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute('UPDATE csi_trials SET end_time=?,stop_reason=?,dropped_samples=? WHERE id=?',
                                             (utc_now(), trial.get('stop_reason', 'stopped'), trial['dropped'], trial['id']))
                            await db.commit()
                    self.csi_trial = None
                except Exception as exc:
                    self.csi_trial_error = str(exc)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, start_time TEXT, end_time TEXT, name TEXT)')
        await db.execute('CREATE TABLE IF NOT EXISTS sensing_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, timestamp TEXT, payload TEXT, FOREIGN KEY(session_id) REFERENCES sessions(id))')
        await db.execute('CREATE INDEX IF NOT EXISTS sensing_session_idx ON sensing_telemetry(session_id)')
        await db.execute('CREATE TABLE IF NOT EXISTS csi_trials (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, initial_label TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT, stop_reason TEXT, sample_count INTEGER NOT NULL DEFAULT 0, dropped_samples INTEGER NOT NULL DEFAULT 0)')
        await db.execute('CREATE TABLE IF NOT EXISTS csi_trial_samples (id INTEGER PRIMARY KEY AUTOINCREMENT, trial_id INTEGER NOT NULL, timestamp TEXT NOT NULL, sequence INTEGER NOT NULL, label TEXT NOT NULL, rssi_dbm REAL, channel INTEGER, subcarrier_count INTEGER NOT NULL, amplitudes TEXT NOT NULL, truncated INTEGER NOT NULL, FOREIGN KEY(trial_id) REFERENCES csi_trials(id))')
        await db.execute('CREATE INDEX IF NOT EXISTS csi_trial_sample_idx ON csi_trial_samples(trial_id,id)')
        await db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, ended_at TEXT, duration_s REAL, peak_change_score REAL, source TEXT, channel INTEGER, baseline_dbm REAL, neighbor_links INTEGER, stop_reason TEXT, pre_frames TEXT NOT NULL, post_frames TEXT NOT NULL)')
        await db.execute('CREATE INDEX IF NOT EXISTS events_started_idx ON events(started_at)')
        await db.execute("UPDATE csi_trials SET end_time=?,stop_reason='server_restarted' WHERE end_time IS NULL", (utc_now(),))
        await db.commit()


@asynccontextmanager
async def lifespan(app):
    await init_db()
    runtime = Runtime(create_source())
    app.state.runtime = runtime
    tasks = [asyncio.create_task(runtime.acquire()), asyncio.create_task(runtime.publish()),
             asyncio.create_task(runtime.record()), asyncio.create_task(runtime.record_csi_trials()),
             asyncio.create_task(runtime.write_events())]
    try:
        yield
    finally:
        if runtime.csi_trial:
            runtime.csi_trial['active'] = False
            runtime.csi_trial['stop_reason'] = 'server_shutdown'
            deadline = time.monotonic() + 3
            while runtime.csi_trial and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
        if runtime.pending_event:
            runtime.interrupt_event()
            try:
                event = await asyncio.wait_for(runtime.event_queue.get(), timeout=2)
                await runtime.write_one_event(event)
            except Exception:
                pass
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.to_thread(runtime.source.close)
        if runtime.session_id is not None:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute('UPDATE sessions SET end_time=? WHERE id=?', (utc_now(), runtime.session_id))
                await db.commit()


app = FastAPI(title='WiWave Live Sensing', version='6.0.0', lifespan=lifespan)
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
            'version': '6.0.0', 'engine': runtime.source.source,
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


class CsiTrialStart(BaseModel):
    name: str = Field(default='Room trial', min_length=1, max_length=80)
    label: Literal['empty_room', 'person_still', 'person_moving', 'fan_interference', 'door_change', 'pet_or_other_motion']
    seconds: int = Field(default=120, ge=10, le=180)


class CsiTrialLabel(BaseModel):
    label: Literal['empty_room', 'person_still', 'person_moving', 'fan_interference', 'door_change', 'pet_or_other_motion']


@app.get('/api/csi/trials')
async def csi_trials():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM csi_trials ORDER BY id DESC LIMIT 50') as cursor:
            trials = [dict(row) for row in await cursor.fetchall()]
        async with db.execute('SELECT COALESCE(SUM(sample_count),0) FROM csi_trials') as cursor:
            total_samples = (await cursor.fetchone())[0]
    return {'active': app.state.runtime.snapshot()['csi_trial'], 'trials': trials,
            'total_samples': total_samples, 'error': app.state.runtime.csi_trial_error}


@app.post('/api/csi/trials/start')
async def start_csi_trial(request: CsiTrialStart):
    runtime = app.state.runtime
    if runtime.source.source != 'esp32_csi':
        raise HTTPException(409, 'Select and connect an ESP32 CSI serial source before collecting CSI trials.')
    if runtime.snapshot()['system_status'] != 'ok' or not runtime.latest.get('amplitudes_ready', False):
        raise HTTPException(409, 'Waiting for fresh CSI frames. Check the serial port and firmware CSV stream.')
    if not request.name.strip():
        raise HTTPException(422, 'Give this trial a short non-identifying name.')
    async with runtime.db_lock:
        if runtime.csi_trial:
            raise HTTPException(409, 'Stop or wait for the current CSI trial before starting another.')
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute('SELECT COALESCE(SUM(sample_count),0) FROM csi_trials') as cursor:
                total = (await cursor.fetchone())[0]
            if total >= 15000:
                raise HTTPException(409, 'Local CSI trial capacity reached. Export and remove old trials before collecting more data.')
            limit = min(request.seconds * 10, 15000 - total)
            cursor = await db.execute('INSERT INTO csi_trials (name,initial_label,start_time) VALUES (?,?,?)',
                                      (request.name.strip(), request.label, utc_now()))
            await db.commit()
        now = time.monotonic()
        runtime.csi_trial_error = None
        trial_id = cursor.lastrowid
        runtime.csi_trial = {'id': trial_id, 'label': request.label, 'active': True,
                             'deadline': now + request.seconds, 'next_capture': 0.0,
                             'samples': 0, 'accepted': 0, 'limit': limit,
                             'dropped': 0, 'stop_reason': 'stopped'}
    return {'message': 'CSI amplitude trial started. Samples are stored only in the local database.',
            'trial_id': trial_id, 'seconds': request.seconds, 'sample_rate_limit_hz': 10,
            'amplitude_bins_limit': 512, 'sample_limit': limit, 'schema': 'wiwave-csi-amplitude-v1'}


@app.post('/api/csi/trials/label')
async def label_csi_trial(request: CsiTrialLabel):
    runtime = app.state.runtime
    trial = runtime.csi_trial
    if not trial or not trial['active']:
        raise HTTPException(409, 'No CSI trial is currently collecting samples.')
    trial['label'] = request.label
    return {'message': 'Label changed. New frames will use this label.', 'label': request.label}


@app.post('/api/csi/trials/stop')
async def stop_csi_trial():
    trial = app.state.runtime.csi_trial
    if not trial:
        return {'message': 'No CSI trial is active.'}
    trial['active'] = False
    trial['stop_reason'] = 'stopped_by_operator'
    return {'message': 'CSI trial is stopping after buffered samples are saved.', 'trial_id': trial['id']}


@app.get('/api/csi/trials/{trial_id}/export')
async def export_csi_trial(trial_id: int):
    active = app.state.runtime.csi_trial
    if active and active['id'] == trial_id:
        raise HTTPException(409, 'Stop the active trial and wait for it to finish before downloading.')
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM csi_trials WHERE id=?', (trial_id,)) as cursor:
            trial = await cursor.fetchone()
        if trial is None:
            raise HTTPException(404, 'CSI trial not found')
        async with db.execute('SELECT COUNT(*) FROM csi_trial_samples WHERE trial_id=?', (trial_id,)) as cursor:
            count = (await cursor.fetchone())[0]
    if count == 0:
        raise HTTPException(409, 'This trial has no CSI frames to export.')

    async def lines():
        yield json.dumps({'record_type': 'metadata', 'schema': 'wiwave-csi-amplitude-v1',
                          **dict(trial), 'source': 'esp32_csi', 'amplitude_units': 'hypot(I,Q), device-dependent',
                          'note': 'CSI magnitude vectors only; phase and raw signed I/Q were not captured.'}, allow_nan=False) + '\n'
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute('SELECT timestamp,sequence,label,rssi_dbm,channel,subcarrier_count,amplitudes,truncated FROM csi_trial_samples WHERE trial_id=? ORDER BY id', (trial_id,)) as cursor:
                async for row in cursor:
                    yield json.dumps({'record_type': 'sample', 'timestamp': row[0], 'sequence': row[1],
                                      'label': row[2], 'rssi_dbm': row[3], 'channel': row[4],
                                      'subcarrier_count': row[5], 'amplitudes': json.loads(row[6]),
                                      'truncated': bool(row[7])}, allow_nan=False) + '\n'
    return StreamingResponse(lines(), media_type='application/x-ndjson',
                             headers={'Content-Disposition': f'attachment; filename=wiwave_csi_trial_{trial_id}.jsonl'})


@app.get('/api/csi/trials/{trial_id}/analysis')
async def analyse_csi_trial(trial_id: int):
    """Descriptive per-label statistics over stored amplitude frames. A one-way
    F-statistic per subcarrier shows how much labels differ; it is not a human
    detection result and carries no identity information."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT id FROM csi_trials WHERE id=?', (trial_id,)) as cursor:
            if await cursor.fetchone() is None:
                raise HTTPException(404, 'CSI trial not found')
        async with db.execute('SELECT label, amplitudes FROM csi_trial_samples WHERE trial_id=? ORDER BY id LIMIT 10000',
                              (trial_id,)) as cursor:
            rows = await cursor.fetchall()
    if not rows:
        raise HTTPException(409, 'This trial has no samples to analyse.')
    parsed = []
    for label, raw in rows:
        try:
            amplitudes = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(amplitudes, list) and amplitudes:
            parsed.append((label, np.asarray(amplitudes, dtype=float)))
    if not parsed:
        raise HTTPException(409, 'No parsable CSI frames in this trial.')
    lengths = {}
    for _, vector in parsed:
        lengths[len(vector)] = lengths.get(len(vector), 0) + 1
    length = max(lengths, key=lengths.get)
    frames = [(label, vector) for label, vector in parsed if len(vector) == length]
    by_label = {}
    for label, vector in frames:
        by_label.setdefault(label, []).append(vector)
    labels = []
    for label, vectors in by_label.items():
        stacked = np.stack(vectors)
        labels.append({'label': label, 'frames': len(vectors),
                       'mean_activity': round(float(np.mean(np.abs(np.diff(stacked, axis=0)))) if len(vectors) > 1 else 0.0, 4),
                       'mean_amplitudes': [round(float(value), 2)
                                           for value in stacked.mean(axis=0)[::max(1, length // 64)][:64]]})
    separation = None
    if len(by_label) >= 2:
        data = np.stack([vector for _, vector in frames])
        names = np.array([label for label, _ in frames])
        groups = [data[names == name] for name in by_label]
        grand = data.mean(axis=0)
        between = sum(len(group) * (group.mean(axis=0) - grand) ** 2 for group in groups)
        within = sum(((group - group.mean(axis=0)) ** 2).sum(axis=0) for group in groups)
        with np.errstate(divide='ignore', invalid='ignore'):
            f_stats = (between / (len(groups) - 1)) / (within / (len(data) - len(groups)))
        f_stats = np.nan_to_num(f_stats, nan=0.0, posinf=0.0, neginf=0.0)
        order = np.argsort(f_stats)[::-1][:8]
        separation = {'max_f': round(float(f_stats.max()), 2), 'median_f': round(float(np.median(f_stats)), 2),
                      'top_subcarriers': [{'subcarrier': int(index), 'f_statistic': round(float(f_stats[index]), 2)}
                                          for index in order]}
    return {'trial_id': trial_id, 'subcarriers': length, 'frames_analyzed': len(frames),
            'labels': labels, 'separation': separation,
            'note': 'Descriptive statistics of stored amplitude frames. Differences between labels do not establish human detection.'}


@app.delete('/api/csi/trials/{trial_id}')
async def delete_csi_trial(trial_id: int):
    runtime = app.state.runtime
    if runtime.csi_trial and runtime.csi_trial['id'] == trial_id:
        raise HTTPException(409, 'Stop the active CSI trial before removing it.')
    async with runtime.db_lock:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('DELETE FROM csi_trial_samples WHERE trial_id=?', (trial_id,))
            result = await db.execute('DELETE FROM csi_trials WHERE id=?', (trial_id,))
            await db.commit()
            if result.rowcount == 0:
                raise HTTPException(404, 'CSI trial not found')
    return {'message': 'CSI trial and its local sample data were removed.'}


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


EVENT_SUMMARY_COLUMNS = ('id,started_at,ended_at,duration_s,peak_change_score,source,channel,baseline_dbm,neighbor_links,stop_reason')


@app.get('/api/events')
async def list_events(limit: int = Query(50, ge=1, le=200)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f'SELECT {EVENT_SUMMARY_COLUMNS} FROM events ORDER BY id DESC LIMIT ?', (limit,)) as cursor:
            return {'events': [dict(row) for row in await cursor.fetchall()]}


@app.get('/api/events/{event_id}')
async def event_detail(event_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f'SELECT {EVENT_SUMMARY_COLUMNS},pre_frames,post_frames FROM events WHERE id=?', (event_id,)) as cursor:
            row = await cursor.fetchone()
    if row is None:
        raise HTTPException(404, 'Event not found')
    data = dict(row)
    data['pre_frames'] = json.loads(data['pre_frames'])
    data['post_frames'] = json.loads(data['post_frames'])
    return data


@app.delete('/api/events/{event_id}')
async def delete_event(event_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        result = await db.execute('DELETE FROM events WHERE id=?', (event_id,))
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(404, 'Event not found')
    return {'message': 'Event record removed.'}


class AlertSettings(BaseModel):
    enabled: bool


@app.get('/api/alerts')
async def get_alerts():
    return {'enabled': app.state.runtime.alerts_enabled,
            'note': 'Shows a Windows notification when a sustained signal change starts. Alerts are optional and local.'}


@app.post('/api/alerts')
async def set_alerts(settings: AlertSettings):
    runtime = app.state.runtime
    runtime.alerts_enabled = settings.enabled
    return {'enabled': runtime.alerts_enabled, 'message': 'Alerts enabled.' if settings.enabled else 'Alerts disabled.'}


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
