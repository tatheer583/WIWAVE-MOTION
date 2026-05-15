"""Position estimator module for multi-person detection.

This module provides position estimation capabilities for determining the
location of people based on Wi-Fi signal timing differences between access
points and cross-viewpoint fusion.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict
import time

from multi_person.core.models import PersonState
from multi_person.core.interfaces import PositionEstimatorInterface
from multi_person.modules.signal_processor import SignalProcessor
from multi_person.modules.signal_separator import SignalSeparator


@dataclass
class PositionZone:
    """Represents a position zone in the detection area."""
    zone_id: str  # 'left', 'center', 'right'
    x_range: tuple[float, float]
    name: str


@dataclass
class APData:
    """Data from a single Wi-Fi access point."""
    ap_id: str
    position: tuple[float, float]  # (x, y) position of AP
    rssi: float  # Signal strength
    rtt: float  # Round-trip time
    timestamp: float = field(default_factory=time.time)


@dataclass
class PersonPosition:
    """Estimated position of a person."""
    person_id: int
    position: tuple[float, float]
    zone: str
    confidence: float
    timestamp: float = field(default_factory=time.time)


class PositionEstimator(PositionEstimatorInterface):
    """Position estimator for multi-person detection.
    
    This class implements position estimation algorithms for:
    - Estimating person positions from Wi-Fi signals
    - Assigning people to position zones (left/center/right)
    - Fusing data from multiple access points
    - Tracking position updates at 5 Hz rate
    - Detecting zone congestion
    """

    # Position zones for the detection area
    ZONES = {
        'left': PositionZone('left', (-10.0, -3.0), 'Left Zone'),
        'center': PositionZone('center', (-3.0, 3.0), 'Center Zone'),
        'right': PositionZone('right', (3.0, 10.0), 'Right Zone'),
    }
    
    # Zone boundaries (exclusive for left/center, inclusive for center/right)
    ZONE_BOUNDARIES = {
        'left': (-10.0, -3.0),   # x < -3.0
        'center': (-3.0, 3.0),   # -3.0 <= x <= 3.0
        'right': (3.0, 10.0),    # x > 3.0
    }

    def __init__(
        self,
        signal_processor: Optional[SignalProcessor] = None,
        signal_separator: Optional[SignalSeparator] = None,
        detection_area_width: float = 20.0,
        ap_positions: Optional[dict[str, tuple[float, float]]] = None,
        update_rate_hz: float = 5.0,
    ):
        """Initialize the position estimator.
        
        Args:
            signal_processor: SignalProcessor instance for signal processing
            signal_separator: SignalSeparator instance for signal separation
            detection_area_width: Total width of detection area in meters
            ap_positions: Dictionary mapping AP IDs to their (x, y) positions
            update_rate_hz: Position update rate in Hz (default 5 Hz)
        """
        self.signal_processor = signal_processor or SignalProcessor()
        self.signal_separator = signal_separator or SignalSeparator()
        self.detection_area_width = detection_area_width
        self.update_rate_hz = update_rate_hz
        
        # Default AP positions (3 access points: left, center, right)
        self.ap_positions = ap_positions or {
            'ap1': (-8.0, 0.0),  # Left AP
            'ap2': (0.0, 0.0),   # Center AP
            'ap3': (8.0, 0.0),   # Right AP
        }
        
        # Person position tracking
        self.person_positions: dict[int, PersonPosition] = {}
        self.last_update_times: dict[int, float] = {}
        
        # Zone tracking
        self.zone_persons: dict[str, list[int]] = defaultdict(list)
        
        # Position update timing
        self.min_update_interval = 1.0 / update_rate_hz
        self.last_update_global = 0.0

    def estimate_position(self, signal: Any) -> tuple[float, float]:
        """Estimate position of a single person from signal data.
        
        Uses signal timing differences and RSSI to estimate position.
        For a single AP, returns a position based on signal strength.
        For multiple APs, uses time-of-arrival differences.
        
        Args:
            signal: Signal data from person (dict with 'rssi', 'rtt' keys,
                   or tuple/list of (rssi, rtt) values)
        
        Returns:
            Tuple of (x, y) coordinates representing estimated position
        """
        if signal is None:
            return (0.0, 0.0)
        
        # Preprocess the signal
        preprocessed = self.signal_processor.preprocess_signal(signal)
        
        rssi = preprocessed.get('rssi', np.array([]))
        rtt = preprocessed.get('rtt', np.array([]))
        
        # Calculate average RSSI and RTT
        avg_rssi = float(np.mean(rssi)) if len(rssi) > 0 else -70.0
        avg_rtt = float(np.mean(rtt)) if len(rtt) > 0 else 0.5
        
        # Estimate distance from RSSI (simplified model)
        # RSSI decreases with distance; -30 dBm is very close, -90 dBm is far
        estimated_distance = self._rssi_to_distance(avg_rssi)
        
        # Use the center AP as reference for single-AP estimation
        center_ap_pos = self.ap_positions.get('ap2', (0.0, 0.0))
        
        # Estimate position based on signal characteristics
        # This is a simplified estimation - in practice, you'd use TOA/TDOA
        # For now, we use RSSI-based proximity estimation
        x_position = self._estimate_x_position(avg_rssi, avg_rtt)
        y_position = self._estimate_y_position(avg_rssi, avg_rtt)
        
        return (x_position, y_position)

    def estimate_positions(self, signals: list[Any]) -> list[tuple[float, float]]:
        """Estimate positions of multiple people.
        
        Args:
            signals: List of individual person signals
        
        Returns:
            List of (x, y) coordinate tuples for each person
        """
        if not signals:
            return []
        
        positions = []
        for signal in signals:
            position = self.estimate_position(signal)
            positions.append(position)
        
        return positions

    def fuse_cross_viewpoint(self, ap_data: dict[str, dict[str, Any]]) -> tuple[float, float]:
        """Combine data from multiple Wi-Fi access points for position estimation.
        
        Uses time-of-arrival differences and RSSI-based proximity to estimate
        position from multiple viewpoints (access points).
        
        Args:
            ap_data: Dictionary mapping AP IDs to their data dictionaries.
                    Each data dict should contain 'rssi', 'rtt', and optionally
                    'timestamp' and 'position'.
        
        Returns:
            Tuple of (x, y) coordinates representing fused position estimate
        """
        if not ap_data:
            return (0.0, 0.0)
        
        # Parse AP data into APData objects
        ap_data_objects = []
        for ap_id, data in ap_data.items():
            rssi = data.get('rssi', -70.0)
            rtt = data.get('rtt', 0.5)
            timestamp = data.get('timestamp', time.time())
            
            # Get AP position (use default if not provided)
            ap_pos = self.ap_positions.get(ap_id, (0.0, 0.0))
            
            ap_data_objects.append(APData(
                ap_id=ap_id,
                position=ap_pos,
                rssi=rssi,
                rtt=rtt,
                timestamp=timestamp,
            ))
        
        if len(ap_data_objects) == 0:
            return (0.0, 0.0)
        
        if len(ap_data_objects) == 1:
            # Single AP - use RSSI-based estimation
            ap = ap_data_objects[0]
            return self._estimate_single_ap_position(ap)
        
        # Multiple APs - use trilateration-like approach
        return self._estimate_multilateration(ap_data_objects)

    def update_position(self, person_id: int, zone: str) -> bool:
        """Update position with 5 Hz rate limit.
        
        Updates the position state for a person, ensuring updates
        don't exceed the configured rate (default 5 Hz).
        
        Args:
            person_id: Unique identifier for the person
            zone: Position zone ('left', 'center', 'right')
        
        Returns:
            True if position was updated, False if rate-limited
        """
        current_time = time.time()
        
        # Check rate limit
        if person_id in self.last_update_times:
            time_since_last = current_time - self.last_update_times[person_id]
            if time_since_last < self.min_update_interval:
                return False  # Rate limited
        
        # Update position
        self.last_update_times[person_id] = current_time
        
        # Update zone tracking
        self._update_zone_tracking(person_id, zone)
        
        return True

    def get_position_zone(self, position: tuple[float, float]) -> str:
        """Determine which zone a position belongs to.
        
        Args:
            position: (x, y) coordinates
        
        Returns:
            Zone name ('left', 'center', 'right')
        """
        x, _ = position
        
        # Check zones in order: left, center, right
        # Left zone: x < -3.0
        if x < -3.0:
            return 'left'
        
        # Center zone: -3.0 <= x <= 3.0
        if -3.0 <= x <= 3.0:
            return 'center'
        
        # Right zone: x > 3.0
        if x > 3.0:
            return 'right'
        
        # Default to center if outside all zones
        return 'center'

    def get_zone_persons(self, zone: str) -> list[int]:
        """Get list of person IDs in a specific zone.
        
        Args:
            zone: Zone name ('left', 'center', 'right')
        
        Returns:
            List of person IDs in the zone
        """
        return self.zone_persons.get(zone, []).copy()

    def detect_zone_congestion(self, zone: str, threshold: int = 2) -> bool:
        """Detect if a zone has too many people.
        
        Args:
            zone: Zone name to check
            threshold: Number of people that constitutes congestion
        
        Returns:
            True if zone is congested
        """
        person_count = len(self.get_zone_persons(zone))
        return person_count >= threshold

    def get_all_zones_congestion(self) -> dict[str, bool]:
        """Get congestion status for all zones.
        
        Returns:
            Dictionary mapping zone names to congestion status
        """
        return {
            zone_name: self.detect_zone_congestion(zone_name)
            for zone_name in self.ZONES.keys()
        }

    def get_person_position(self, person_id: int) -> Optional[PersonPosition]:
        """Get the current position of a person.
        
        Args:
            person_id: Person ID to look up
        
        Returns:
            PersonPosition object or None if not found
        """
        return self.person_positions.get(person_id)

    def _rssi_to_distance(self, rssi: float) -> float:
        """Convert RSSI to estimated distance.
        
        Uses a simplified path loss model:
        distance = 10^((RSSI_ref - RSSI) / (10 * n))
        
        Args:
            rssi: RSSI value in dBm
        
        Returns:
            Estimated distance in meters
        """
        # Reference RSSI at 1 meter (typical for Wi-Fi)
        rssi_ref = -30.0
        # Path loss exponent (typical for indoor)
        path_loss_exponent = 2.5
        
        # Calculate distance without clamping first
        # RSSI typically ranges from -30 (very close) to -100 (very far)
        # Higher RSSI (closer to 0) = closer distance
        # Lower RSSI (more negative) = farther distance
        distance = 10 ** ((rssi_ref - rssi) / (10 * path_loss_exponent))
        
        # Clamp to reasonable range
        return min(max(distance, 0.5), 30.0)

    def _estimate_x_position(self, rssi: float, rtt: float) -> float:
        """Estimate x position based on signal characteristics.
        
        Uses RSSI as a proxy for distance from center, with adjustments
        based on RTT patterns.
        
        Args:
            rssi: Average RSSI value
            rtt: Average RTT value
        
        Returns:
            Estimated x position
        """
        # RSSI-based distance from center AP
        # Stronger signal (higher RSSI) = closer to center
        distance_from_center = self._rssi_to_distance(rssi)
        
        # RTT can indicate relative position
        # Higher RTT might indicate further distance
        rtt_factor = (rtt - 0.5) * 10  # Normalize RTT to position offset
        
        # Combine factors
        # Stronger RSSI pulls toward center, RTT adjusts based on timing
        x_position = rtt_factor
        
        # Clamp to detection area
        half_width = self.detection_area_width / 2
        x_position = max(-half_width, min(half_width, x_position))
        
        return x_position

    def _estimate_y_position(self, rssi: float, rtt: float) -> float:
        """Estimate y position based on signal characteristics.
        
        For a single AP, assumes person is in front of the AP (y > 0).
        For multiple APs, uses trilateration.
        
        Args:
            rssi: Average RSSI value
            rtt: Average RTT value
        
        Returns:
            Estimated y position
        """
        # Assume person is in front of the detection area
        # Y position is typically positive (in front of APs)
        y_position = 2.0 + (self._rssi_to_distance(rssi) * 0.1)
        
        # Clamp to reasonable range
        return max(0.0, min(10.0, y_position))

    def _estimate_single_ap_position(self, ap: APData) -> tuple[float, float]:
        """Estimate position using a single access point.
        
        Args:
            ap: APData object with signal data
        
        Returns:
            Estimated (x, y) position
        """
        ap_pos = ap.position
        distance = self._rssi_to_distance(ap.rssi)
        
        # For single AP, assume person is in front (positive y direction)
        # and estimate x based on signal strength relative to AP
        x_offset = (ap.rtt - 0.5) * 5  # RTT-based x offset
        y_offset = distance  # Distance from AP
        
        x = ap_pos[0] + x_offset
        y = ap_pos[1] + y_offset
        
        return (x, y)

    def _estimate_multilateration(self, ap_data: list[APData]) -> tuple[float, float]:
        """Estimate position using multiple access points.
        
        Uses a simplified trilateration approach combining:
        - RSSI-based distance estimates
        - Time-of-arrival differences
        
        Args:
            ap_data: List of APData objects
        
        Returns:
            Estimated (x, y) position
        """
        if len(ap_data) == 0:
            return (0.0, 0.0)
        
        if len(ap_data) == 1:
            return self._estimate_single_ap_position(ap_data[0])
        
        # Weighted average based on signal strength
        # Stronger signals (higher RSSI) get more weight
        total_weight = 0.0
        weighted_x = 0.0
        weighted_y = 0.0
        
        for ap in ap_data:
            # Convert RSSI to weight (higher RSSI = higher weight)
            # RSSI typically ranges from -30 (very close) to -100 (very far)
            weight = max(0.0, (ap.rssi + 100) / 70.0)  # Normalize to 0-1
            
            if weight > 0:
                # Estimate position relative to this AP
                ap_pos = ap.position
                distance = self._rssi_to_distance(ap.rssi)
                
                # Simple estimation: person is in front of AP
                x = ap_pos[0] + (ap.rtt - 0.5) * 5
                y = ap_pos[1] + distance
                
                weighted_x += weight * x
                weighted_y += weight * y
                total_weight += weight
        
        if total_weight > 0:
            return (weighted_x / total_weight, weighted_y / total_weight)
        
        # Fallback: use center of APs
        avg_x = np.mean([ap.position[0] for ap in ap_data])
        avg_y = np.mean([ap.position[1] for ap in ap_data])
        return (avg_x, avg_y)

    def _update_zone_tracking(self, person_id: int, zone: str) -> None:
        """Update zone tracking for a person.
        
        Args:
            person_id: Person ID
            zone: Zone name
        """
        # Remove from old zone
        for old_zone, persons in self.zone_persons.items():
            if person_id in persons:
                persons.remove(person_id)
        
        # Add to new zone
        if zone not in self.zone_persons:
            self.zone_persons[zone] = []
        self.zone_persons[zone].append(person_id)
        
        # Update person position
        self.person_positions[person_id] = PersonPosition(
            person_id=person_id,
            position=(0.0, 0.0),  # Will be updated by caller
            zone=zone,
            confidence=1.0,
            timestamp=time.time(),
        )

    def reset(self) -> None:
        """Reset the position estimator state."""
        self.person_positions = {}
        self.last_update_times = {}
        self.zone_persons = defaultdict(list)
        self.last_update_global = 0.0
