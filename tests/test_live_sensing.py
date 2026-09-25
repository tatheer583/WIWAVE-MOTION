import asyncio
import csv
import io
import json
import math
import time
import pytest
from sensing.detector import ChangeDetector
from sensing.sources import EspCsiParser, SerialCsiSource, create_source
from server import Runtime


def reading(rssi=-50, **extra):
    return {'source': 'native_rssi', 'rssi_dbm': rssi, 'link_id': 'test-ap', 'channel': 7, **extra}


def calibrated():
    detector = ChangeDetector(calibration_seconds=5)
    for i in range(61):
        result = detector.update(reading(-50 + 0.2 * math.sin(i)), i / 10)
    assert result['state'] == 'quiet'
    return detector


def test_quiet_baseline_has_no_activity():
    detector = calibrated()
    for i in range(61, 160):
        result = detector.update(reading(-50 + 0.3 * math.sin(i)), i / 10)
    assert result['state'] == 'quiet'
    assert result['event_count'] == 0


def test_isolated_spike_cannot_trigger():
    detector = calibrated()
    results = [detector.update(reading(-25 if i == 80 else -50), i / 10) for i in range(61, 120)]
    assert all(not r['motion_detected'] for r in results)


def test_sustained_change_triggers_once_and_recovers():
    detector = calibrated()
    results = [detector.update(reading(-40), i / 10) for i in range(61, 110)]
    assert results[-1]['state'] == 'signal_change'
    assert results[-1]['event_count'] == 1
    for i in range(110, 175):
        result = detector.update(reading(), i / 10)
    assert result['state'] == 'quiet'
    assert result['event_count'] == 1


@pytest.mark.parametrize('change', [{'link_id': 'other-ap'}, {'channel': 11}])
def test_link_changes_reset_baseline(change):
    detector = calibrated()
    result = detector.update(reading(**change), 6.1)
    assert result['state'] == 'calibrating'
    assert result['learning_progress'] == 0


def test_long_gap_resets_baseline():
    detector = calibrated()
    assert detector.update(reading(), 15)['state'] == 'calibrating'


def test_duplicate_timestamps_rejected():
    detector = calibrated()
    with pytest.raises(ValueError, match='ordered'):
        detector.update(reading(), 6)


@pytest.mark.parametrize('value', [float('nan'), float('inf')])
def test_nonfinite_measurements_rejected(value):
    with pytest.raises(ValueError, match='finite'):
        ChangeDetector().update(reading(value), 1)


def test_elapsed_time_alone_does_not_finish_calibration():
    detector = ChangeDetector(calibration_seconds=5)
    for i in range(12):
        result = detector.update(reading(), i)
    assert result['learning_progress'] < 1
    assert result['state'] == 'calibrating'


def test_csi_common_gain_does_not_trigger_motion():
    detector = ChangeDetector(calibration_seconds=5)
    for i in range(120):
        gain = 1 if i < 65 else 2
        result = detector.update(reading(source='esp32_csi', amplitudes=[gain * (j + 5) for j in range(32)]), i / 10)
    assert result['state'] == 'quiet'


def csi_line(raw=None, first_word=0, seq=1):
    raw = [3, 4] * 32 if raw is None else raw
    output = io.StringIO()
    csv.writer(output).writerow(['CSI_DATA', seq, '00:11:22:33:44:55', -50, 7, len(raw), first_word, json.dumps(raw)])
    return output.getvalue()


def parser():
    instance = EspCsiParser()
    instance.parse('type,id,mac,rssi,channel,len,first_word,data')
    return instance


def test_csi_header_and_invalid_first_word():
    sample = parser().parse(csi_line(first_word=1))
    assert len(sample['amplitudes']) == 30
    assert sample['amplitudes'] == [5.0] * 30


def test_csi_duplicate_frame_ignored():
    instance = parser()
    assert instance.parse(csi_line()) is not None
    assert instance.parse(csi_line()) is None


def test_csi_corrupt_data_rejected():
    with pytest.raises(ValueError):
        parser().parse(csi_line([200, 0] * 32))
    with pytest.raises(ValueError, match='header'):
        EspCsiParser().parse(csi_line())


def test_serial_frame_split_across_reads_is_preserved(monkeypatch):
    import sys
    from types import SimpleNamespace
    row = csi_line().encode()
    chunks = iter([row[:15], row[15:]])
    monkeypatch.setitem(sys.modules, 'serial', SimpleNamespace(SerialException=OSError))
    source = SerialCsiSource('test', 115200)
    source.serial = SimpleNamespace(read_until=lambda *args, **kwargs: next(chunks))
    source.parser = parser()
    assert source.read() is None
    assert source.read()['amplitudes'] == [5.0] * 32


def test_legacy_recording_can_still_be_exported(tmp_path, monkeypatch):
    import sqlite3
    import server
    path = str(tmp_path / 'legacy.db')
    monkeypatch.setattr(server, 'DB_PATH', path)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sessions (id INTEGER PRIMARY KEY, start_time TEXT, end_time TEXT, name TEXT)')
        db.execute('INSERT INTO sessions VALUES (1, "2026-01-01", "2026-01-02", "old session")')
        db.execute('CREATE TABLE telemetry (id INTEGER PRIMARY KEY, session_id INTEGER, status TEXT)')
        db.execute('INSERT INTO telemetry VALUES (1, 1, "legacy measurement")')
    async def check():
        await server.init_db()
        response = await server.export_session(1)
        chunks = [chunk async for chunk in response.body_iterator]
        assert 'legacy measurement' in ''.join(chunks)
    asyncio.run(check())


def test_demo_requires_explicit_selection(monkeypatch):
    monkeypatch.delenv('SIMULATION_MODE', raising=False)
    monkeypatch.setenv('WIWAVE_SOURCE', 'invalid')
    monkeypatch.setenv('AUTO_SIM_FALLBACK', 'true')
    with pytest.raises(ValueError):
        create_source()


class SlowSource:
    source = 'native_rssi'

    def read(self):
        time.sleep(0.25)
        return reading()


def test_slow_reader_does_not_block_publisher():
    async def check():
        runtime = Runtime(SlowSource())
        queue = asyncio.Queue(maxsize=1)
        runtime.subscribers.add(queue)
        tasks = [asyncio.create_task(runtime.acquire()), asyncio.create_task(runtime.publish())]
        try:
            message = json.loads(await asyncio.wait_for(queue.get(), timeout=0.1))
            assert message['state'] == 'waiting'
            await asyncio.sleep(0.35)
            assert queue.qsize() == 1
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.run(check())


def test_stale_snapshot_clears_detection_and_never_invents_people():
    runtime = Runtime(SlowSource())
    runtime.latest = {'state': 'signal_change', 'motion_detected': True, 'rssi_dbm': -40}
    runtime.last_received = time.monotonic() - 10
    data = runtime.snapshot()
    assert data['state'] == 'stale'
    assert data['motion_detected'] is False
    assert data['rssi_dbm'] is None
    assert data['person_count'] is None
    assert data['distance'] is None
    assert data['capabilities']['human_detection'] is False
