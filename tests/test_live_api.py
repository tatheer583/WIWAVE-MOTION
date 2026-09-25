"""Exercise actual HTTP, WebSocket, recording, and calibration endpoints."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import pytest
import websockets


@pytest.fixture(scope='module')
def live_server(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {**os.environ, 'WIWAVE_SOURCE': 'simulation', 'SIMULATION_MODE': 'true',
           'WIWAVE_DB_PATH': str(tmp_path_factory.mktemp('live-api') / 'sessions.db'),
           'WIWAVE_CALIBRATION_SECONDS': '5', 'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen([sys.executable, '-B', '-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', str(port)],
                               cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urlopen(base + '/api/health', timeout=1):
                    break
            except (URLError, OSError):
                if process.poll() is not None:
                    pytest.fail('Test server failed to start')
                time.sleep(0.1)
        else:
            pytest.fail('Test server startup timed out')
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


def request(base, path, method='GET', headers=None):
    with urlopen(Request(base + path, method=method, headers=headers or {}), timeout=3) as response:
        return response.read().decode()


def test_http_and_websocket_share_truthful_schema(live_server):
    data = json.loads(request(live_server, '/api/poll'))
    assert data['is_simulation'] is True
    assert data['person_count'] is None
    async def check():
        async with websockets.connect(live_server.replace('http', 'ws') + '/ws/radar') as socket:
            payloads = [json.loads(await asyncio.wait_for(socket.recv(), 2)) for _ in range(5)]
        assert all(p['distance'] is None and p['bpm'] is None for p in payloads)
        assert payloads[-1]['sequence'] > payloads[0]['sequence']
    asyncio.run(check())


def test_calibration_recording_and_csv(live_server):
    request(live_server, '/api/calibrate', 'POST')
    data = json.loads(request(live_server, '/api/poll'))
    assert data['learning_progress'] < 0.2
    session = json.loads(request(live_server, '/session/start?name=Acceptance', 'POST'))
    with pytest.raises(HTTPError) as conflict:
        request(live_server, '/session/start', 'POST')
    assert conflict.value.code == 409
    time.sleep(0.7)
    request(live_server, '/session/stop', 'POST')
    exported = request(live_server, f'/session/{session["session_id"]}/export')
    assert 'rssi_dbm' in exported
    assert 'simulation' in exported
    assert len(exported.splitlines()) > 1
    sessions = json.loads(request(live_server, '/sessions'))
    assert sessions[0]['name'] == 'Acceptance'
    assert sessions[0]['end_time'] is not None
    replay = json.loads(request(live_server, f'/session/{session["session_id"]}/frames'))
    assert replay['is_replay'] is True
    assert len(replay['frames']) >= 2
    assert all(frame['source'] == 'simulation' and frame['is_simulation'] for frame in replay['frames'])
    assert all(frame['person_count'] is None for frame in replay['frames'])
    bounded = json.loads(request(live_server, f'/session/{session["session_id"]}/frames?limit=1'))
    assert len(bounded['frames']) == 1
    assert bounded['truncated'] is True


def test_replay_validates_session_and_limits(live_server):
    for path, status in [('/session/999999/frames', 404), ('/session/1/frames?limit=10001', 422), ('/session/1/frames?limit=0', 422)]:
        with pytest.raises(HTTPError) as error:
            request(live_server, path)
        assert error.value.code == status


def test_unknown_api_is_404_and_controls_reject_other_origins(live_server):
    with pytest.raises(HTTPError) as missing:
        request(live_server, '/api/does-not-exist')
    assert missing.value.code == 404
    with pytest.raises(HTTPError) as denied:
        request(live_server, '/api/calibrate', 'POST', {'Origin': 'https://unrelated.example'})
    assert denied.value.code == 403
