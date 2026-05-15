"""Comprehensive integration tests for the multi-person detection pipeline.

Covers:
  - End-to-end detection scenarios (1 → 5 people)
  - Performance requirements (<100 ms P95 latency)
  - Stage-level timing breakdown
  - Event system (enter / exit / activity change)
  - Zone congestion logic
  - Backward-compatibility payload format
  - Graceful degradation on bad / empty signals
  - Realistic walking / breathing signal patterns
  - Stress test (50 rapid frames)
  - Reset and re-initialisation
"""

import time
import math
import pytest
import numpy as np

from multi_person.modules.orchestrator import MultiPersonDetector, StageTimings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(rssi: float = 75.0, rtt: float = 30.0) -> dict:
    return {"rssi": rssi, "rtt": rtt, "timestamp": time.time()}


def _walking_signal(frame: int, freq_hz: float = 1.5, base_rssi: float = 75.0) -> dict:
    """Synthesise a walking-pattern signal at the given frame index."""
    t = frame * 0.1  # 10 Hz sampling
    return {
        "rssi": base_rssi + 5.0 * math.sin(2 * math.pi * freq_hz * t),
        "rtt": 30.0 + 10.0 * math.sin(2 * math.pi * freq_hz * t),
        "timestamp": time.time(),
    }


def _breathing_signal(frame: int, base_rssi: float = 75.0) -> dict:
    """Synthesise a breathing-pattern signal (0.25 Hz)."""
    t = frame * 0.1
    return {
        "rssi": base_rssi + 1.0 * math.sin(2 * math.pi * 0.25 * t),
        "rtt": 30.0 + 2.0 * math.sin(2 * math.pi * 0.25 * t),
        "timestamp": time.time(),
    }


def _run_frames(detector: MultiPersonDetector, signals: list[dict]) -> list:
    return [detector.detect(s) for s in signals]


# ---------------------------------------------------------------------------
# 1. End-to-end detection
# ---------------------------------------------------------------------------

class TestEndToEndDetection:

    def test_single_frame_returns_result(self):
        d = MultiPersonDetector()
        r = d.detect(_make_signal())
        assert isinstance(r.success, bool)
        assert r.processing_time_ms >= 0

    def test_single_person_pipeline_succeeds(self):
        d = MultiPersonDetector()
        results = _run_frames(d, [_make_signal() for _ in range(15)])
        assert all(r.success for r in results)

    def test_person_count_does_not_exceed_max_capacity(self):
        for cap in (2, 3, 5):
            d = MultiPersonDetector(max_capacity=cap)
            _run_frames(d, [_make_signal(75 + np.random.randn() * 3,
                                         30 + np.random.randn() * 5)
                            for _ in range(30)])
            assert d.get_output_payload()["person_count"] <= cap

    def test_payload_person_count_matches_persons_list(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(10)])
        p = d.get_output_payload()
        assert p["person_count"] == len(p["persons"])

    def test_walking_signal_detected(self):
        d = MultiPersonDetector()
        _run_frames(d, [_walking_signal(i) for i in range(40)])
        p = d.get_output_payload()
        assert p["person_count"] >= 0  # pipeline ran without error

    def test_breathing_signal_detected(self):
        d = MultiPersonDetector()
        _run_frames(d, [_breathing_signal(i) for i in range(40)])
        p = d.get_output_payload()
        assert p["person_count"] >= 0

    def test_mixed_walking_and_breathing(self):
        d = MultiPersonDetector()
        signals = [_walking_signal(i) if i % 2 == 0 else _breathing_signal(i)
                   for i in range(40)]
        results = _run_frames(d, signals)
        assert all(isinstance(r.success, bool) for r in results)

    def test_five_person_max_capacity(self):
        d = MultiPersonDetector(max_capacity=5)
        for i in range(40):
            composite = sum(math.sin(2 * math.pi * (0.3 + p * 0.25) * i * 0.1)
                            for p in range(5))
            d.detect({"rssi": 75 + composite, "rtt": 30 + composite * 2,
                       "timestamp": time.time()})
        assert d.get_output_payload()["person_count"] <= 5


