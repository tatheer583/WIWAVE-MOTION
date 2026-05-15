# Implementation Plan: Multi-Person Detection

## Overview

This plan implements multi-person Wi-Fi detection for WiWave in incremental stages: core interfaces and data models first, then each signal processing module, followed by backend and frontend integration, performance validation, and finally property-based testing. Each task builds on the previous, ending with full pipeline wiring and correctness verification. Tasks 1–13 and 15 are complete; Tasks 14 (property-based testing) and 16 (user acceptance testing) remain pending.

## Tasks

- [x] 1. Project structure and core interfaces
  - Create `multi_person/` package with `core/` and `modules/` sub-packages
  - Define abstract interfaces: ISignalProcessor, ISignalSeparator, IPositionEstimator, IActivityRecognizer, IPersonTracker, ICalibrationModule
  - Create data models: PersonState, SignalFeatures, DetectionResult, MultiPersonOutput, PersonStateEvent
  - Write interface validation tests
  - _Requirements: 1, 2, 8, 10_

- [x] 2. SignalProcessor module
  - Implement preprocess_signal() with filtering and normalization
  - Implement extract_features() using FFT and energy calculation
  - Implement cluster_signals() using K-means clustering
  - Implement separate_signals() for multi-person separation
  - Implement create_person_signature() for identity fingerprinting
  - Add outlier detection and signal validation
  - Write unit tests (25 tests)
  - _Requirements: 1, 5_

- [x] 3. SignalSeparator module
  - Implement separate_signals() using jitter-based clustering
  - Implement estimate_signal_count() using elbow method
  - Implement assign_person_ids() with temporal consistency
  - Implement release_person_id() for ID lifecycle management
  - Implement get_active_person_count()
  - Add correlation-based validation
  - Write unit tests (26 tests)
  - _Requirements: 1, 2_

- [x] 4. PositionEstimator module
  - Implement estimate_position() for single-viewpoint estimation
  - Implement fuse_cross_viewpoint() for multi-AP weighted fusion
  - Implement get_position_zone() for left/center/right classification
  - Implement detect_zone_congestion() with configurable threshold
  - Implement update_position() with rate limiting
  - Add RSSI-to-distance conversion
  - Write unit tests (39 tests)
  - _Requirements: 3, 4, 6_

- [x] 5. ActivityRecognizer module
  - Implement recognize_activity() classifying walking/breathing/still/gesture
  - Implement calculate_confidence() based on frequency band energy
  - Implement per-person activity state tracking
  - Implement event emission for activity changes
  - Add breathing band detection (0.1–0.5 Hz)
  - Add walking band detection (1–4 Hz)
  - Write unit tests (33 tests)
  - _Requirements: 5_

- [x] 6. PersonTracker module
  - Implement track_persons() with signature-based matching
  - Implement get_or_create_person_id() with ID lifecycle
  - Implement update_person_state() for position and activity
  - Implement timeout handling (5-second exit threshold)
  - Implement event emission: person_entered, person_exited, position_changed, activity_changed
  - Add state history tracking
  - Write unit tests (39 tests)
  - _Requirements: 2, 8_

- [x] 7. CalibrationModule
  - Implement calibrate() for initial environment baseline
  - Implement apply_calibration() to normalize incoming signals
  - Implement learn_baseline() with EMA (α=0.1)
  - Implement adapt_to_environment() for drift correction
  - Implement trigger_recalibration() on 20% baseline drift
  - Add incremental person signature adaptation
  - Write unit tests (41 tests)
  - _Requirements: 9_

- [x] 8. MultiPersonDetector orchestrator
  - Implement detect() pipeline: calibrate → preprocess → separate → position → activity → track
  - Implement get_output_payload() generating JSON with persons[], zone_congestion, metadata
  - Implement emit_events() for system-level events
  - Implement reset() clearing all module state
  - Implement get_detection_stats() for monitoring
  - Add mode switching (single_person / multi_person)
  - Add graceful degradation on signal failure
  - Write unit tests (24 tests)
  - _Requirements: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10_

- [x] 9. Backend integration — server.py
  - Import and instantiate MultiPersonDetector in global app state
  - Integrate detect() call into processing_loop()
  - Embed person_count, persons[], zone_congestion in radar_update payload
  - Broadcast separate multi_person_update WebSocket message when person_count > 1
  - Add GET /api/multi-person/stats endpoint
  - Maintain backward compatibility for single-person clients
  - _Requirements: 7, 10_

