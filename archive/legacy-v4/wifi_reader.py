"""
wifi_reader.py — Hardware Abstraction Layer for WiWave.

Supports multi-AP data collection with timing information for
cross-viewpoint fusion used by the multi-person detection engine.
"""

import subprocess
import re
import platform
import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class HardwareError(Exception):
    """Raised when the Wi-Fi interface is missing or disconnected."""
    pass


@dataclass
class APReading:
    """A single access point reading with timing information."""
    bssid: str
    signal: int                    # RSSI percentage (0-100)
    timestamp: float               # Unix timestamp of reading
    rtt_ms: Optional[float] = None # Round-trip time in ms (if measured)
    channel: Optional[int] = None  # Wi-Fi channel
    ssid: Optional[str] = None     # Network name


@dataclass
class MultiAPSnapshot:
    """Snapshot of all visible APs at a point in time.

    Used by the cross-viewpoint fusion module to estimate
    person positions relative to multiple access points.
    """
    aps: list[APReading] = field(default_factory=list)
    snapshot_time: float = field(default_factory=time.time)
    primary_rssi: Optional[int] = None   # Connected AP signal %
    primary_rtt: Optional[float] = None  # Connected AP RTT ms

    def to_dict(self) -> dict:
        return {
            "aps": [
                {
                    "bssid": ap.bssid,
                    "signal": ap.signal,
                    "timestamp": ap.timestamp,
                    "rtt_ms": ap.rtt_ms,
                    "channel": ap.channel,
                    "ssid": ap.ssid,
                }
                for ap in self.aps
            ],
            "snapshot_time": self.snapshot_time,
            "primary_rssi": self.primary_rssi,
            "primary_rtt": self.primary_rtt,
        }


class BaseWifiReader(ABC):
    """Abstract Base Class for multi-platform Wi-Fi sensing."""

    @abstractmethod
    def get_rssi(self) -> Optional[int]:
        """Returns signal strength % (0-100) of connected AP."""
        pass

    @abstractmethod
    async def get_rtt(self, target: str = "1.1.1.1") -> Optional[float]:
        """Returns ping latency in ms (non-blocking)."""
        pass

    @abstractmethod
    def get_all_aps(self) -> list[dict]:
        """Returns a list of dicts: [{'bssid': str, 'signal': int}]."""
        pass

    def get_multi_ap_snapshot(self) -> MultiAPSnapshot:
        """Returns a full multi-AP snapshot with timing information.

        This is the primary method used by the multi-person detection
        engine for cross-viewpoint fusion.

        Returns:
            MultiAPSnapshot with all visible APs and timing data
        """
        snapshot_time = time.time()
        raw_aps = self.get_all_aps()

        ap_readings = [
            APReading(
                bssid=ap["bssid"],
                signal=ap["signal"],
                timestamp=snapshot_time,
                channel=ap.get("channel"),
                ssid=ap.get("ssid"),
            )
            for ap in raw_aps
        ]

        return MultiAPSnapshot(
            aps=ap_readings,
            snapshot_time=snapshot_time,
            primary_rssi=self.get_rssi(),
        )

    async def get_multi_ap_snapshot_with_rtt(
        self,
        rtt_targets: Optional[list[str]] = None,
    ) -> MultiAPSnapshot:
        """Returns a multi-AP snapshot including RTT measurements.

        Pings multiple targets concurrently to gather timing data
        for cross-viewpoint fusion.

        Args:
            rtt_targets: List of IP addresses to ping. Defaults to
                         common gateway addresses.

        Returns:
            MultiAPSnapshot with RTT measurements included
        """
        if rtt_targets is None:
            rtt_targets = ["1.1.1.1", "8.8.8.8"]

        snapshot = self.get_multi_ap_snapshot()

        # Gather RTT measurements concurrently
        rtt_tasks = [self.get_rtt(target) for target in rtt_targets]
        rtt_results = await asyncio.gather(*rtt_tasks, return_exceptions=True)

        # Use the first successful RTT as primary
        for result in rtt_results:
            if isinstance(result, float) and result > 0:
                snapshot.primary_rtt = result
                break

        return snapshot