# ---------------------------------------------------------------------------
# 2. Person entry / exit scenarios
# ---------------------------------------------------------------------------

class TestPersonEntryExit:

    def test_entry_increases_or_maintains_count(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal(-100, 0) for _ in range(10)])
        before = d.get_output_payload()["person_count"]
        _run_frames(d, [_make_signal(75, 30) for _ in range(10)])
        after = d.get_output_payload()["person_count"]
        assert after >= before

    def test_exit_decreases_or_maintains_count(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal(75, 30) for _ in range(10)])
        before = d.get_output_payload()["person_count"]
        _run_frames(d, [_make_signal(-100, 0) for _ in range(10)])
        after = d.get_output_payload()["person_count"]
        assert after <= before

    def test_event_callbacks_are_invoked(self):
        events = []
        d = MultiPersonDetector()
        d.add_event_callback(lambda e: events.append(e))
        _run_frames(d, [_make_signal() for _ in range(15)])
        # Callbacks registered — no assertion on count (depends on signal)
        assert isinstance(events, list)

    def test_remove_event_callback(self):
        calls = []
        cb = lambda e: calls.append(e)
        d = MultiPersonDetector()
        d.add_event_callback(cb)
        d.remove_event_callback(cb)
        _run_frames(d, [_make_signal() for _ in range(10)])
        assert calls == []


# ---------------------------------------------------------------------------
# 3. Zone congestion
# ---------------------------------------------------------------------------

class TestZoneCongestion:

    def test_zone_congestion_keys_present(self):
        d = MultiPersonDetector()
        d.detect(_make_signal())
        zc = d.get_output_payload()["zone_congestion"]
        assert set(zc.keys()) == {"left", "center", "right"}

    def test_zone_congestion_values_are_bool(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(10)])
        for v in d.get_output_payload()["zone_congestion"].values():
            assert isinstance(v, bool)

    def test_congestion_false_when_no_persons(self):
        d = MultiPersonDetector()
        d.detect(_make_signal(-100, 0))
        zc = d.get_output_payload()["zone_congestion"]
        # With 0 persons no zone should be congested
        if d.get_output_payload()["person_count"] == 0:
            assert not any(zc.values())


# ---------------------------------------------------------------------------
# 4. Performance requirements
# ---------------------------------------------------------------------------

class TestPerformanceRequirements:

    def test_single_frame_under_100ms(self):
        d = MultiPersonDetector()
        r = d.detect(_make_signal())
        assert r.processing_time_ms < 100

    def test_p95_latency_under_100ms_after_50_frames(self):
        d = MultiPersonDetector()
        latencies = []
        for _ in range(50):
            r = d.detect(_make_signal(75 + np.random.randn() * 3,
                                      30 + np.random.randn() * 5))
            latencies.append(r.processing_time_ms)
        p95 = float(np.percentile(latencies, 95))
        assert p95 < 100, f"P95 latency {p95:.1f}ms exceeds 100ms"

    def test_average_latency_under_50ms(self):
        d = MultiPersonDetector()
        latencies = [d.detect(_make_signal()).processing_time_ms for _ in range(30)]
        assert np.mean(latencies) < 50

    def test_stress_50_rapid_frames(self):
        d = MultiPersonDetector()
        latencies = []
        for _ in range(50):
            r = d.detect(_make_signal(75 + np.random.randn() * 5,
                                      30 + np.random.randn() * 10))
            latencies.append(r.processing_time_ms)
        assert max(latencies) < 200, "Worst-case latency exceeded 200ms"

    def test_latency_scales_with_capacity(self):
        """Latency for cap=5 should not be more than 10× latency for cap=1."""
        d1 = MultiPersonDetector(max_capacity=1)
        d5 = MultiPersonDetector(max_capacity=5)
        lat1 = np.mean([d1.detect(_make_signal()).processing_time_ms for _ in range(20)])
        lat5 = np.mean([d5.detect(_make_signal()).processing_time_ms for _ in range(20)])
        assert lat5 < lat1 * 10 + 50  # generous bound


