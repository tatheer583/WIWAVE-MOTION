"""Detect changes relative to a quiet baseline, without inferring identities.

RSSI is coarse link telemetry. CSI amplitude changes provide richer motion
evidence, but this unsupervised detector is not a human classifier.
"""
from collections import deque
import math
import numpy as np


class ChangeDetector:
    def __init__(self, calibration_seconds=20.0, window_seconds=2.0):
        self.calibration_seconds = calibration_seconds
        self.window_seconds = window_seconds
        self.reset()

    def reset(self):
        self.history = deque(maxlen=2000)
        self.baseline = []
        self.started = None
        self.center = None
        self.noise = None
        self.source_key = None
        self.last_time = None
        self.candidate_since = None
        self.quiet_since = None
        self.active = False
        self.events = 0
        self.last_channel_z = None
        self.last_was_csi = False

    def update(self, sample, now):
        is_csi = sample.get('amplitudes') is not None
        if is_csi:
            values = np.asarray(sample['amplitudes'], dtype=float)
        else:
            # Primary link first; neighbor access points from the scan cache are
            # extra slow channels. All values share dBm units.
            links = [link for link in sample.get('links') or [] if link.get('rssi_dbm') is not None]
            values = np.asarray([sample['rssi_dbm']] + [link['rssi_dbm'] for link in links], dtype=float)
        if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
            raise ValueError('Sensor values must be a finite vector')
        if is_csi:
            scale = float(np.mean(values))
            if scale <= 0:
                raise ValueError('CSI frame contains no signal')
            values = values / scale
        key = (sample['source'], sample.get('link_id'), sample.get('channel'), len(values))
        if key != self.source_key or (self.last_time is not None and now - self.last_time > 3):
            self.reset()
            self.source_key = key
        if self.last_time is not None and now <= self.last_time:
            raise ValueError('Samples must be ordered by acquisition time')
        self.last_time = now
        if self.started is None:
            self.started = now
        self.history.append((now, values))
        while self.history and now - self.history[0][0] > self.window_seconds:
            self.history.popleft()
        progress = min(1.0, (now - self.started) / self.calibration_seconds)
        if self.center is None:
            self.baseline.append(values)
            # Time and minimum sample count must both be satisfied.
            progress = min(progress, len(self.baseline) / 30)
            if progress >= 1:
                baseline = np.stack(self.baseline)
                self.center = np.median(baseline, axis=0)
                floor = 0.015 if is_csi else 1.0
                self.noise = np.maximum(1.4826 * np.median(np.abs(baseline - self.center), axis=0), floor)
                self.baseline = []
            return self.result('calibrating', progress, 0.0)

        recent = np.stack([value for _, value in self.history])
        # Require sustained deviations across a time window; an isolated spike
        # cannot trigger, and scalar receiver gain is normalized for CSI.
        excursion = np.percentile(np.abs(recent - self.center), 75, axis=0)
        spread = 1.4826 * np.median(np.abs(recent - np.median(recent, axis=0)), axis=0)
        channel_z = np.maximum(excursion, spread) / self.noise
        if is_csi:
            z = float(np.median(channel_z))
        elif channel_z.size > 1:
            # Primary link is the fast, sensitive channel; neighbor links vote
            # as slow confirmation so one noisy neighbor cannot trigger alone.
            z = float(max(channel_z[0], 0.9 * float(np.median(channel_z[1:]))))
        else:
            z = float(channel_z[0])
        self.last_channel_z = channel_z
        self.last_was_csi = is_csi
        score = min(100.0, max(0.0, z / 6.0 * 100.0))
        if z >= 3.0:
            self.quiet_since = None
            if self.candidate_since is None:
                self.candidate_since = now
            if now - self.candidate_since >= 0.6 and not self.active:
                self.active = True
                self.events += 1
        else:
            self.candidate_since = None
            if self.active and z < 1.8:
                if self.quiet_since is None:
                    self.quiet_since = now
                if now - self.quiet_since >= 2.0:
                    self.active = False
            else:
                self.quiet_since = None
        state = 'motion_candidate' if is_csi and self.active else 'signal_change' if self.active else 'quiet'
        return self.result(state, 1.0, score)

    def result(self, state, progress, score):
        times = [row[0] for row in self.history]
        rate = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0.0
        links = None
        if self.last_channel_z is not None and not self.last_was_csi and self.last_channel_z.size > 1:
            links = [round(min(100.0, max(0.0, float(z) / 6.0 * 100.0)), 1) for z in self.last_channel_z]
        return {
            'state': state, 'learning_progress': round(progress, 3),
            'change_score': round(score, 1), 'motion_detected': self.active,
            'read_rate_hz': round(rate, 2) if math.isfinite(rate) else 0,
            'event_count': self.events,
            'baseline_rssi_dbm': round(float(self.center[0]), 1)
            if self.center is not None and len(self.center) == 1 else None,
            'link_change': links,
        }