class WindowsWifiReader(BaseWifiReader):
    """Wi-Fi reader for Windows using netsh and ping."""

    def get_rssi(self) -> Optional[int]:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, check=True
            )
            out_lower = result.stdout.lower()
            if "software off" in out_lower or "disconnected" in out_lower or "error" in out_lower:
                raise HardwareError("Wi-Fi Interface Disconnected, Off, or returned Error")
            match = re.search(r"Signal\s*:\s*(\d+)%", result.stdout)
            if not match:
                raise HardwareError("Could not parse Wi-Fi signal from netsh output (no matches)")
            return int(match.group(1))
        except (subprocess.CalledProcessError, HardwareError) as e:
            raise HardwareError(str(e))
        except Exception:
            return None

    async def get_rtt(self, target: str = "1.1.1.1") -> Optional[float]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-n", "1", "-w", "500", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode("cp437")
            match = re.search(r"time[=<](\d+)ms", output)
            return float(match.group(1)) if match else (0.5 if "time<1ms" in output else None)
        except Exception:
            return None

    def get_all_aps(self) -> list[dict]:
        """Scans for all visible BSSIDs using netsh with channel info."""
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True, text=True, check=True
            )
            aps = []
            current_bssid = None
            current_ssid = None
            current_channel = None

            for line in result.stdout.splitlines():
                # SSID line
                ssid_match = re.search(r"^SSID\s+\d+\s+:\s+(.+)$", line.strip())
                if ssid_match:
                    current_ssid = ssid_match.group(1).strip()
                    continue

                # BSSID line
                b_match = re.search(r"BSSID\s+\d+\s+:\s+([0-9a-fA-F:]{17})", line)
                if b_match:
                    current_bssid = b_match.group(1).upper()
                    continue

                # Signal line
                s_match = re.search(r"Signal\s+:\s+(\d+)%", line)
                if s_match and current_bssid:
                    aps.append({
                        "bssid": current_bssid,
                        "signal": int(s_match.group(1)),
                        "ssid": current_ssid,
                        "channel": current_channel,
                        "timestamp": time.time(),
                    })
                    current_bssid = None
                    current_channel = None
                    continue

                # Channel line
                ch_match = re.search(r"Channel\s+:\s+(\d+)", line)
                if ch_match:
                    current_channel = int(ch_match.group(1))

            return aps
        except Exception:
            return []


class LinuxWifiReader(BaseWifiReader):
    """Wi-Fi reader for Linux using iwconfig/nmcli."""

    def get_rssi(self) -> Optional[int]:
        try:
            result = subprocess.run(["iwconfig"], capture_output=True, text=True)
            match = re.search(r"Link Quality=(\d+)/(\d+)", result.stdout)
            if match:
                return int((int(match.group(1)) / int(match.group(2))) * 100)
            return None
        except Exception:
            return None

    async def get_rtt(self, target: str = "1.1.1.1") -> Optional[float]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "1", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()
            match = re.search(r"time=(\d+\.?\d*)", output)
            return float(match.group(1)) if match else None
        except Exception:
            return None

    def get_all_aps(self) -> list[dict]:
        """Scan APs using nmcli if available, else return empty list."""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "BSSID,SIGNAL,CHAN,SSID", "dev", "wifi", "list"],
                capture_output=True, text=True, timeout=5
            )
            aps = []
            for line in result.stdout.splitlines():
                parts = line.split(":")
                if len(parts) >= 3:
                    bssid = parts[0].upper()
                    try:
                        signal = int(parts[1])
                        channel = int(parts[2]) if parts[2].isdigit() else None
                        ssid = parts[3] if len(parts) > 3 else None
                        aps.append({
                            "bssid": bssid,
                            "signal": signal,
                            "channel": channel,
                            "ssid": ssid,
                            "timestamp": time.time(),
                        })
                    except (ValueError, IndexError):
                        continue
            return aps
        except Exception:
            return []


