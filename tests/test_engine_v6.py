"""Tests for the v6 engine: multi-link fusion, spectral statistics, event journal, alerts."""
import asyncio
import json
import math
import time

import pytest

import server
from sensing.detector import ChangeDetector
from sensing.spectral import SpectralAnalyzer
from sensing.sources import CsiDemoSource, create_source


def linked_sample(primary, neighbors, link_id='a', channel=6):
    return {'source': 'native_rssi', 'rssi_dbm': primary, 'link_id': link_id, 'channel': channel,
            'links': [{'bssid': f'n{i}', 'rssi_dbm': value} for i, value in enumerate(neighbors)]}


def calibrate_links(detector, primary=-50, neighbors=None, count=70):
    neighbors = neighbors if neighbors is not None else [-70, -72, -74, -76]
    result = None
    for i in range(count):
        result = detector.update(linked_sample(primary, neighbors), i / 10)
    return result


def test_primary_link_change_triggers():
    detector = ChangeDetector(5)
    calibrate_links(detector)
    for i in range(70, 110):
        result = detector.update(linked_sample(-40, [-70, -72, -74, -76]), i / 10)
    assert result['state'] == 'signal_change'
    assert result['link_change'][0] == 100.0
    assert all(value == 0.0 for value in result['link_change'][1:])


def test_single_noisy_neighbor_does_not_trigger():
    detector = ChangeDetector(5)
    calibrate_links(detector)
    for i in range(70, 120):
        result = detector.update(linked_sample(-50, [-25, -72, -74, -76]), i / 10)
    assert result['state'] == 'quiet'
    assert result['event_count'] == 0


def test_majority_neighbor_change_triggers():
    detector = ChangeDetector(5)
    calibrate_links(detector)
    for i in range(70, 120):
        result = detector.update(linked_sample(-50, [-60, -61, -62, -76]), i / 10)
    assert result['state'] == 'signal_change'


def test_neighbor_set_size_change_resets_baseline():
    detector = ChangeDetector(5)
    calibrate_links(detector)
    result = detector.update(linked_sample(-50, [-70, -72, -74]), 7.1)
    assert result['state'] == 'calibrating'


def test_csi_detector_unchanged_by_links_code():
    detector = ChangeDetector(5)
    for i in range(70):
        result = detector.update({'source': 'esp32_csi', 'amplitudes': [10 + 0.1 * math.sin(i)] * 32}, i / 10)
    assert result['state'] == 'quiet'
    assert result.get('link_change') is None


def test_spectral_finds_sine_in_band():
    analyzer = SpectralAnalyzer(rate_hz=10)
    stats = None
    for i in range(320):
        stats = analyzer.update(i / 10, -50 + 3 * math.sin(2 * math.pi * 0.3 * i / 10))
    assert stats is not None
    assert stats['slow_oscillation'] > 0.6
    assert 0.2 <= stats['dominant_hz'] <= 0.45


def test_spectral_fast_burst_in_fast_band():
    analyzer = SpectralAnalyzer(rate_hz=10)
    stats = None
    for i in range(320):
        stats = analyzer.update(i / 10, -50 + 2.5 * math.sin(2 * math.pi * 2.5 * i / 10))
    assert stats['fast_activity'] > 0.5


def test_spectral_waits_for_minimum_window():
    analyzer = SpectralAnalyzer(rate_hz=10)
    for i in range(50):
        assert analyzer.update(i / 10, -50) is None


def test_csi_demo_source_is_labelled_synthetic():
    source = CsiDemoSource()
    sample = source.read()
    assert source.source == 'csi_simulation'
    assert len(sample['amplitudes']) == 52
    assert all(value > 0 for value in sample['amplitudes'])


def test_csi_simulation_source_selectable(monkeypatch):
    monkeypatch.setenv('WIWAVE_SOURCE', 'csi_simulation')
    source = create_source()
    assert source.source == 'csi_simulation'


class FakeSource:
    source = 'native_rssi'

    def read(self):
        return {'source': 'native_rssi', 'rssi_dbm': -50, 'link_id': 'a', 'channel': 6, 'links': []}

    def close(self):
        pass


class FakeCsiSource:
    source = 'esp32_csi'

    def read(self):
        return {'source': 'esp32_csi', 'rssi_dbm': -50, 'link_id': 'esp', 'channel': 6,
                'amplitudes': [10.0 + i for i in range(128)]}

    def close(self):
        pass