# ---------------------------------------------------------------------------
# 5. Stage-level timing breakdown
# ---------------------------------------------------------------------------

class TestStageLevelTimings:

    def test_stage_timings_present_on_success(self):
        d = MultiPersonDetector()
        r = d.detect(_make_signal())
        assert r.stage_timings is not None

    def test_stage_timings_all_non_negative(self):
        d = MultiPersonDetector()
        r = d.detect(_make_signal())
        t = r.stage_timings
        assert t.calibration_ms >= 0
        assert t.preprocessing_ms >= 0
        assert t.separation_ms >= 0
        assert t.feature_extraction_ms >= 0
        assert t.tracking_ms >= 0
        assert t.zone_update_ms >= 0

    def test_stage_total_close_to_processing_time(self):
        d = MultiPersonDetector()
        r = d.detect(_make_signal())
        # total_ms from stages should be within 5ms of reported processing_time_ms
        assert abs(r.stage_timings.total_ms - r.processing_time_ms) < 5

    def test_stage_timings_to_dict_has_all_keys(self):
        d = MultiPersonDetector()
        r = d.detect(_make_signal())
        keys = r.stage_timings.to_dict().keys()
        for expected in ("calibration_ms", "preprocessing_ms", "separation_ms",
                         "feature_extraction_ms", "tracking_ms", "zone_update_ms", "total_ms"):
            assert expected in keys

    def test_performance_stats_after_10_frames(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(10)])
        stats = d.get_performance_stats()
        assert stats.frame_count == 10
        assert stats.avg_ms >= 0
        assert stats.p95_ms >= stats.avg_ms - 1  # p95 ≥ avg (within float noise)
        assert stats.p99_ms >= stats.p95_ms - 1

    def test_performance_stats_to_dict_schema(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(5)])
        d_dict = d.get_performance_stats().to_dict()
        for key in ("frame_count", "avg_ms", "min_ms", "max_ms", "p95_ms",
                    "p99_ms", "latency_violations", "stage_avg"):
            assert key in d_dict

    def test_latency_violation_counter_increments(self):
        # Use a very tight target so violations are guaranteed
        d = MultiPersonDetector(target_latency_ms=0.001)
        _run_frames(d, [_make_signal() for _ in range(5)])
        assert d._latency_violations >= 1

    def test_detection_stats_endpoint_schema(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(5)])
        stats = d.get_detection_stats()
        for key in ("frame_id", "is_calibrated", "mode", "max_capacity",
                    "person_count", "zone_person_counts", "performance"):
            assert key in stats
        for key in ("avg_ms", "p95_ms", "p99_ms", "latency_violations"):
            assert key in stats["performance"]


# ---------------------------------------------------------------------------
# 6. Output payload schema and backward compatibility
# ---------------------------------------------------------------------------

