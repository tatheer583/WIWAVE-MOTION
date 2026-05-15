"""Multi-person detection orchestrator module.

This module provides the main MultiPersonDetector class that integrates all
multi-person detection modules into a cohesive system for detecting and
tracking multiple people using Wi-Fi signal metadata (RSSI and RTT).

Architecture:
    Raw Signal
        → CalibrationModule   (baseline normalisation)
        → SignalProcessor     (FFT, feature extraction)
        → SignalSeparator     (jitter-based person separation)
        → PositionEstimator   (cross-viewpoint fusion, zone assignment)
        → ActivityRecognizer  (walking / breathing / still / gesture)
        → PersonTracker       (ID lifecycle, state history, events)
        → OutputPayload       (JSON for WebSocket broadcast)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Callable
from collections import defaultdict, deque

import numpy as np

from multi_person.core.models import PersonState, MultiPersonOutput, PersonStateEvent
from multi_person.modules.signal_processor import SignalProcessor, SignalFeatures
from multi_person.modules.signal_separator import SignalSeparator
from multi_person.modules.position_estimator import PositionEstimator, PositionZone
from multi_person.modules.activity_recognizer import ActivityRecognizer
from multi_person.modules.person_tracker import PersonTracker
from multi_person.modules.calibration_module import CalibrationModule, CalibrationParams

# ---------------------------------------------------------------------------
# Module-level logger — structured, named per module for easy filtering
# ---------------------------------------------------------------------------
logger = logging.getLogger("WiWave.MultiPerson.Orchestrator")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StageTimings:
    """Per-stage latency breakdown for a single detection frame."""
    calibration_ms: float = 0.0
    preprocessing_ms: float = 0.0
    separation_ms: float = 0.0
    feature_extraction_ms: float = 0.0
    tracking_ms: float = 0.0
    zone_update_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        return (
            self.calibration_ms
            + self.preprocessing_ms
            + self.separation_ms
            + self.feature_extraction_ms
            + self.tracking_ms
            + self.zone_update_ms
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "calibration_ms": round(self.calibration_ms, 3),
            "preprocessing_ms": round(self.preprocessing_ms, 3),
            "separation_ms": round(self.separation_ms, 3),
            "feature_extraction_ms": round(self.feature_extraction_ms, 3),
            "tracking_ms": round(self.tracking_ms, 3),
            "zone_update_ms": round(self.zone_update_ms, 3),
            "total_ms": round(self.total_ms, 3),
        }


@dataclass
class DetectionResult:
    """Result of a single multi-person detection cycle."""
    success: bool
    persons: list[PersonState]
    processing_time_ms: float
    stage_timings: Optional[StageTimings] = None
    error_message: Optional[str] = None


@dataclass
class PerformanceStats:
    """Aggregated performance statistics over a rolling window."""
    frame_count: int
    avg_ms: float
    min_ms: float
    max_ms: float
    p95_ms: float
    p99_ms: float
    latency_violations: int          # frames that exceeded target_latency_ms
    stage_avg: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_count": self.frame_count,
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "latency_violations": self.latency_violations,
            "stage_avg": {k: round(v, 3) for k, v in self.stage_avg.items()},
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class MultiPersonDetector:
    """Main orchestrator for multi-person Wi-Fi motion detection.

    Integrates all detection modules into a single, observable pipeline with:
    - Per-stage latency profiling
    - Rolling performance history (last 100 frames)
    - Structured logging at every pipeline stage
    - Graceful degradation on signal failure
    - Backward-compatible single-person output format
    """

    # Maximum frames kept in the rolling performance history
    _PERF_HISTORY_SIZE = 100

    def __init__(
        self,
        signal_processor: Optional[SignalProcessor] = None,
        signal_separator: Optional[SignalSeparator] = None,
        position_estimator: Optional[PositionEstimator] = None,
        activity_recognizer: Optional[ActivityRecognizer] = None,
        person_tracker: Optional[PersonTracker] = None,
        calibration_module: Optional[CalibrationModule] = None,
        max_capacity: int = 5,
        mode: str = "multi_person",
        target_latency_ms: float = 100.0,
    ):
        # ── Module wiring ──────────────────────────────────────────────────
        self.signal_processor = signal_processor or SignalProcessor()
        self.signal_separator = signal_separator or SignalSeparator(self.signal_processor)
        self.position_estimator = position_estimator or PositionEstimator(
            self.signal_processor, self.signal_separator
        )
        self.activity_recognizer = activity_recognizer or ActivityRecognizer(self.signal_processor)
        self.person_tracker = person_tracker or PersonTracker(
            self.signal_processor, self.signal_separator,
            self.position_estimator, self.activity_recognizer,
        )
        self.calibration_module = calibration_module or CalibrationModule(self.signal_processor)

        # ── Configuration ──────────────────────────────────────────────────
        self.max_capacity = max_capacity
        self.mode = mode
        self.target_latency_ms = target_latency_ms

        # ── Runtime state ──────────────────────────────────────────────────
        self.frame_id: int = 0
        self.last_detection_time: Optional[float] = None
        self.is_calibrated: bool = False
        self.zone_person_counts: dict[str, int] = defaultdict(int)

        # ── Performance history (rolling deques for O(1) append/pop) ───────
        self._latency_history: deque[float] = deque(maxlen=self._PERF_HISTORY_SIZE)
        self._stage_history: deque[StageTimings] = deque(maxlen=self._PERF_HISTORY_SIZE)
        self._latency_violations: int = 0

        # ── Event callbacks ────────────────────────────────────────────────
        self.event_callbacks: list[Callable[[PersonStateEvent], None]] = []

        logger.info(
            "MultiPersonDetector initialised | mode=%s max_capacity=%d target_latency=%.0fms",
            mode, max_capacity, target_latency_ms,
        )

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def detect(self, raw_signal: Any) -> DetectionResult:
        """Run the full detection pipeline on one frame of raw Wi-Fi data.

        Pipeline stages (each timed independently):
            1. Calibration   — first-frame baseline learning
            2. Preprocessing — normalisation, outlier removal
            3. Separation    — jitter-based multi-person splitting
            4. Features      — FFT energy extraction per separated signal
            5. Tracking      — ID assignment, state update, event emission
            6. Zone update   — congestion map refresh

        Args:
            raw_signal: Dict with at minimum ``rssi`` and ``rtt`` keys.

        Returns:
            DetectionResult with persons, per-stage timings, and latency.
        """
        pipeline_start = time.perf_counter()
        timings = StageTimings()

        try:
            # Normalise scalar RSSI/RTT values into single-element lists so
            # downstream modules that call len() on them don't crash.
            raw_signal = self._normalise_signal(raw_signal)

            # ── Stage 1: Calibration ───────────────────────────────────────
            t0 = time.perf_counter()
            if not self.is_calibrated:
                self.calibration_module.calibrate(raw_signal)
                self.is_calibrated = True
                logger.debug("[frame=%d] Calibration complete", self.frame_id)
            timings.calibration_ms = (time.perf_counter() - t0) * 1000

            # ── Stage 2: Preprocessing ─────────────────────────────────────
            t0 = time.perf_counter()
            preprocessed = self.signal_processor.preprocess_signal(raw_signal)
            rtt = preprocessed.get("rtt", [])
            timings.preprocessing_ms = (time.perf_counter() - t0) * 1000

            if len(rtt) == 0:
                logger.warning("[frame=%d] Empty RTT after preprocessing — skipping frame", self.frame_id)
                return DetectionResult(
                    success=False,
                    persons=[],
                    processing_time_ms=0.0,
                    stage_timings=timings,
                    error_message="No valid signal data after preprocessing",
                )

            # ── Stage 3: Signal separation ─────────────────────────────────
            t0 = time.perf_counter()
            separated = self.signal_separator.separate_signals(raw_signal)
            if self.mode == "single_person" or len(separated) == 0:
                separated = [preprocessed]
            separated = separated[: self.max_capacity]
            timings.separation_ms = (time.perf_counter() - t0) * 1000
            logger.debug(
                "[frame=%d] Separated into %d signal(s) | mode=%s",
                self.frame_id, len(separated), self.mode,
            )

            # ── Stage 4: Feature extraction + position + activity ──────────
            t0 = time.perf_counter()
            positions, activities, signal_strengths, confidences = [], [], [], []

            for sig in separated:
                features = self.signal_processor.extract_features(sig)
                positions.append(self.position_estimator.estimate_position(sig))
                activities.append(self.activity_recognizer.recognize_activity(sig))
                signal_strengths.append(
                    float(features.rssi_mean) if features.rssi_mean is not None else -70.0
                )
                confidences.append(self._calculate_confidence(features, sig))

            timings.feature_extraction_ms = (time.perf_counter() - t0) * 1000

            # ── Stage 5: Person tracking ───────────────────────────────────
            t0 = time.perf_counter()
            tracked = self.person_tracker.track_persons(
                current_positions=positions,
                current_activities=activities,
                current_signal_strengths=signal_strengths,
                current_confidences=confidences,
            )
            persons = self._build_person_states(
                tracked, positions, activities, signal_strengths, confidences
            )
            timings.tracking_ms = (time.perf_counter() - t0) * 1000

            # ── Stage 6: Zone update ───────────────────────────────────────
            t0 = time.perf_counter()
            self._update_zones(positions)
            timings.zone_update_ms = (time.perf_counter() - t0) * 1000

            # ── Bookkeeping ────────────────────────────────────────────────
            total_ms = (time.perf_counter() - pipeline_start) * 1000
            self._record_performance(total_ms, timings)
            self.frame_id += 1
            self.last_detection_time = time.time()

            if total_ms > self.target_latency_ms:
                self._latency_violations += 1
                logger.warning(
                    "[frame=%d] Latency violation: %.1fms > %.0fms target | stages=%s",
                    self.frame_id, total_ms, self.target_latency_ms,
                    timings.to_dict(),
                )
            else:
                logger.debug(
                    "[frame=%d] Detection OK | persons=%d latency=%.1fms",
                    self.frame_id, len(persons), total_ms,
                )

            return DetectionResult(
                success=True,
                persons=persons,
                processing_time_ms=total_ms,
                stage_timings=timings,
            )

        except Exception as exc:
            total_ms = (time.perf_counter() - pipeline_start) * 1000
            logger.error(
                "[frame=%d] Pipeline error after %.1fms: %s",
                self.frame_id, total_ms, exc, exc_info=True,
            )
            return DetectionResult(
                success=False,
                persons=[],
                processing_time_ms=total_ms,
                stage_timings=timings,
                error_message=str(exc),
            )

    def get_output_payload(self) -> dict[str, Any]:
        """Build the JSON payload broadcast to WebSocket clients.

        Returns:
            Dict with person_count, persons[], zone_congestion, mode,
            processing_latency_ms, frame_id, timestamp, and (when N=1)
            a single_person_update field for backward compatibility.
        """
        person_states = self.person_tracker.get_all_person_states()

        persons = [
            {
                "person_id": pid,
                "position_zone": self.position_estimator.get_position_zone(state["position"]),
                "activity": state["activity"],
                "confidence": round(state["confidence"] * 100, 1),
                "signal_strength": state["signal_strength"],
            }
            for pid, state in person_states.items()
        ]

        zone_congestion = {
            zone: self.zone_person_counts.get(zone, 0) >= 2
            for zone in ("left", "center", "right")
        }

        perf = self.get_performance_stats()

        payload: dict[str, Any] = {
            "person_count": len(persons),
            "max_capacity": self.max_capacity,
            "mode": self.mode,
            "processing_latency_ms": perf.avg_ms,
            "zone_congestion": zone_congestion,
            "persons": persons,
            "frame_id": self.frame_id,
            "timestamp": self.last_detection_time or time.time(),
        }

        if len(persons) == 1:
            p = persons[0]
            payload["single_person_update"] = {
                "person_id": p["person_id"],
                "position_zone": p["position_zone"],
                "activity": p["activity"],
                "confidence": p["confidence"],
                "signal_strength": p["signal_strength"],
            }

        return payload

    def get_performance_stats(self) -> PerformanceStats:
        """Return aggregated performance statistics over the rolling window.

        Returns:
            PerformanceStats with avg/min/max/p95/p99 latency, violation
            count, and per-stage averages.
        """
        if not self._latency_history:
            return PerformanceStats(
                frame_count=0, avg_ms=0.0, min_ms=0.0, max_ms=0.0,
                p95_ms=0.0, p99_ms=0.0, latency_violations=0,
            )

        arr = np.array(self._latency_history)

        # Per-stage averages
        stage_avg: dict[str, float] = {}
        if self._stage_history:
            for key in ("calibration_ms", "preprocessing_ms", "separation_ms",
                        "feature_extraction_ms", "tracking_ms", "zone_update_ms"):
                stage_avg[key] = float(np.mean([getattr(s, key) for s in self._stage_history]))

        return PerformanceStats(
            frame_count=len(arr),
            avg_ms=float(np.mean(arr)),
            min_ms=float(np.min(arr)),
            max_ms=float(np.max(arr)),
            p95_ms=float(np.percentile(arr, 95)),
            p99_ms=float(np.percentile(arr, 99)),
            latency_violations=self._latency_violations,
            stage_avg=stage_avg,
        )

    def get_detection_stats(self) -> dict[str, Any]:
        """Return a combined stats dict for the /api/multi-person/stats endpoint."""
        perf = self.get_performance_stats()
        return {
            "frame_id": self.frame_id,
            "is_calibrated": self.is_calibrated,
            "mode": self.mode,
            "max_capacity": self.max_capacity,
            "person_count": self.person_tracker.get_person_count(),
            "zone_person_counts": dict(self.zone_person_counts),
            "performance": perf.to_dict(),
        }

    def calibrate(self, reference_signal: Any) -> dict[str, Any]:
        """Perform explicit calibration with a reference signal."""
        result = self.calibration_module.calibrate(self._normalise_signal(reference_signal))
        self.is_calibrated = True
        logger.info("Manual calibration complete")
        return result

    def apply_calibration(self, signal: Any) -> dict[str, Any]:
        """Apply stored calibration parameters to a signal."""
        return self.calibration_module.apply_calibration(signal)

    def set_mode(self, mode: str) -> None:
        """Switch detection mode at runtime.

        Args:
            mode: ``"single_person"`` or ``"multi_person"``

        Raises:
            ValueError: If mode is not one of the accepted values.
        """
        if mode not in ("single_person", "multi_person"):
            raise ValueError(f"Invalid mode '{mode}'. Use 'single_person' or 'multi_person'.")
        old = self.mode
        self.mode = mode
        logger.info("Mode switched: %s → %s", old, mode)

    def add_event_callback(self, callback: Callable[[PersonStateEvent], None]) -> None:
        """Register a callback invoked on every PersonStateEvent."""
        self.event_callbacks.append(callback)
        self.person_tracker.add_event_callback(callback)
        self.activity_recognizer.add_event_callback(callback)

    def remove_event_callback(self, callback: Callable[[PersonStateEvent], None]) -> None:
        """Deregister a previously registered callback."""
        if callback in self.event_callbacks:
            self.event_callbacks.remove(callback)
        self.person_tracker.remove_event_callback(callback)
        self.activity_recognizer.remove_event_callback(callback)

    def reset(self) -> None:
        """Reset all module state and performance history."""
        self.frame_id = 0
        self.last_detection_time = None
        self.is_calibrated = False
        self.zone_person_counts = defaultdict(int)
        self._latency_history.clear()
        self._stage_history.clear()
        self._latency_violations = 0

        self.signal_processor.reset()
        self.signal_separator.reset()
        self.position_estimator.reset()
        self.activity_recognizer.reset()
        self.person_tracker.reset()
        self.calibration_module.reset()

        logger.info("MultiPersonDetector reset complete")

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _calculate_confidence(self, features: SignalFeatures, signal: dict[str, Any]) -> float:
        """Compute a [0, 1] confidence score from signal quality indicators."""
        confidence = 1.0

        rssi = features.rssi_mean or 0.0
        if rssi < -90:
            confidence *= 0.5
        elif rssi < -80:
            confidence *= 0.7

        total_energy = (features.breathing_energy or 0.0) + (features.walking_energy or 0.0)
        if total_energy < 0.01:
            confidence *= 0.8

        if (features.rtt_std or 0.0) > 0.2:
            confidence *= 0.85

        return max(0.0, min(1.0, confidence))

    def _update_zones(self, positions: list[tuple[float, float]]) -> None:
        """Rebuild the zone → person-count map from current positions."""
        self.zone_person_counts = defaultdict(int)
        for pos in positions:
            zone = self.position_estimator.get_position_zone(pos)
            self.zone_person_counts[zone] += 1

    def _build_person_states(
        self,
        tracked: dict[int, dict[str, Any]],
        positions: list[tuple[float, float]],
        activities: list[str],
        signal_strengths: list[float],
        confidences: list[float],
    ) -> list[PersonState]:
        """Construct PersonState objects from tracker output and per-signal data."""
        persons = []
        now = time.time()

        for person_id, _ in tracked.items():
            idx = person_id - 1  # IDs are 1-based
            position = positions[idx] if idx < len(positions) else (0.0, 0.0)
            activity = activities[idx] if idx < len(activities) else "unknown"
            strength = signal_strengths[idx] if idx < len(signal_strengths) else -70.0
            confidence = confidences[idx] if idx < len(confidences) else 1.0

            persons.append(PersonState(
                person_id=person_id,
                position=position,
                activity=activity,
                timestamp=now,
                signal_features={
                    "signal_strength": strength,
                    "confidence": confidence,
                    "zone": self.position_estimator.get_position_zone(position),
                },
                velocity=None,
                confidence=confidence,
            ))

        return persons

    def _normalise_signal(self, raw_signal: Any) -> Any:
        """Wrap scalar RSSI / RTT values into single-element lists.

        Downstream modules call ``len()`` on these values, which raises a
        TypeError when they are plain Python floats or 0-d numpy arrays.
        """
        if not isinstance(raw_signal, dict):
            return raw_signal
        out = dict(raw_signal)
        for key in ("rssi", "rtt"):
            val = out.get(key)
            if val is None:
                out[key] = []
            elif isinstance(val, (int, float)):
                out[key] = [float(val)]
            # lists / arrays pass through unchanged
        return out

    def _record_performance(self, total_ms: float, timings: StageTimings) -> None:
        """Append a frame's latency and stage timings to the rolling history."""
        self._latency_history.append(total_ms)
        self._stage_history.append(timings)

    # ------------------------------------------------------------------
    # Backward-compatibility shim for old unit tests that access
    # detector.processing_times directly.
    # ------------------------------------------------------------------
    @property
    def processing_times(self) -> list[float]:
        return list(self._latency_history)