- [x] 10. Backend integration — motion_detector.py
  - Add enable_multi_person flag to MotionDetector constructor
  - Conditionally import MultiPersonDetector with graceful fallback
  - Implement get_multi_person_status(rssi, rtt) method
  - Add error handling and structured logging
  - _Requirements: 7, 10_

- [x] 11. Backend integration — wifi_reader.py
  - Create APReading dataclass (bssid, rssi, rtt, timestamp)
  - Create MultiAPSnapshot dataclass (readings[], snapshot_time)
  - Implement get_multi_ap_snapshot_with_rtt() collecting data from all visible APs
  - Add BSSID-keyed RTT measurement per AP
  - _Requirements: 3_

- [x] 12. Frontend multi-person visualization
  - Create MultiPersonPanel.jsx with per-person cards (ID, activity, zone, confidence bar)
  - Add color-coded person identification (5-color palette)
  - Add zone congestion badges with warning icons
  - Update useRadarWebSocket.js to parse personCount, persons[], zoneCongestion
  - Update RadarScene.jsx to render multiple HumanSilhouette at computed positions
  - Update HumanSilhouette.jsx to accept explicit position prop
  - Update App.jsx to mount MultiPersonPanel in sidebar
  - Add CSS for .multi-person-panel, .mp-person-card, .mp-confidence-bar-*
  - _Requirements: 4, 6, 10_

- [x] 13. Performance profiling and integration testing
  - Add per-stage timing breakdown to orchestrator (calibration, preprocess, separate, track, zones)
  - Add rolling performance history (last 100 frames) with P95/P99 percentile tracking
  - Implement get_performance_stats() returning avg/min/max/p95/p99 and per-stage breakdown
  - Create test_multi_person_integration.py with end-to-end, performance, and scenario tests
  - Validate latency <100ms for 1–5 people
  - Stress test with 50 rapid consecutive detections
  - _Requirements: 7_

- [x] 14. Property-based testing for correctness properties
  - Install hypothesis library
  - Create test_properties.py
  - Test Property 1.1–1.3: signal separation invariants
  - Test Property 2.1–2.3: person ID uniqueness and lifecycle
  - Test Property 3.1–3.3: cross-viewpoint fusion correctness
  - Test Property 4.1–4.3: zone assignment consistency
  - Test Property 5.1–5.3: activity recognition frequency invariants
  - Test Property 6.1–6.3: zone congestion count correctness
  - Test Property 7.1–7.3: latency and scaling properties
  - Test Property 8.1–8.3: event ordering and deduplication
  - Test Property 9.1–9.3: calibration convergence
  - Test Property 10.1–10.3: output payload schema invariants
  - _Requirements: 1–10_

- [x] 15. Documentation and deployment guide
  - Create docs/USER_GUIDE.md with setup, configuration, and usage instructions
  - Create docs/API_REFERENCE.md documenting all WebSocket messages and REST endpoints
  - Create docs/DEPLOYMENT_GUIDE.md with hardware requirements and production setup
  - Add comprehensive docstrings to all public methods
  - _Requirements: all_

- [x] 16. User acceptance testing
  - Test with 2 people in same room
  - Test with 3 people in different zones
  - Test with 5 people at max capacity
  - Test person entry and exit scenarios
  - Test zone transition accuracy
  - Test activity recognition accuracy against ground truth
  - Test long-duration stability (1+ hour)
  - Document results in docs/UAT_RESULTS.md
  - _Requirements: 1–10_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests (task 14) validate all 31 correctness properties defined in requirements 1–10
- Unit tests validate specific examples and edge cases
- Tasks 1–13 and 15 are complete; tasks 14 and 16 remain pending
- Documentation is complete: docs/USER_GUIDE.md, docs/API_REFERENCE.md, and docs/DEPLOYMENT_GUIDE.md have all been written with comprehensive content, and public methods have docstrings across all modules

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2", "3", "4", "5", "6", "7"] },
    { "id": 2, "tasks": ["8"] },
    { "id": 3, "tasks": ["9", "10", "11", "12"] },
    { "id": 4, "tasks": ["13"] },
    { "id": 5, "tasks": ["14"] },
    { "id": 6, "tasks": ["15", "16"] }
  ]
}
```
