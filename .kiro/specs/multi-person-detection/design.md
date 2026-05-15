# Design: Multi-Person Detection for WiWave

## Overview

This document describes the technical design for adding multi-person detection capabilities to WiWave. The system uses Wi-Fi signal analysis (RSSI and RTT) to detect, separate, and track 2-5 people simultaneously.

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     WiFi Hardware Layer                      │
│  (Multiple APs collecting RSSI + RTT measurements)          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              MultiPersonDetector (Orchestrator)              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. CalibrationModule (baseline learning)            │  │
│  │  2. SignalProcessor (FFT, feature extraction)        │  │
│  │  3. SignalSeparator (jitter-based separation)        │  │
│  │  4. PositionEstimator (cross-viewpoint fusion)       │  │
│  │  5. ActivityRecognizer (walking/breathing/still)     │  │
│  │  6. PersonTracker (ID management, state tracking)    │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Output Layer                              │
│  • JSON Payload (person_count, persons[], congestion)       │
│  • WebSocket Broadcast                                       │
│  • Event Emission (person_entered, position_changed, etc.)  │
└─────────────────────────────────────────────────────────────┘
```

### Module Responsibilities

#### 1. CalibrationModule
- **Purpose**: Learn environment baseline and adapt to changes
- **Inputs**: Raw signal data (RSSI, RTT)
- **Outputs**: Calibrated signal, baseline parameters
- **Key Methods**:
  - `calibrate(reference_signal)` - Initial calibration
  - `apply_calibration(signal)` - Apply calibration to new signals
  - `adapt_to_environment(features)` - EMA-based adaptation

#### 2. SignalProcessor
- **Purpose**: Preprocess signals and extract features
- **Inputs**: Raw signal data
- **Outputs**: Preprocessed signal, signal features
- **Key Methods**:
  - `preprocess_signal(raw_signal)` - Filtering, normalization
  - `extract_features(signal)` - FFT, energy calculation
  - `cluster_signals(features)` - K-means clustering for separation

#### 3. SignalSeparator
- **Purpose**: Separate multi-person signals using jitter analysis
- **Inputs**: Preprocessed signal
- **Outputs**: List of separated signals (one per person)
- **Key Methods**:
  - `separate_signals(signal)` - Main separation algorithm
  - `estimate_signal_count(signal)` - Estimate number of people
  - `assign_person_ids(signals)` - Assign consistent IDs

#### 4. PositionEstimator
- **Purpose**: Estimate position using cross-viewpoint fusion
- **Inputs**: Separated signals, multi-AP data
- **Outputs**: Position coordinates, zone assignment
- **Key Methods**:
  - `estimate_position(signal)` - Single-viewpoint position
  - `fuse_cross_viewpoint(ap_data)` - Multi-AP fusion
  - `get_position_zone(position)` - Zone classification

#### 5. ActivityRecognizer
- **Purpose**: Classify person activity from signal features
- **Inputs**: Signal features (frequency domain)
- **Outputs**: Activity label, confidence
- **Key Methods**:
  - `recognize_activity(signal)` - Main classification
  - `calculate_confidence(features)` - Confidence scoring
  - `emit_activity_change_event(person_id, activity)` - Event emission

#### 6. PersonTracker
- **Purpose**: Track persons across frames with consistent IDs
- **Inputs**: Positions, activities, signal strengths
- **Outputs**: Tracked persons with state history
- **Key Methods**:
  - `track_persons(positions, activities, ...)` - Main tracking
  - `get_or_create_person_id(signature)` - ID lifecycle
  - `update_person_state(person_id, state)` - State management

---

## Data Models

### PersonState
```python
@dataclass
class PersonState:
    person_id: int                    # Unique ID (1-5)
    position: tuple[float, float]     # (x, y) coordinates
    activity: str                     # walking/breathing/still/gesture
    timestamp: float                  # Unix timestamp
    signal_features: dict             # RSSI, RTT, jitter, etc.
    velocity: Optional[tuple[float, float]]  # (vx, vy) if available
    confidence: float                 # 0.0 - 1.0
```

### SignalFeatures
```python
@dataclass
class SignalFeatures:
    rssi_mean: float
    rssi_std: float
    rtt_mean: float
    rtt_std: float
    breathing_energy: float           # Energy in 0.1-0.5 Hz
    walking_energy: float             # Energy in 1-4 Hz
    jitter: float                     # RTT variance
    dominant_frequency: float
```

### DetectionResult
```python
@dataclass
class DetectionResult:
    success: bool
    persons: list[PersonState]
    processing_time_ms: float
    error_message: Optional[str] = None
