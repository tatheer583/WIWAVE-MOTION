import subprocess
import re
import os

def get_wifi_signal():
    """Returns signal strength % (Macro sensor - slow updates)"""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        match = re.search(r"Signal\s*:\s*(\d+)%", result.stdout)
        return int(match.group(1)) if match else None
    except:
        return None

def get_ping_latency(target=None):
    """Returns ping latency in ms (Micro sensor - fast updates)"""
    if target is None:
        try:
            # Try to get default gateway
            res = subprocess.run(["powershell", "-NoProfile", "Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Select-Object -ExpandProperty NextHop"], capture_output=True, text=True)
            target = res.stdout.strip().splitlines()[0]
        except:
            target = "192.168.1.1"

    try:
        # Run a single ping with a short timeout (500ms)
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "500", target], 
            capture_output=True, 
            text=True,
            encoding='cp437' # Use cp437 for Windows shell output
        )
        # Look for "time=Xms" or "time<1ms"
        match = re.search(r"time[=<](\d+)ms", result.stdout)
        if match:
            return float(match.group(1))
        if "time<1ms" in result.stdout:
            return 0.5
        return None
    except:
        return None

def get_network_devices():
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True, check=True)
        matches = re.findall(r"dynamic", result.stdout)
        return len(matches)
    except:
        return 0

if __name__ == "__main__":
    print(f"Signal: {get_wifi_signal()}%")
    print(f"Ping: {get_ping_latency()}ms")
    print(f"Devices: {get_network_devices()}")
