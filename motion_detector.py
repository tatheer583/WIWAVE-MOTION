import numpy as np
from scipy.signal import welch, butter, sosfilt
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging

# Setup basic logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("WiWave.DSP")

class FilterError(Exception):
    """Raised when filter coefficients are numerically unstable."""
    pass

def validate_filter_stability(sos, fs):
    """Validates SOS filter stability by checking if all poles are within the unit circle."""
    for section in sos:
        a = section[3:]
        roots = np.roots(a)
        if np.any(np.abs(roots) >= 1.0):
            raise FilterError(f"Filter unstable at fs={fs}Hz (pole magnitude >= 1.0)")
    return True

@dataclass
class GestureEvent:
    type: str
    confidence: float
    timestamp: datetime

class GestureDetector:
    """
    Real-time Gesture Recognition.
    Detects 'wave' (1-2Hz burst) and 'still' (immobility).
    """
    def __init__(self, sample_rate=10.0):
        self.sample_rate = sample_rate
        self.still_threshold_seconds = 3.0
        self.last_motion_time = datetime.now()
        self.is_still = False

    def update(self, rtt_window, walking_energy, breathing_energy, jitter):
        """
        Processes a 1s window (approx 10 samples) for gesture signatures.
        """
        now = datetime.now()
        
        # 1. Detect 'STILL' (No motion across all bands for 3s)
        if jitter > 2.0 or walking_energy > 0.5 or breathing_energy > 0.5:
            self.last_motion_time = now
            if self.is_still:
                self.is_still = False
        else:
            if not self.is_still and (now - self.last_motion_time).total_seconds() > self.still_threshold_seconds:
                self.is_still = True
                return GestureEvent("still", 0.95, now)

        # 2. Detect 'WAVE' (1-2 Hz modulation in RTT)
        # Requires approx 1s of data
        if len(rtt_window) >= 10:
            # Look for 1-2 Hz signature in the very recent window
            # Wave is faster than breathing but rhythmic like walking
            data = np.array(rtt_window[-10:])
            data = data - np.mean(data)
            
            # Simple zero-crossing or peak detection for short-lived gesture
            # A 1-2Hz wave over 500ms has ~1 period (2 crossings)
            crossings = np.where(np.diff(np.sign(data)))[0]
            
            # If we see 2-4 crossings in 1s with high enough energy
            if 2 <= len(crossings) <= 5 and 2.0 < walking_energy < 8.0:
                # Confidence based on energy alignment
                return GestureEvent("wave", 0.85, now)

        return None

class KalmanFilter1D:
    def __init__(self, Q=0.01, R=0.1, initial_state=None):
        self.Q, self.R, self.x, self.P = Q, R, initial_state, 1.0
    def update(self, z):
        if self.x is None: self.x = z; return z
        self.P += self.Q
        K = self.P / (self.P + self.R)
        self.x += K * (z - self.x)
        self.P = (1 - K) * self.P
        return self.x
    def reset(self, initial_state=None):
        self.x, self.P = initial_state, 1.0

@dataclass
class FallEvent:
    confidence: float
    timestamp: datetime

@dataclass
class SleepSegment:
    start_time: str; end_time: str; stage: str; avg_breath_hz: float

class SleepTracker:
    def __init__(self, window_seconds=30):
        self.window_seconds, self.buffer, self.segments, self.current_session_start = window_seconds, [], [], None
    def update(self, breathing_energy, breathing_hz, timestamp, is_moving):
        if self.current_session_start is None: self.current_session_start = timestamp
        self.buffer.append({"ts": timestamp, "energy": breathing_energy, "hz": breathing_hz, "moving": is_moving})
        elapsed = (timestamp - self.buffer[0]["ts"]).total_seconds()
        if elapsed >= self.window_seconds: self._classify_window(); self.buffer = []
    def _classify_window(self):
        energies = [d["energy"] for d in self.buffer]; frequencies = [d["hz"] for d in self.buffer]
        moving_count = sum(1 for d in self.buffer if d["moving"])
        hz_var, avg_hz, avg_energy = np.var(frequencies), np.mean(frequencies), np.mean(energies)
        if moving_count > (len(self.buffer) * 0.2) or avg_energy < 0.05: stage = "AWAKE"
        elif 0.20 <= avg_hz <= 0.26 and hz_var < 0.001: stage = "DEEP SLEEP"
        elif hz_var > 0.005: stage = "REM"
        else: stage = "LIGHT SLEEP"
        self.segments.append(SleepSegment(self.buffer[0]["ts"].isoformat(), self.buffer[-1]["ts"].isoformat(), stage, round(avg_hz, 3)))
    def export_session(self): return [asdict(s) for s in self.segments]