```

---

## Algorithms

### 1. Signal Separation Algorithm

**Approach**: Jitter-based clustering with temporal consistency

```python
def separate_signals(signal: dict) -> list[dict]:
    """
    Separate multi-person signals using RTT jitter analysis.
    
    Algorithm:
    1. Extract RTT time series
    2. Compute sliding window jitter (variance)
    3. Apply K-means clustering on jitter patterns
    4. Estimate number of clusters (people) using elbow method
    5. Assign signal segments to clusters
    6. Reconstruct separated signals
    
    Time Complexity: O(n * k) where n = signal length, k = num people
    Space Complexity: O(n * k)
    """
    rtt_series = signal['rtt']
    
    # Compute jitter in sliding windows
    window_size = 10
    jitter_features = []
    for i in range(len(rtt_series) - window_size):
        window = rtt_series[i:i+window_size]
        jitter = np.var(window)
        jitter_features.append(jitter)
    
    # Estimate number of people using elbow method
    num_people = estimate_signal_count(jitter_features)
    
    # K-means clustering
    kmeans = KMeans(n_clusters=num_people)
    labels = kmeans.fit_predict(jitter_features)
    
    # Reconstruct separated signals
    separated = []
    for person_id in range(num_people):
        mask = (labels == person_id)
        person_signal = {
            'rssi': signal['rssi'][mask],
            'rtt': rtt_series[mask],
            'person_id': person_id + 1
        }
        separated.append(person_signal)
    
    return separated
```

### 2. Cross-Viewpoint Fusion Algorithm

**Approach**: Weighted averaging based on signal strength

```python
def fuse_cross_viewpoint(ap_data: list[APData]) -> tuple[float, float]:
    """
    Fuse position estimates from multiple APs.
    
    Algorithm:
    1. Filter APs with weak signal (RSSI < -90 dBm)
    2. Compute position estimate from each AP using RSSI-to-distance
    3. Calculate weights based on signal strength
    4. Weighted average of positions
    
    Time Complexity: O(m) where m = number of APs
    Space Complexity: O(m)
    """
    # Filter weak signals
    strong_aps = [ap for ap in ap_data if ap.rssi > -90]
    
    if len(strong_aps) == 0:
        return (0.0, 0.0)  # Default position
    
    # Compute weights (higher RSSI = higher weight)
    weights = []
    positions = []
    
    for ap in strong_aps:
        # Convert RSSI to distance
        distance = rssi_to_distance(ap.rssi)
        
        # Estimate position from AP location and distance
        position = estimate_position_from_ap(ap.location, distance)
        positions.append(position)
        
        # Weight = normalized signal strength
        weight = (ap.rssi + 100) / 100  # Normalize to [0, 1]
        weights.append(weight)
    
    # Normalize weights
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    
    # Weighted average
    x = sum(p[0] * w for p, w in zip(positions, weights))
    y = sum(p[1] * w for p, w in zip(positions, weights))
    
    return (x, y)
```

### 3. Person ID Assignment Algorithm

**Approach**: Signature matching with Hungarian algorithm

```python
def assign_person_ids(current_signals: list, previous_states: dict) -> dict:
    """
    Assign consistent person IDs across frames.
    
    Algorithm:
    1. Extract signature from each current signal (RSSI mean, jitter, position)
    2. Compute similarity matrix between current and previous signatures
    3. Use Hungarian algorithm for optimal assignment
    4. Assign new IDs to unmatched signals
    5. Release IDs for persons not detected
    
    Time Complexity: O(n^3) where n = max(current, previous)
    Space Complexity: O(n^2)
    """
    # Extract signatures
    current_signatures = [extract_signature(s) for s in current_signals]
    previous_signatures = [state.signature for state in previous_states.values()]
    
    # Compute similarity matrix
    similarity = np.zeros((len(current_signatures), len(previous_signatures)))
    for i, curr in enumerate(current_signatures):
        for j, prev in enumerate(previous_signatures):
            similarity[i, j] = compute_similarity(curr, prev)
    
    # Hungarian algorithm for optimal assignment
    row_ind, col_ind = linear_sum_assignment(-similarity)  # Maximize similarity
    
    # Assign IDs
    assignments = {}
    used_ids = set()
    
    for curr_idx, prev_idx in zip(row_ind, col_ind):
        if similarity[curr_idx, prev_idx] > 0.7:  # Threshold
            person_id = list(previous_states.keys())[prev_idx]
            assignments[curr_idx] = person_id
            used_ids.add(person_id)
    
    # Assign new IDs to unmatched signals
    available_ids = [i for i in range(1, 6) if i not in used_ids]
    for i in range(len(current_signals)):
        if i not in assignments:
            if available_ids:
                assignments[i] = available_ids.pop(0)
    
    return assignments