class MacOSWifiReader(BaseWifiReader):
    """Wi-Fi reader for macOS using airport utility."""

    _AIRPORT = (
        "/System/Library/PrivateFrameworks/Apple80211.framework"
        "/Versions/Current/Resources/airport"
    )

    def get_rssi(self) -> Optional[int]:
        try:
            result = subprocess.run(
                [self._AIRPORT, "-I"],
                capture_output=True, text=True
            )
            match = re.search(r"agrCtlRSSI:\s*(-?\d+)", result.stdout)
            if match:
                rssi_dbm = int(match.group(1))
                return max(0, min(100, int((rssi_dbm + 100) * 1.4)))
            return None
        except Exception:
            return None

    async def get_rtt(self, target: str = "1.1.1.1") -> Optional[float]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-t", "1", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()
            match = re.search(r"time=(\d+\.?\d*)", output)
            return float(match.group(1)) if match else None
        except Exception:
            return None

    def get_all_aps(self) -> list[dict]:
        """Scan APs using airport -s."""
        try:
            result = subprocess.run(
                [self._AIRPORT, "-s"],
                capture_output=True, text=True, timeout=5
            )
            aps = []
            for line in result.stdout.splitlines()[1:]:  # skip header
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        ssid = parts[0]
                        bssid = parts[1].upper()
                        rssi_dbm = int(parts[2])
                        signal = max(0, min(100, int((rssi_dbm + 100) * 1.4)))
                        channel = int(parts[3]) if len(parts) > 3 else None
                        aps.append({
                            "bssid": bssid,
                            "signal": signal,
                            "ssid": ssid,
                            "channel": channel,
                            "timestamp": time.time(),
                        })
                    except (ValueError, IndexError):
                        continue
            return aps
        except Exception:
            return []


def create_wifi_reader() -> BaseWifiReader:
    """Factory function — returns the correct reader for the current OS."""
    os_name = platform.system()
    if os_name == "Windows":
        return WindowsWifiReader()
    elif os_name == "Linux":
        return LinuxWifiReader()
    elif os_name == "Darwin":
        return MacOSWifiReader()
    else:
        raise OSError(f"Unsupported OS: {os_name}")


def get_network_devices() -> int:
    """Returns count of dynamic ARP entries (connected devices)."""
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True, check=True)
        matches = re.findall(r"dynamic", result.stdout)
        return len(matches)
    except Exception:
        return 0


# Legacy helpers kept for backward compatibility
def get_wifi_signal() -> Optional[int]:
    """Legacy helper — returns RSSI % of connected AP."""
    try:
        return create_wifi_reader().get_rssi()
    except Exception:
        return None


def get_ping_latency(target: str = "1.1.1.1") -> Optional[float]:
    """Legacy synchronous ping helper (blocks)."""
    try:
        os_name = platform.system()
        if os_name == "Windows":
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "500", target],
                capture_output=True, text=True, timeout=2
            )
            output = result.stdout
            match = re.search(r"time[=<](\d+)ms", output)
            return float(match.group(1)) if match else None
        else:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "1", target],
                capture_output=True, text=True, timeout=2
            )
            output = result.stdout
            match = re.search(r"time=(\d+\.?\d*)", output)
            return float(match.group(1)) if match else None
    except Exception:
        return None


if __name__ == "__main__":
    reader = create_wifi_reader()
    print(f"OS Detected: {platform.system()}")
    try:
        print(f"RSSI: {reader.get_rssi()}%")
        aps = reader.get_all_aps()
        print(f"Visible APs ({len(aps)}):")
        for ap in aps:
            print(f"  {ap['bssid']}  signal={ap['signal']}%  ch={ap.get('channel')}  ssid={ap.get('ssid')}")
        snapshot = reader.get_multi_ap_snapshot()
        print(f"\nMulti-AP Snapshot: {len(snapshot.aps)} APs at t={snapshot.snapshot_time:.2f}")
    except HardwareError as e:
        print(f"Hardware Error: {e}")