class FallDetector:
    def __init__(self, cooldown_seconds=30):
        self.cooldown_seconds, self.last_alert_time, self.in_impact_state, self.impact_start_time, self.max_impact_energy = cooldown_seconds, None, False, None, 0.0
    def update(self, walking_energy, timestamp):
        now = timestamp
        if self.last_alert_time and (now - self.last_alert_time).total_seconds() < self.cooldown_seconds: return None
        if walking_energy > 5.0:
            if not self.in_impact_state: self.in_impact_state, self.impact_start_time, self.max_impact_energy = True, now, walking_energy
            else: self.max_impact_energy = max(self.max_impact_energy, walking_energy)
            return None
        if self.in_impact_state:
            dt = (now - self.impact_start_time).total_seconds()
            if walking_energy < 0.1:
                if 0.3 <= dt <= 1.2:
                    self.last_alert_time, self.in_impact_state = now, False
                    return FallEvent(min(0.95, 0.4 + (self.max_impact_energy / 20.0)), now)
                elif dt > 1.2: self.in_impact_state = False
        return None

def fuse_distance_estimates(d_rssi, sigma_rssi, d_rtt, sigma_rtt):
    sigma_rssi, sigma_rtt = max(sigma_rssi, 1e-6), max(sigma_rtt, 1e-6)
    w_rssi, w_rtt = 1.0 / (sigma_rssi ** 2), 1.0 / (sigma_rtt ** 2)
    return float((d_rssi * w_rssi + d_rtt * w_rtt) / (w_rssi + w_rtt)), float(np.sqrt(1.0 / (w_rssi + w_rtt)))

@dataclass
class DetectorConfig:
    RSSI_WINDOW: int = 50; RTT_WINDOW: int = 100; MIN_BUFFER: int = 32
    KALMAN_Q_RSSI: float = 0.001; KALMAN_R_RSSI: float = 10.0; KALMAN_Q_RTT: float = 0.1; KALMAN_R_RTT: float = 1.0
    BREATHING_BAND: tuple = (0.1, 0.5); WALKING_BAND: tuple = (1.0, 4.0)
    FILTER_LOW: float = 0.05; FILTER_HIGH: float = 4.99
    JITTER_THRESHOLD_WALKING: float = 8.0; JITTER_THRESHOLD_BREATHING: float = 2.0
    ENERGY_THRESHOLD_WALKING: float = 1.0; ENERGY_THRESHOLD_BREATHING: float = 0.2
    SIGMA_RSSI: float = 2.5; SIGMA_RTT: float = 0.4

def build_bandpass_filter(low_hz, high_hz, fs, order=4):
    nyq = 0.5 * fs; low, high = low_hz / nyq, high_hz / nyq
    return butter(order, [low, high], btype='band', output='sos')