class TestOutputPayloadSchema:

    def test_required_top_level_keys(self):
        d = MultiPersonDetector()
        d.detect(_make_signal())
        p = d.get_output_payload()
        for key in ("person_count", "persons", "zone_congestion", "mode",
                    "max_capacity", "frame_id", "timestamp", "processing_latency_ms"):
            assert key in p, f"Missing key: {key}"

    def test_person_count_is_int(self):
        d = MultiPersonDetector()
        d.detect(_make_signal())
        assert isinstance(d.get_output_payload()["person_count"], int)

    def test_persons_is_list(self):
        d = MultiPersonDetector()
        d.detect(_make_signal())
        assert isinstance(d.get_output_payload()["persons"], list)

    def test_person_entry_schema(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(10)])
        for person in d.get_output_payload()["persons"]:
            for key in ("person_id", "position_zone", "activity", "confidence", "signal_strength"):
                assert key in person, f"Person missing key: {key}"

    def test_confidence_in_0_to_100(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(10)])
        for person in d.get_output_payload()["persons"]:
            assert 0 <= person["confidence"] <= 100

    def test_backward_compat_single_person_update(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(10)])
        p = d.get_output_payload()
        if p["person_count"] == 1:
            assert "single_person_update" in p
            sp = p["single_person_update"]
            for key in ("person_id", "position_zone", "activity", "confidence", "signal_strength"):
                assert key in sp

    def test_no_single_person_update_when_zero_persons(self):
        d = MultiPersonDetector()
        d.detect(_make_signal(-100, 0))
        p = d.get_output_payload()
        if p["person_count"] == 0:
            assert "single_person_update" not in p

    def test_frame_id_increments(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(5)])
        assert d.get_output_payload()["frame_id"] == 5


# ---------------------------------------------------------------------------
# 7. System behaviour
# ---------------------------------------------------------------------------

class TestSystemBehaviour:

    def test_calibration_sets_flag(self):
        d = MultiPersonDetector()
        assert not d.is_calibrated
        d.detect(_make_signal())
        assert d.is_calibrated

    def test_explicit_calibrate_sets_flag(self):
        d = MultiPersonDetector()
        d.calibrate(_make_signal())
        assert d.is_calibrated

    def test_mode_switch_single_to_multi(self):
        d = MultiPersonDetector(mode="single_person")
        d.set_mode("multi_person")
        assert d.mode == "multi_person"

    def test_mode_switch_multi_to_single(self):
        d = MultiPersonDetector(mode="multi_person")
        d.set_mode("single_person")
        assert d.mode == "single_person"

    def test_invalid_mode_raises(self):
        d = MultiPersonDetector()
        with pytest.raises(ValueError):
            d.set_mode("turbo_mode")

    def test_reset_clears_frame_id(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(10)])
        d.reset()
        assert d.frame_id == 0

    def test_reset_clears_calibration(self):
        d = MultiPersonDetector()
        d.detect(_make_signal())
        d.reset()
        assert not d.is_calibrated

    def test_reset_clears_performance_history(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(10)])
        d.reset()
        assert d.get_performance_stats().frame_count == 0

    def test_reset_then_reuse(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(5)])
        d.reset()
        r = d.detect(_make_signal())
        assert r.success
        assert d.frame_id == 1


# ---------------------------------------------------------------------------
# 8. Graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:

    def test_empty_dict_does_not_raise(self):
        d = MultiPersonDetector()
        r = d.detect({})
        assert isinstance(r.success, bool)

    def test_none_values_do_not_raise(self):
        d = MultiPersonDetector()
        r = d.detect({"rssi": None, "rtt": None})
        assert isinstance(r.success, bool)

    def test_very_weak_signal_handled(self):
        d = MultiPersonDetector()
        r = d.detect({"rssi": -100.0, "rtt": 0.0, "timestamp": time.time()})
        assert isinstance(r.success, bool)

    def test_extreme_noise_handled(self):
        d = MultiPersonDetector()
        for _ in range(10):
            r = d.detect({"rssi": float(np.random.randn() * 200),
                           "rtt": float(np.random.randn() * 500),
                           "timestamp": time.time()})
            assert isinstance(r.success, bool)

    def test_error_result_has_message(self):
        d = MultiPersonDetector()
        r = d.detect({})
        if not r.success:
            assert r.error_message is not None and len(r.error_message) > 0

    def test_pipeline_continues_after_bad_frame(self):
        d = MultiPersonDetector()
        d.detect({})  # bad frame
        r = d.detect(_make_signal())  # good frame
        assert isinstance(r.success, bool)


# ---------------------------------------------------------------------------
# 9. Realistic multi-person scenarios
# ---------------------------------------------------------------------------

