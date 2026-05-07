import numpy as np
from scipy.fft import fft, fftfreq
from dataclasses import dataclass

@dataclass
class DetectorConfig:
    """Configuration constants for the Motion Engine."""
    RSSI_WINDOW: int = 50       # Samples for stable distance estimation
    RTT_WINDOW: int = 100       # Samples for FFT analysis (approx 10s at 10Hz)
    EMA_ALPHA_RSSI: float = 0.05 # Learning rate for RSSI baseline
    EMA_ALPHA_RTT: float = 0.01  # Slow adaptation for RTT baseline
    
    # Frequency Bands (Hz) - Assuming 10Hz sampling rate
    BREATHING_BAND: tuple = (0.1, 0.5)
    WALKING_BAND: tuple = (1.0, 4.0)
    
    # Thresholds
    JITTER_THRESHOLD_WALKING: float = 8.0
    JITTER_THRESHOLD_BREATHING: float = 2.0
    ENERGY_THRESHOLD_WALKING: float = 15.0
    ENERGY_THRESHOLD_BREATHING: float = 5.0

class MotionDetector:
    """
    Intelligence Engine v4: Real-time Wi-Fi Motion Detection.
    
    Uses Dual-Sensor Fusion (RSSI + RTT), Adaptive Baselining (EMA), 
    and Frequency Domain Analysis (FFT) to identify human motion signatures.
    """
    
    def __init__(self, sample_rate=10.0, config: DetectorConfig = None):
        self.sample_rate = sample_rate
        self.config = config or DetectorConfig()
        
        self.rssi_history = []
        self.rtt_history = []
        
        # Adaptive Baseline (EMA)
        self.ema_baseline_rtt = None
        self.ema_baseline_rssi = None
        
        # Classification State
        self.last_activity = "CALM"
        self.confidence = 1.0

    def add_rssi(self, value: float):
        """Add a new RSSI (signal strength) reading."""
        if value is None:
            return
            
        self.rssi_history.append(value)
        if self.ema_baseline_rssi is None:
            self.ema_baseline_rssi = value
        else:
            alpha = self.config.EMA_ALPHA_RSSI
            self.ema_baseline_rssi = (alpha * value) + (1 - alpha) * self.ema_baseline_rssi
        
        if len(self.rssi_history) > self.config.RSSI_WINDOW:
            self.rssi_history.pop(0)

    def add_rtt(self, value: float):
        """Add a new RTT (ping latency) reading."""
        if value is None:
            return
            
        self.rtt_history.append(value)
        if self.ema_baseline_rtt is None:
            self.ema_baseline_rtt = value
        else:
            alpha = self.config.EMA_ALPHA_RTT
            self.ema_baseline_rtt = (alpha * value) + (1 - alpha) * self.ema_baseline_rtt
        
        if len(self.rtt_history) > self.config.RTT_WINDOW:
            self.rtt_history.pop(0)

    def _analyze_frequencies(self):
        """Perform FFT to find periodic signatures (Breathing vs Walking)."""
        if len(self.rtt_history) < 32:
            return 0.0, 0.0
            
        # Detrend the data (remove baseline)
        data = np.array(self.rtt_history) - np.mean(self.rtt_history)
        n = len(data)
        
        # Apply Hanning window to reduce spectral leakage
        windowed = data * np.hanning(n)
        
        yf = fft(windowed)
        xf = fftfreq(n, 1 / self.sample_rate)
        
        # Get magnitudes (first half)
        mags = np.abs(yf[:n//2])
        freqs = xf[:n//2]
        
        # Calculate energy in specific bands
        b_mask = (freqs >= self.config.BREATHING_BAND[0]) & (freqs <= self.config.BREATHING_BAND[1])
        w_mask = (freqs >= self.config.WALKING_BAND[0]) & (freqs <= self.config.WALKING_BAND[1])
        
        breathing_energy = np.sum(mags[b_mask])
        walking_energy = np.sum(mags[w_mask])
        
        return breathing_energy, walking_energy

    def get_motion_status(self):
        """
        Classifies current environment based on Jitter + Frequency Analysis.
        Returns (status_string, jitter_variance).
        """
        if len(self.rtt_history) < 20:
            return "LEARNING ENVIRONMENT...", 0.0
            
        jitter = float(np.var(self.rtt_history))
        b_energy, w_energy = self._analyze_frequencies()
        
        # Probabilistic Logic
        if w_energy > self.config.ENERGY_THRESHOLD_WALKING or jitter > self.config.JITTER_THRESHOLD_WALKING:
            self.last_activity = "HUMAN DETECTED: WALKING"
            self.confidence = min(1.0, 0.7 + (w_energy / 100.0))
        elif b_energy > self.config.ENERGY_THRESHOLD_BREATHING and jitter < self.config.JITTER_THRESHOLD_BREATHING:
            self.last_activity = "HUMAN DETECTED: BREATHING / PRESENCE"
            self.confidence = min(0.95, 0.5 + (b_energy / 20.0))
        elif jitter > self.config.JITTER_THRESHOLD_BREATHING:
            self.last_activity = "SCANNING: RF INTERFERENCE"
            self.confidence = 0.6
        else:
            self.last_activity = "CALM / NO MOTION"
            self.confidence = 0.9
            
        return f"{self.last_activity} ({int(self.confidence*100)}%)", jitter

    def get_estimated_distance(self):
        """
        Estimates distance from router using a Log-Distance Path Loss Model.
        Note: This is an approximation as exact TX power and Path Loss Exponent are unknown.
        """
        if not self.rssi_history or self.ema_baseline_rssi is None:
            return 5.0
            
        current_rssi_avg = np.mean(self.rssi_history[-5:])
        
        # Log-distance path loss model approximation:
        # RSSI = P_tx - 10 * n * log10(d)
        # We use the EMA baseline as a reference (e.g., at 2 meters)
        # d = d_ref * 10^((RSSI_ref - RSSI) / (10 * n))
        
        n = 2.5 # Path loss exponent (indoor environment)
        d_ref = 3.0 # Assumed reference distance for the baseline
        
        # We use signal percentage (0-100) as a proxy for RSSI (dBm)
        # This is rough, but signal% correlates with dBm
        rssi_diff = self.ema_baseline_rssi - current_rssi_avg
        
        # Calculate ratio
        dist = d_ref * (10 ** (rssi_diff / (10 * n)))
        
        return max(0.5, min(20.0, float(dist)))

if __name__ == "__main__":
    detector = MotionDetector()
    print("Intelligence Engine v4 Active.")

if __name__ == "__main__":
    detector = MotionDetector()
    print("Intelligence Engine v4 Active.")
