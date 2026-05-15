# Requirements: Multi-Person Detection for WiWave

## Introduction

This document specifies the requirements for adding multi-person detection capabilities to the WiWave Wi-Fi motion detection system. The feature will enable simultaneous detection and tracking of 2-5 people in the same or different rooms using Wi-Fi signal analysis (RSSI and RTT).

## Glossary

- **RSSI**: Received Signal Strength Indicator - measures signal power
- **RTT**: Round-Trip Time - measures signal propagation delay
- **AP**: Access Point - Wi-Fi router or access point
- **FFT**: Fast Fourier Transform - frequency domain analysis
- **Jitter**: Variance in RTT measurements
- **Cross-viewpoint fusion**: Combining data from multiple APs for better accuracy
- **Zone**: Spatial region (left/center/right) where a person is located
- **Person ID**: Unique identifier assigned to each detected person
- **Activity**: Classification of person's movement (walking/breathing/still/gesture)

---

## Requirement 1: Multi-Person Signal Separation

**User Story**: As a system operator, I want the system to separate Wi-Fi signals from multiple people, so that each person can be tracked independently.

### Acceptance Criteria

1. WHERE the system receives RTT measurements, WHEN multiple people are present, THE system SHALL separate individual signal components using jitter-based clustering
2. WHERE signal separation is performed, THE system SHALL maintain a minimum separation accuracy of 80% for 2-3 people
3. WHERE more than 3 people are detected, THE system SHALL gracefully degrade and report reduced confidence
4. WHERE signal quality is poor (SNR < 10dB), THE system SHALL fall back to single-person detection mode
5. WHERE signals cannot be reliably separated, THE system SHALL report "single_person" mode in the output payload

### Correctness Properties

- **Property 1.1**: Signal separation SHALL preserve total signal energy (sum of separated signals ≈ original signal energy ± 10%)
- **Property 1.2**: Separated signals SHALL have low cross-correlation (< 0.3) indicating independence
- **Property 1.3**: Number of separated signals SHALL not exceed max_capacity (5 people)

---

## Requirement 2: Person ID Lifecycle Management

**User Story**: As a system operator, I want each detected person to have a consistent ID across frames, so that I can track individuals over time.

### Acceptance Criteria

1. WHERE a new person is detected, THE system SHALL assign a unique person ID (1-5)
2. WHERE a person remains in the detection area, THE system SHALL maintain their ID across consecutive frames
3. WHERE a person exits the detection area for >5 seconds, THE system SHALL release their ID for reuse
4. WHERE a person re-enters after ID release, THE system SHALL assign a new ID (may differ from previous)
5. WHERE all IDs are in use and a new person enters, THE system SHALL report max capacity reached

### Correctness Properties

- **Property 2.1**: Person IDs SHALL be unique within a frame (no duplicate IDs)
- **Property 2.2**: Person ID assignment SHALL be deterministic given the same signal features
- **Property 2.3**: Released IDs SHALL be reused in ascending order (1, 2, 3, ...)

---

## Requirement 3: Cross-Viewpoint Position Fusion

**User Story**: As a system operator, I want the system to combine data from multiple Wi-Fi access points, so that position estimates are more accurate.

### Acceptance Criteria

1. WHERE multiple APs are available, THE system SHALL collect RSSI and RTT from each AP
2. WHERE cross-viewpoint data is available, THE system SHALL fuse measurements using weighted averaging (weight = signal strength)
3. WHERE an AP has weak signal (RSSI < -90 dBm), THE system SHALL exclude it from fusion
4. WHERE only one AP is available, THE system SHALL use single-viewpoint estimation
5. WHERE cross-viewpoint fusion is used, THE system SHALL improve position accuracy by at least 20% vs single-viewpoint

### Correctness Properties

- **Property 3.1**: Fused position SHALL be within the convex hull of individual AP position estimates
- **Property 3.2**: Fusion weights SHALL sum to 1.0
- **Property 3.3**: Stronger signals (higher RSSI) SHALL have higher weights in fusion

---

## Requirement 4: Zone-Based Positioning