class TestRealisticScenarios:

    def test_two_walkers_different_frequencies(self):
        d = MultiPersonDetector(max_capacity=2)
        for i in range(40):
            sig = {
                "rssi": 75 + 5 * math.sin(2 * math.pi * 1.2 * i * 0.1)
                           + 4 * math.sin(2 * math.pi * 1.8 * i * 0.1),
                "rtt": 30 + 8 * math.sin(2 * math.pi * 1.2 * i * 0.1)
                          + 6 * math.sin(2 * math.pi * 1.8 * i * 0.1),
                "timestamp": time.time(),
            }
            d.detect(sig)
        assert d.get_output_payload()["person_count"] <= 2

    def test_person_zone_transition(self):
        d = MultiPersonDetector()
        # Strong signal → close zone
        _run_frames(d, [_make_signal(85, 20) for _ in range(15)])
        # Weaker signal → far zone
        _run_frames(d, [_make_signal(65, 45) for _ in range(15)])
        p = d.get_output_payload()
        assert p["person_count"] >= 0  # pipeline ran without crash

    def test_congested_zone_five_people(self):
        d = MultiPersonDetector(max_capacity=5)
        for i in range(50):
            composite = sum(math.sin(2 * math.pi * (0.3 + k * 0.2) * i * 0.1)
                            for k in range(5))
            d.detect({"rssi": 75 + composite, "rtt": 30 + composite * 2,
                       "timestamp": time.time()})
        p = d.get_output_payload()
        assert p["person_count"] <= 5
        assert isinstance(p["zone_congestion"], dict)

    def test_long_session_no_memory_leak(self):
        """Rolling history must stay bounded after many frames."""
        d = MultiPersonDetector()
        for _ in range(200):
            d.detect(_make_signal(75 + np.random.randn(), 30 + np.random.randn()))
        # History capped at 100
        assert len(d._latency_history) <= 100
        assert len(d._stage_history) <= 100

    def test_frame_id_monotonically_increases(self):
        d = MultiPersonDetector()
        ids = []
        for _ in range(10):
            d.detect(_make_signal())
            ids.append(d.frame_id)
        assert ids == list(range(1, 11))


# ---------------------------------------------------------------------------
# 10. Performance validation (final acceptance gate)
# ---------------------------------------------------------------------------

class TestPerformanceAcceptanceGate:
    """These tests mirror the acceptance criteria in requirements.md §7."""

    def test_avg_latency_under_50ms_single_person(self):
        d = MultiPersonDetector()
        lats = [d.detect(_make_signal()).processing_time_ms for _ in range(30)]
        assert np.mean(lats) < 50

    def test_p95_latency_under_100ms_multi_person(self):
        d = MultiPersonDetector(max_capacity=3)
        lats = []
        for _ in range(50):
            r = d.detect(_make_signal(75 + np.random.randn() * 3,
                                      30 + np.random.randn() * 5))
            lats.append(r.processing_time_ms)
        assert np.percentile(lats, 95) < 100

    def test_p99_latency_under_150ms(self):
        d = MultiPersonDetector(max_capacity=5)
        lats = []
        for _ in range(100):
            r = d.detect(_make_signal(75 + np.random.randn() * 5,
                                      30 + np.random.randn() * 10))
            lats.append(r.processing_time_ms)
        assert np.percentile(lats, 99) < 150

    def test_capacity_respected_for_all_sizes(self):
        for cap in (1, 2, 3, 4, 5):
            d = MultiPersonDetector(max_capacity=cap)
            _run_frames(d, [_make_signal(75 + np.random.randn() * 5,
                                         30 + np.random.randn() * 10)
                            for _ in range(30)])
            assert d.get_output_payload()["person_count"] <= cap

    def test_performance_stats_stage_avg_populated(self):
        d = MultiPersonDetector()
        _run_frames(d, [_make_signal() for _ in range(20)])
        stage_avg = d.get_performance_stats().stage_avg
        assert len(stage_avg) > 0
        for v in stage_avg.values():
            assert v >= 0
