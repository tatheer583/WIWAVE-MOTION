"""Spectral statistics for the live signal stream.

The bands below are named for their frequency ranges, not their cause: ordinary
RSSI at ~10 Hz is a coarse, quantized channel, and energy in the 0.1-0.5 Hz band
is described here as slow oscillation, never as breathing or footsteps. These
statistics describe the measured link; associating them with activity requires
labelled room trials and a validated model.
"""
from collections import deque
import math
import numpy as np
from scipy.signal import welch

BANDS = {'slow_oscillation': (0.1, 0.5), 'mid_activity': (0.5, 2.0), 'fast_activity': (2.0, 4.0)}


class SpectralAnalyzer:
    """Resamples the primary-signal stream onto a uniform grid and keeps
    rolling Welch power statistics over a bounded window."""

    def __init__(self, rate_hz=10.0, window_seconds=30.0, minimum_seconds=12.0):
        self.rate = float(rate_hz)
        self.window_seconds = float(window_seconds)
        self.minimum = max(30, int(self.rate * minimum_seconds))
        self.buffer = deque(maxlen=int(self.rate * (window_seconds + 2)) + 4)
        self.statistics = None

    def update(self, now, value):
        if value is None or not math.isfinite(value):
            return self.statistics
        if self.buffer and now <= self.buffer[-1][0]:
            return self.statistics
        self.buffer.append((now, value))
        times = np.array([t for t, _ in self.buffer], dtype=float)
        if now - times[0] < self.minimum / self.rate:
            self.statistics = None
            return None
        values = np.array([v for _, v in self.buffer], dtype=float)
        grid = np.arange(times[0], times[-1] - 1e-9, 1.0 / self.rate)
        signal = np.interp(grid, times, values)
        signal -= signal.mean()
        nperseg = min(256, len(signal))
        _, power = welch(signal, fs=self.rate, nperseg=nperseg, noverlap=nperseg // 2)
        total = float(power.sum())
        if not math.isfinite(total) or total <= 1e-12:
            self.statistics = None
            return None
        freqs = np.fft.rfftfreq(nperseg, d=1.0 / self.rate)[:len(power)]
        bands = {name: round(float(power[(freqs >= low) & (freqs < high)].sum() / total), 3)
                 for name, (low, high) in BANDS.items()}
        share = power / total
        entropy = float(-np.sum(share[share > 0] * np.log(share[share > 0])) / math.log(len(share)))
        dominant = float(freqs[int(np.argmax(power))])
        self.statistics = {**bands,
                           'dominant_hz': round(min(dominant, 4.9), 3),
                           'spectral_entropy': round(max(0.0, min(1.0, entropy)), 3),
                           'window_s': round(float(len(signal)) / self.rate, 1)}
        return self.statistics