**User Story**: As a user, I want to know which room or zone each person is in, so that I can understand spatial distribution.

### Acceptance Criteria

1. WHERE a person's position is estimated, THE system SHALL assign them to a zone (left/center/right/unknown)
2. WHERE a person moves between zones, THE system SHALL update their zone assignment within 2 seconds
3. WHERE zone boundaries are configurable, THE system SHALL support custom zone definitions
4. WHERE a person is at a zone boundary, THE system SHALL assign them to the zone with highest confidence
5. WHERE position confidence is low (<50%), THE system SHALL assign zone as "unknown"

### Correctness Properties

- **Property 4.1**: Each person SHALL be assigned to exactly one zone at any time
- **Property 4.2**: Zone transitions SHALL be monotonic (no rapid oscillation between zones)
- **Property 4.3**: Zone assignment SHALL be consistent with position coordinates

---

## Requirement 5: Per-Person Activity Recognition

**User Story**: As a user, I want to know what each person is doing (walking/breathing/still), so that I can understand their activity level.

### Acceptance Criteria

1. WHERE a person's signal is separated, THE system SHALL classify their activity as walking/breathing/still/gesture/unknown
2. WHERE a person is walking, THE system SHALL detect walking frequency (1-4 Hz) with ±0.2 Hz accuracy
3. WHERE a person is breathing, THE system SHALL detect breathing frequency (0.1-0.5 Hz) with ±0.05 Hz accuracy
4. WHERE a person is still for >3 seconds, THE system SHALL classify activity as "still"
5. WHERE activity changes, THE system SHALL update classification within 1 second

### Correctness Properties

- **Property 5.1**: Activity classification SHALL be based on frequency domain features (FFT)
- **Property 5.2**: Walking energy SHALL be in 1-4 Hz band, breathing energy in 0.1-0.5 Hz band
- **Property 5.3**: Activity confidence SHALL be proportional to signal energy in the corresponding frequency band

---

## Requirement 6: Zone Congestion Detection

**User Story**: As a user, I want to be alerted when a zone is congested (≥2 people), so that I can manage space utilization.

### Acceptance Criteria

1. WHERE 2 or more people are in the same zone, THE system SHALL mark that zone as "congested"
2. WHERE zone congestion status changes, THE system SHALL emit a zone_congestion event
3. WHERE congestion is detected, THE system SHALL include congestion info in the output payload
4. WHERE a zone becomes uncongested, THE system SHALL clear the congestion flag within 2 seconds
5. WHERE all zones are congested, THE system SHALL report overall system congestion

### Correctness Properties

- **Property 6.1**: Zone congestion count SHALL equal the number of people assigned to that zone
- **Property 6.2**: Congestion flag SHALL be true IFF person count ≥ 2
- **Property 6.3**: Sum of people across all zones SHALL equal total person count

---

## Requirement 7: Real-Time Performance

**User Story**: As a system operator, I want multi-person detection to run in real-time (<100ms latency), so that the system remains responsive.

### Acceptance Criteria

1. WHERE a detection cycle is executed, THE system SHALL complete processing within 100ms (P95)
2. WHERE processing exceeds 100ms, THE system SHALL log a latency violation warning
3. WHERE system load is high, THE system SHALL prioritize recent frames over queued frames
4. WHERE latency consistently exceeds 200ms, THE system SHALL reduce max_capacity to improve performance
5. WHERE performance is measured, THE system SHALL track per-stage timing (preprocessing, separation, tracking, etc.)

### Correctness Properties

- **Property 7.1**: Average processing latency SHALL be <50ms under normal load
- **Property 7.2**: P99 latency SHALL be <150ms
- **Property 7.3**: Processing time SHALL scale linearly with person count (O(n))

---

## Requirement 8: Event System

**User Story**: As a developer, I want to receive events when people enter/exit or change state, so that I can trigger actions or notifications.

### Acceptance Criteria