class MotionDetector:
    def __init__(self, sample_rate=10.0, config: DetectorConfig = None):
        self.sample_rate = sample_rate
        self.config = config or DetectorConfig()
        self.rssi_history, self.rtt_history, self.ts_history = [], [], []
        self.kf_rssi = KalmanFilter1D(Q=self.config.KALMAN_Q_RSSI, R=self.config.KALMAN_R_RSSI)
        self.kf_rtt = KalmanFilter1D(Q=self.config.KALMAN_Q_RTT, R=self.config.KALMAN_R_RTT)
        self.fall_detector, self.sleep_tracker, self.gesture_detector = FallDetector(), SleepTracker(), GestureDetector(sample_rate)
        self.last_activity, self.confidence, self.last_uncertainty = "CALM", 1.0, 1.0

    def add_rssi(self, value: float):
        if value is None: return
        self.rssi_history.append(value); self.ema_baseline_rssi = self.kf_rssi.update(value)
        if len(self.rssi_history) > self.config.RSSI_WINDOW: self.rssi_history.pop(0)

    def add_rtt(self, value: float, timestamp: datetime = None):
        if value is None: return
        now = timestamp or datetime.now()
        self.rtt_history.append(value); self.ts_history.append(now.timestamp()); self.ema_baseline_rtt = self.kf_rtt.update(value)
        if len(self.rtt_history) > self.config.RTT_WINDOW: self.rtt_history.pop(0); self.ts_history.pop(0)

    def reset_rtt_state(self):
        self.rtt_history, self.ts_history = [], []; self.kf_rtt.reset()
        logger.info("RTT State Reset: Signal loss detected.")

    def _analyze_frequencies(self):
        fallback = {"breathing_energy": 0.0, "walking_energy": 0.0, "breathing_hz": 0.0, "walking_hz": 0.0, "status": "low_fs"}
        if len(self.rtt_history) < self.config.MIN_BUFFER: return fallback
        ts_diffs = np.diff(self.ts_history)
        actual_fs = 1.0 / np.mean(ts_diffs) if len(ts_diffs) > 0 and np.mean(ts_diffs) > 0 else self.sample_rate
        raw_data = np.array(self.rtt_history); processed_data = raw_data
        
        if actual_fs < 0.5:
            logger.warning(f"Critical low FS ({actual_fs:.2f}Hz). Skipping analysis.")
            return fallback
            
        try:
            assert actual_fs > 2 * self.config.FILTER_HIGH, f"FS {actual_fs:.2f}Hz <= Nyquist requirement"
            sos = build_bandpass_filter(self.config.FILTER_LOW, self.config.FILTER_HIGH, actual_fs)
            validate_filter_stability(sos, actual_fs)
            processed_data = sosfilt(sos, raw_data)
        except (AssertionError, FilterError) as e:
            logger.warning(f"Bypassing filter: {e}")
            processed_data = raw_data - np.mean(raw_data)
        except Exception as e:
            logger.error(f"Filter design error: {e}. Bypassing.")
            processed_data = raw_data - np.mean(raw_data)
            
        logger.debug(f"Calling welch() with actual_fs={actual_fs:.2f}Hz")
        f, pxx = welch(processed_data, fs=actual_fs, nperseg=len(processed_data), detrend='constant')
        b_mask, w_mask = (f >= self.config.BREATHING_BAND[0]) & (f <= self.config.BREATHING_BAND[1]), (f >= self.config.WALKING_BAND[0]) & (f <= self.config.WALKING_BAND[1])
        
        if not np.any(b_mask) or not np.any(w_mask):
            logger.warning(f"Low sampling rate ({actual_fs:.2f}Hz). Frequency bands not populated.")
            return fallback
            
        try:
            b_en = float(np.trapezoid(pxx[b_mask], f[b_mask]))
            w_en = float(np.trapezoid(pxx[w_mask], f[w_mask]))
        except AttributeError: # Fallback for older numpy versions
            b_en = float(np.trapz(pxx[b_mask], f[b_mask]))
            w_en = float(np.trapz(pxx[w_mask], f[w_mask]))

        return {
            "breathing_energy": b_en,
            "walking_energy": w_en,
            "breathing_hz": float(f[b_mask][np.argmax(pxx[b_mask])]),
            "walking_hz": float(f[w_mask][np.argmax(pxx[w_mask])]),
            "status": "ok"
        }

    def get_motion_status(self):
        current_len = len(self.rtt_history)
        if current_len < self.config.MIN_BUFFER: return "LEARNING ENVIRONMENT...", 0.0, None, current_len / self.config.MIN_BUFFER, None
        jitter = max(float(np.var(self.rtt_history)), 1e-9)
        freqs = self._analyze_frequencies()
        b_energy, w_energy, b_hz, w_hz = freqs["breathing_energy"], freqs["walking_energy"], freqs["breathing_hz"], freqs["walking_hz"]
        now = datetime.now()
        fall_event = self.fall_detector.update(w_energy, now)
        is_moving = w_energy > self.config.ENERGY_THRESHOLD_WALKING or jitter > self.config.JITTER_THRESHOLD_WALKING
        self.sleep_tracker.update(b_energy, b_hz, now, is_moving)
        gesture_event = self.gesture_detector.update(self.rtt_history, w_energy, b_energy, jitter)
        if is_moving:
            self.last_activity = f"HUMAN DETECTED: WALKING ({w_hz:.1f}Hz)"
            self.confidence = min(1.0, 0.7 + (w_energy / 10.0))
        elif b_energy > self.config.ENERGY_THRESHOLD_BREATHING and jitter < self.config.JITTER_THRESHOLD_BREATHING:
            self.last_activity = f"HUMAN DETECTED: BREATHING ({b_hz:.2f}Hz)"
            self.confidence = min(0.95, 0.5 + (b_energy / 2.0))
        elif jitter > self.config.JITTER_THRESHOLD_BREATHING:
            self.last_activity, self.confidence = "SCANNING: RF INTERFERENCE", 0.6
        else: self.last_activity, self.confidence = "CALM / NO MOTION", 0.9
        return f"{self.last_activity} ({int(self.confidence*100)}%)", jitter, fall_event, 1.0, gesture_event

    def _estimate_distance_rssi(self):
        if not self.rssi_history or self.kf_rssi.x is None: return 5.0
        rssi_diff = self.kf_rssi.x - np.mean(self.rssi_history[-5:])
        return max(0.5, min(20.0, float(3.0 * (10 ** (rssi_diff / 25.0)))))

    def _estimate_distance_rtt(self):
        if not self.rtt_history: return 3.0
        return max(1.0, min(10.0, 5.0 - np.log1p(np.var(self.rtt_history[-10:]))))

    def get_estimated_distance(self):
        d, unc = fuse_distance_estimates(self._estimate_distance_rssi(), self.config.SIGMA_RSSI, self._estimate_distance_rtt(), self.config.SIGMA_RTT)
        self.last_uncertainty = unc
        return d

if __name__ == "__main__":
    detector = MotionDetector()
    print("Intelligence Engine v4 Active.")