def detection(state='quiet', score=0.0, motion=False):
    return {'state': state, 'change_score': score, 'motion_detected': motion,
            'learning_progress': 1.0, 'read_rate_hz': 10, 'event_count': 0, 'baseline_rssi_dbm': -50}


def build_runtime(source=None):
    runtime = server.Runtime(source or FakeSource())
    runtime.latest = {'state': 'quiet', 'timestamp': server.utc_now(), 'rssi_dbm': -50,
                      'channel': 6, 'links': []}
    return runtime


def test_event_journal_records_transition():
    runtime = build_runtime()
    for step in range(5):
        runtime.observe_event(detection(), 1 + step / 10)
    runtime.observe_event(detection('signal_change', 40.0, True), 2.0)
    for step in range(10):
        runtime.observe_event(detection('signal_change', 60.0, True), 2.1 + step / 10)
    runtime.observe_event(detection(), 5.0)
    assert runtime.pending_event is None
    assert not runtime.event_queue.empty()
    event = asyncio.run(runtime.event_queue.get())
    assert event['duration_s'] is not None
    assert event['peak_change_score'] == 60.0
    assert event['post_frames'], 'active frames after the trigger should be captured'


def test_event_journal_interrupts_on_sensor_failure():
    runtime = build_runtime()
    runtime.observe_event(detection('signal_change', 40.0, True), 1.0)
    runtime.error = 'adapter gone'
    runtime.interrupt_event()
    event = asyncio.run(runtime.event_queue.get())
    assert event['stop_reason'] == 'sensor_interrupted'


def test_events_api_roundtrip(tmp_path, monkeypatch):
    import sqlite3
    path = str(tmp_path / 'events.db')
    monkeypatch.setattr(server, 'DB_PATH', path)
    runtime = build_runtime()
    runtime.observe_event(detection(), 1.0)
    runtime.observe_event(detection('signal_change', 50.0, True), 2.0)
    for step in range(4):
        runtime.observe_event(detection('signal_change', 50.0, True), 2.2 + step / 10)
    runtime.observe_event(detection(), 4.0)
    event = asyncio.run(runtime.event_queue.get())

    async def flow():
        await server.init_db()
        await runtime.write_one_event(event)
        listing = await server.list_events(limit=10)
        assert len(listing['events']) == 1
        summary = listing['events'][0]
        assert summary['peak_change_score'] == 50.0
        detail = await server.event_detail(summary['id'])
        assert detail['pre_frames'] and detail['post_frames']
        message = await server.delete_event(summary['id'])
        assert 'removed' in message['message']
        with pytest.raises(server.HTTPException):
            await server.event_detail(summary['id'])
    asyncio.run(flow())


def test_alert_toggle():
    runtime = build_runtime()
    assert runtime.alerts_enabled is False
    runtime.alerts_enabled = True
    assert runtime.alerts_enabled is True


def test_csi_preview_downsampled_in_snapshot():
    runtime = build_runtime(FakeCsiSource())
    sample = runtime.source.read()
    detection = runtime.detector.update(sample, time.monotonic())
    runtime.latest = {k: v for k, v in sample.items() if k != 'amplitudes'}
    runtime.latest.update(detection, timestamp=server.utc_now())
    step = max(1, round(len(sample['amplitudes']) / 64))
    runtime.latest['csi_preview'] = [round(float(v), 2) for v in sample['amplitudes'][::step][:64]]
    runtime.last_received = time.monotonic()
    snapshot = runtime.snapshot()
    assert len(snapshot['csi_preview']) == 64
    assert snapshot['capabilities']['csi'] is True
    assert snapshot['capabilities']['human_detection'] is False


def test_csi_simulation_snapshot_marked_synthetic():
    runtime = build_runtime(CsiDemoSource())
    runtime.last_received = time.monotonic()
    snapshot = runtime.snapshot()
    assert snapshot['is_simulation'] is True
    assert snapshot['source'] == 'csi_simulation'


def test_spectral_stats_reach_snapshot():
    runtime = build_runtime()
    runtime.spectral = SpectralAnalyzer(rate_hz=10, minimum_seconds=1)
    stats = None
    now = time.monotonic()
    for i in range(60):
        stats = runtime.spectral.update(now + i / 10, -50 + math.sin(i / 10))
    runtime.latest['spectral'] = stats
    runtime.last_received = now + 0.5
    snapshot = runtime.snapshot()
    assert snapshot['spectral']['window_s'] >= 4