1. WHERE a new person is detected, THE system SHALL emit a "person_entered" event with person_id
2. WHERE a person exits (not detected for >5s), THE system SHALL emit a "person_exited" event
3. WHERE a person changes zones, THE system SHALL emit a "position_changed" event
4. WHERE a person changes activity, THE system SHALL emit an "activity_changed" event
5. WHERE event callbacks are registered, THE system SHALL invoke them synchronously within the detection cycle

### Correctness Properties

- **Property 8.1**: Events SHALL be emitted in chronological order
- **Property 8.2**: Each state change SHALL emit exactly one event (no duplicates)
- **Property 8.3**: Event callbacks SHALL not block the detection pipeline (execution time <10ms)

---

## Requirement 9: Calibration and Adaptation

**User Story**: As a system operator, I want the system to automatically calibrate to the environment, so that detection accuracy improves over time.

### Acceptance Criteria

1. WHERE the system starts, THE system SHALL perform initial calibration using the first 10 seconds of data
2. WHERE the environment changes (e.g., furniture moved), THE system SHALL detect baseline drift and recalibrate
3. WHERE recalibration is triggered, THE system SHALL update baseline RSSI and RTT values using EMA (α=0.1)
4. WHERE person signatures are learned, THE system SHALL store them for improved tracking
5. WHERE calibration is complete, THE system SHALL set is_calibrated flag to true

### Correctness Properties

- **Property 9.1**: Baseline SHALL converge to environment mean within 30 seconds
- **Property 9.2**: Recalibration SHALL be triggered when baseline drift exceeds 20%
- **Property 9.3**: Person signatures SHALL be updated incrementally (not replaced entirely)

---

## Requirement 10: Output Payload and Backward Compatibility

**User Story**: As a frontend developer, I want a consistent JSON payload with multi-person data, so that I can visualize all detected people.

### Acceptance Criteria

1. WHERE detection is complete, THE system SHALL generate a JSON payload with person_count, persons[], zone_congestion{}
2. WHERE person_count = 1, THE system SHALL include single_person_update field for backward compatibility
3. WHERE persons[] is populated, EACH person SHALL have person_id, position_zone, activity, confidence, signal_strength
4. WHERE zone_congestion is calculated, THE system SHALL include boolean flags for each zone (left/center/right)
5. WHERE the payload is sent, THE system SHALL broadcast via WebSocket to all connected clients

### Correctness Properties

- **Property 10.1**: person_count SHALL equal len(persons[])
- **Property 10.2**: All person_id values SHALL be unique within persons[]
- **Property 10.3**: Confidence values SHALL be in range [0, 100]

---

## Non-Functional Requirements

### Performance
- Detection latency: <100ms (P95)
- Memory usage: <500MB for 5 people
- CPU usage: <40% on modern hardware

### Reliability
- Graceful degradation with poor signal quality
- No crashes or exceptions during normal operation
- Automatic recovery from transient errors

### Scalability
- Support 2-5 people simultaneously
- Linear scaling with person count
- Efficient memory management (rolling buffers)

### Compatibility
- Backward compatible with single-person mode
- Works with existing WiFi hardware
- No changes to frontend API (additive only)

---

## Constraints

1. **Hardware**: Must work with standard Wi-Fi adapters (no specialized hardware)
2. **Latency**: Real-time processing required (<100ms)
3. **Accuracy**: Minimum 80% separation accuracy for 2-3 people
4. **Capacity**: Maximum 5 people simultaneously
5. **Environment**: Indoor environments with 1-3 Wi-Fi access points

---

## Dependencies

- Existing WiWave single-person detection system
- NumPy and SciPy for signal processing
- FastAPI for WebSocket communication
- React frontend for visualization

---

## Success Criteria

The multi-person detection feature will be considered successful when:

1. ✅ All 10 requirements are implemented and tested
2. ✅ All 31 correctness properties pass property-based tests
3. ✅ System achieves <100ms latency for 2-5 people
4. ✅ Separation accuracy ≥80% for 2-3 people
5. ✅ Frontend displays per-person cards with real-time updates
6. ✅ System passes integration tests with realistic multi-person scenarios
7. ✅ Documentation is complete and accurate

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-15  
**Status**: ✅ IMPLEMENTED