```

### 4. Activity Recognition Algorithm

**Approach**: Frequency domain classification

```python
def recognize_activity(signal: dict) -> tuple[str, float]:
    """
    Classify person activity from signal features.
    
    Algorithm:
    1. Extract frequency domain features (FFT)
    2. Compute energy in breathing band (0.1-0.5 Hz)
    3. Compute energy in walking band (1-4 Hz)
    4. Apply decision tree classifier
    5. Calculate confidence based on energy ratios
    
    Time Complexity: O(n log n) for FFT
    Space Complexity: O(n)
    """
    # FFT
    rtt = signal['rtt']
    freqs, psd = welch(rtt, fs=10.0)
    
    # Energy in bands
    breathing_mask = (freqs >= 0.1) & (freqs <= 0.5)
    walking_mask = (freqs >= 1.0) & (freqs <= 4.0)
    
    breathing_energy = np.trapz(psd[breathing_mask], freqs[breathing_mask])
    walking_energy = np.trapz(psd[walking_mask], freqs[walking_mask])
    
    # Classification
    if walking_energy > 1.0:
        activity = "walking"
        confidence = min(1.0, walking_energy / 5.0)
    elif breathing_energy > 0.2:
        activity = "breathing"
        confidence = min(1.0, breathing_energy / 1.0)
    elif breathing_energy < 0.05 and walking_energy < 0.1:
        activity = "still"
        confidence = 0.9
    else:
        activity = "unknown"
        confidence = 0.5
    
    return activity, confidence
```

---

## Performance Optimizations

### 1. Rolling Buffers
- Use fixed-size circular buffers for signal history
- Prevents unbounded memory growth
- O(1) append and pop operations

### 2. Incremental FFT
- Reuse FFT results from previous frames
- Only compute FFT for new samples
- Reduces computation by ~50%

### 3. Lazy Evaluation
- Compute features only when needed
- Cache results within a frame
- Avoid redundant calculations

### 4. Parallel Processing
- Process separated signals in parallel
- Use ThreadPoolExecutor for I/O-bound tasks
- Maintain frame ordering for consistency

### 5. Adaptive Sampling
- Reduce sampling rate when fewer people detected
- Increase rate when activity is high
- Balance latency vs accuracy

---

## Error Handling

### Graceful Degradation
1. **Poor Signal Quality**: Fall back to single-person mode
2. **Separation Failure**: Report single person with low confidence
3. **Calibration Failure**: Use default baseline values
4. **Timeout**: Skip frame and continue with next

### Error Recovery
1. **Transient Errors**: Retry with exponential backoff
2. **Persistent Errors**: Log and report to monitoring system
3. **State Corruption**: Reset module state and recalibrate

---

## Testing Strategy

### Unit Tests
- Test each module independently
- Mock dependencies
- Cover edge cases (empty signals, single sample, etc.)

### Integration Tests
- Test full pipeline with realistic data
- Verify end-to-end latency
- Test multi-person scenarios (2, 3, 5 people)

### Property-Based Tests
- Test correctness properties (31 properties)
- Use Hypothesis for property testing
- Generate random inputs and verify invariants

### Performance Tests
- Measure latency under load
- Profile CPU and memory usage
- Stress test with max capacity (5 people)

---

## Deployment Considerations

### Hardware Requirements
- CPU: 2+ cores, 2+ GHz
- RAM: 2GB minimum, 4GB recommended
- WiFi: 802.11n or later, multiple APs preferred

### Configuration
- `max_capacity`: Maximum people to detect (default: 5)
- `mode`: "single_person" or "multi_person" (default: "multi_person")
- `target_latency_ms`: Target processing latency (default: 100)

### Monitoring
- Track detection latency (avg, P95, P99)
- Monitor person count over time
- Alert on latency violations or errors

---

## Components and Interfaces

### Module Interface Definitions

```python
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

@dataclass
class ModuleResult:
    success: bool
    error_message: Optional[str] = None

