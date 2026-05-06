import numpy as np
from scipy.fft import fft, fftfreq

# --- CONFIGURATION ---
RSSI_WINDOW = 50       # Longer window for stable distance estimation
RTT_WINDOW = 100       # Large enough for FFT analysis (approx 10 seconds of data)
EMA_ALPHA = 0.05       # Learning rate for the environment baseline (SONA-lite)

# Frequency Bands (Hz) - Assuming 10Hz sampling rate
BREATHING_BAND = (0.1, 0.5)
WALKING_BAND = (1.0, 4.0)
# ---------------------

class MotionDetector:
    """
    Intelligence Upgrade: Uses Adaptive Baselining (EMA), FFT Frequency Analysis,
    and Probabilistic Classification to detect Human Signatures.
    """
    
    def __init__(self, sample_rate=10.0):
        self.sample_rate = sample_rate
        self.rssi_history = []
        self.rtt_history = []
        
        # Adaptive Baseline (EMA)
        self.ema_baseline_rtt = None
        self.ema_baseline_rssi = None
        
        # Classification State
        self.last_activity = "CALM"
        self.confidence = 1.0

    def add_rssi(self, value):
        if value is not None:
            self.rssi_history.append(value)
            if self.ema_baseline_rssi is None:
                self.ema_baseline_rssi = value
            else:
                self.ema_baseline_rssi = (EMA_ALPHA * value) + (1 - EMA_ALPHA) * self.ema_baseline_rssi
        
        if len(self.rssi_history) > RSSI_WINDOW:
            self.rssi_history.pop(0)

    def add_rtt(self, value):
        if value is not None:
            self.rtt_history.append(value)
            if self.ema_baseline_rtt is None:
                self.ema_baseline_rtt = value
            else:
                # Slower adaptation for RTT to avoid swallowing motion into baseline
                self.ema_baseline_rtt = (0.01 * value) + (0.99 * self.ema_baseline_rtt)
        
        if len(self.rtt_history) > RTT_WINDOW:
            self.rtt_history.pop(0)

    def _analyze_frequencies(self):
        """Perform FFT to find periodic signatures (Breathing vs Walking)"""
        if len(self.rtt_history) < 32:
            return 0, 0
            
        # Detrend the data (remove baseline)
        data = np.array(self.rtt_history) - np.mean(self.rtt_history)
        n = len(data)
        
        # Apply Hanning window to reduce leakage
        windowed = data * np.hanning(n)
        
        yf = fft(windowed)
        xf = fftfreq(n, 1 / self.sample_rate)
        
        # Get magnitudes
        mags = np.abs(yf[:n//2])
        freqs = xf[:n//2]
        
        # Calculate energy in specific bands
        breathing_energy = np.sum(mags[(freqs >= BREATHING_BAND[0]) & (freqs <= BREATHING_BAND[1])])
        walking_energy = np.sum(mags[(freqs >= WALKING_BAND[0]) & (freqs <= WALKING_BAND[1])])
        
        return breathing_energy, walking_energy

    def get_motion_status(self):
        """
        Sophisticated classification using Jitter + Frequency Analysis.
        """
        if len(self.rtt_history) < 20:
            return "LEARNING ENVIRONMENT...", 0.0
            
        jitter = np.var(self.rtt_history)
        b_energy, w_energy = self._analyze_frequencies()
        
        # Probabilistic Logic
        if w_energy > 15.0 or jitter > 8.0:
            self.last_activity = "HUMAN DETECTED: WALKING"
            self.confidence = min(1.0, 0.7 + (w_energy / 100.0))
        elif b_energy > 5.0 and jitter < 2.0:
            self.last_activity = "HUMAN DETECTED: BREATHING / PRESENCE"
            self.confidence = min(0.95, 0.5 + (b_energy / 20.0))
        elif jitter > 2.0:
            self.last_activity = "SCANNING: RF INTERFERENCE"
            self.confidence = 0.6
        else:
            self.last_activity = "CALM / NO MOTION"
            self.confidence = 0.9
            
        return f"{self.last_activity} ({int(self.confidence*100)}%)", jitter

    def get_estimated_distance(self):
        if not self.rssi_history or self.ema_baseline_rssi is None:
            return 5.0
            
        current_rssi_avg = np.mean(self.rssi_history[-5:])
        # If current is lower than baseline, distance increased
        diff = self.ema_baseline_rssi - current_rssi_avg
        dist = 5.0 + (diff * 0.4) 
        return max(0.5, min(15.0, dist))

if __name__ == "__main__":
    detector = MotionDetector()
    print("Intelligence Engine v4 Active.")
