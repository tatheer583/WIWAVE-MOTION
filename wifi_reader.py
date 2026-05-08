import subprocess
import re
import platform
import asyncio
from abc import ABC, abstractmethod

class HardwareError(Exception):
    """Raised when the Wi-Fi interface is missing or disconnected."""
    pass

class BaseWifiReader(ABC):
    """Abstract Base Class for multi-platform Wi-Fi sensing."""
    
    @abstractmethod
    def get_rssi(self):
        """Returns signal strength % (0-100)."""
        pass

    @abstractmethod
    async def get_rtt(self, target="1.1.1.1"):
        """Returns ping latency in ms (non-blocking)."""
        pass

    @abstractmethod
    def get_all_aps(self):
        """Returns a list of dicts: [{'bssid': str, 'signal': int}] for all visible APs."""
        pass

class WindowsWifiReader(BaseWifiReader):
    def get_rssi(self):
        try:
            result = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, check=True)
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

    async def get_rtt(self, target="1.1.1.1"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-n", "1", "-w", "500", target,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode('cp437')
            match = re.search(r"time[=<](\d+)ms", output)
            return float(match.group(1)) if match else (0.5 if "time<1ms" in output else None)
        except:
            return None

    def get_all_aps(self):
        """Scans for all visible BSSIDs using netsh."""
        try:
            result = subprocess.run(["netsh", "wlan", "show", "networks", "mode=bssid"], capture_output=True, text=True, check=True)
            aps = []
            current_bssid = None
            for line in result.stdout.splitlines():
                b_match = re.search(r"BSSID\s+\d+\s+:\s+([0-9a-fA-F:]{17})", line)
                if b_match:
                    current_bssid = b_match.group(1).upper()
                    continue
                s_match = re.search(r"Signal\s+:\s+(\d+)%", line)
                if s_match and current_bssid:
                    aps.append({"bssid": current_bssid, "signal": int(s_match.group(1))})
                    current_bssid = None
            return aps
        except:
            return []

class LinuxWifiReader(BaseWifiReader):
    def get_rssi(self):
        try:
            result = subprocess.run(["iwconfig"], capture_output=True, text=True)
            match = re.search(r"Link Quality=(\d+)/(\d+)", result.stdout)
            if match:
                return int((int(match.group(1)) / int(match.group(2))) * 100)
            return None
        except:
            return None

    async def get_rtt(self, target="1.1.1.1"):
        try:
            proc = await asyncio.create_subprocess_exec("ping", "-c", "1", "-W", "1", target, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            output = stdout.decode()
            match = re.search(r"time=(\d+\.?\d*)", output)
            return float(match.group(1)) if match else None
        except:
            return None

    def get_all_aps(self):
        # Linux implementation (requires nmcli or scanning tools)
        return []

class MacOSWifiReader(BaseWifiReader):
    def get_rssi(self):
        try:
            cmd = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I"
            result = subprocess.run(cmd.split(), capture_output=True, text=True)
            match = re.search(r"agrCtlRSSI:\s*(-?\d+)", result.stdout)
            if match:
                rssi_dbm = int(match.group(1))
                return max(0, min(100, int((rssi_dbm + 100) * 1.4)))
            return None
        except:
            return None

    async def get_rtt(self, target="1.1.1.1"):
        try:
            proc = await asyncio.create_subprocess_exec("ping", "-c", "1", "-t", "1", target, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            output = stdout.decode()
            match = re.search(r"time=(\d+\.?\d*)", output)
            return float(match.group(1)) if match else None
        except:
            return None

    def get_all_aps(self):
        # MacOS implementation (using airport -s)
        return []

def create_wifi_reader() -> BaseWifiReader:
    os_name = platform.system()
    if os_name == "Windows": return WindowsWifiReader()
    elif os_name == "Linux": return LinuxWifiReader()
    elif os_name == "Darwin": return MacOSWifiReader()
    else: raise OSError(f"Unsupported OS: {os_name}")

def get_network_devices():
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True, check=True)
        matches = re.findall(r"dynamic", result.stdout)
        return len(matches)
    except:
        return 0

if __name__ == "__main__":
    reader = create_wifi_reader()
    print(f"OS Detected: {platform.system()}")
    try:
        print(f"RSSI: {reader.get_rssi()}%")
        print(f"All APs: {reader.get_all_aps()}")
    except HardwareError as e:
        print(f"Hardware Error: {e}")