class BaseModule(ABC):
    """Base class for all multi-person detection modules."""
    
    @abstractmethod
    def process(self, input_data: dict) -> dict:
        """Process input data and return results."""
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset module state."""
        pass
```

### Module Contracts

| Module | Input | Output | Key Methods |
|--------|-------|--------|-------------|
| CalibrationModule | Raw signal (RSSI, RTT) | Calibrated signal | calibrate(), apply_calibration(), adapt_to_environment() |
| SignalProcessor | Raw signal | Preprocessed signal + features | preprocess_signal(), extract_features(), cluster_signals() |
| SignalSeparator | Preprocessed signal | List of separated signals | separate_signals(), estimate_signal_count(), assign_person_ids() |
| PositionEstimator | Separated signals + AP data | Position (x, y) + zone | estimate_position(), fuse_cross_viewpoint(), get_position_zone() |
| ActivityRecognizer | Signal features | Activity label + confidence | recognize_activity(), calculate_confidence(), emit_activity_change_event() |
| PersonTracker | Positions + activities | Tracked persons with IDs | track_persons(), get_or_create_person_id(), update_person_state() |

### Data Flow Interface

```
Raw Signal → SignalProcessor → SignalSeparator → PositionEstimator → PersonTracker → Output
                                    ↓
                              ActivityRecognizer
```

---

## Correctness Properties

### Property 1: Person Count Invariant
**Description**: The number of detected persons must be between 0 and max_capacity (default: 5).

**Validates: Requirements 1.3, 7.3**

**Property**:
```
∀ frames: 0 ≤ person_count ≤ max_capacity
```

**Test Strategy**: Generate random person counts and verify output constraints.

---

### Property 2: Person ID Consistency
**Description**: Person IDs must remain consistent across consecutive frames for the same individual.

**Validates: Requirements 2.1, 2.2, 2.3**

**Property**:
```
∀ t: person_id(t+1) = person_id(t) if same person detected
```

**Test Strategy**: Track a person moving through the scene and verify ID persistence.

---

### Property 3: Position Continuity
**Description**: Person positions must change smoothly between frames (no teleportation).

**Validates: Requirements 3.2, 4.1**

**Property**:
```
∀ persons, frames: |position(t+1) - position(t)| ≤ max_velocity * Δt
```

**Test Strategy**: Verify position deltas are within expected velocity bounds.

---

### Property 4: Activity Classification Completeness
**Description**: Every person must have a valid activity classification.

**Validates**: Requirements 5.1, 5.2, 5.3

**Property**:
```
∀ persons: activity ∈ {walking, breathing, still, gesture}
```

**Test Strategy**: Verify all detected persons have non-empty activity labels.

---

### Property 5: Signal Separation Fidelity
**Description**: Separated signals must reconstruct the original signal within tolerance.

**Validates**: Requirements 1.1, 1.2

**Property**:
```
∀ signals: ||original_signal - Σ(separated_signals)|| < tolerance
```

**Test Strategy**: Compare reconstructed signal to original using signal similarity metrics.

---

### Property 6: Cross-Viewpoint Fusion Accuracy
**Description**: Fused positions must be within expected accuracy of ground truth.

**Validates**: Requirements 3.1, 3.2, 3.3

**Property**:
```
∀ positions: ||fused_position - ground_truth|| < position_error_threshold
```

**Test Strategy**: Use known test positions and verify fusion accuracy.

---

### Property 7: Confidence Bounds
**Description**: Confidence values must be between 0 and 1.

**Validates**: Requirements 5.3, 10.3

**Property**:
```
∀ persons: 0.0 ≤ confidence ≤ 1.0
```

**Test Strategy**: Verify all confidence values are in valid range.

---

### Property 8: Processing Latency Bound
**Description**: Frame processing must complete within target latency.

**Validates**: Requirements 7.1, 7.2, 7.3

**Property**:
```
∀ frames: processing_time ≤ target_latency_ms
```

**Test Strategy**: Measure processing time under load and verify latency SLA.

---

### Property 9: Error Recovery
**Description**: System must recover from transient errors without state corruption.

**Validates**: Non-Functional: Reliability

**Property**:
```
∀ errors: system_state(post-recovery) = system_state(expected)
```

**Test Strategy**: Inject errors and verify state consistency after recovery.

---

### Property 10: Graceful Degradation
**Description**: System must provide valid output even under poor conditions.

**Validates**: Non-Functional: Reliability, Requirements 1.4, 1.5

**Property**:
```
∀ conditions: output ≠ None ∧ output.success = true (with reduced confidence)
```

**Test Strategy**: Test with weak signals and verify graceful degradation.

---

**Note**: These properties will be implemented as executable tests using Hypothesis for property-based testing.

---

## Future Enhancements

1. **Machine Learning**: Train neural network for activity recognition
2. **GPU Acceleration**: Use CUDA for FFT and matrix operations
3. **Distributed Processing**: Scale to multiple rooms/buildings
4. **Advanced Tracking**: Kalman filter for position smoothing
5. **Gesture Recognition**: Detect specific gestures (wave, swipe, etc.)

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-15  
**Status**: ✅ IMPLEMENTED
