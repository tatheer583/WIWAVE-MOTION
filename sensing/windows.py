"""Read Native Wi-Fi RSSI and neighbor-link signal via wlanapi.dll and netsh.

The primary link is queried directly through wlanapi.dll every sample. Neighbor
access points act as extra, slow environment channels: a background thread reads
the driver's cached network list through netsh (BSSID-level Native Wi-Fi APIs
require Windows Location permission for desktop apps and are unavailable on many
machines). Neighbor telemetry therefore refreshes on the scan-cache cadence, not
per sample, and never disturbs the radio.
"""
import ctypes as c
import os
import re
import subprocess
import threading
import time


class GUID(c.Structure):
    _fields_ = [('data', c.c_ubyte * 16)]


class Interface(c.Structure):
    _fields_ = [('guid', GUID), ('description', c.c_wchar * 256), ('state', c.c_uint32)]


class SSID(c.Structure):
    _fields_ = [('length', c.c_uint32), ('data', c.c_ubyte * 32)]


class Association(c.Structure):
    _fields_ = [('ssid', SSID), ('bss_type', c.c_uint32), ('bssid', c.c_ubyte * 6),
                ('phy_type', c.c_uint32), ('phy_index', c.c_uint32), ('quality', c.c_uint32),
                ('rx_rate', c.c_uint32), ('tx_rate', c.c_uint32)]


class Connection(c.Structure):
    _fields_ = [('state', c.c_uint32), ('mode', c.c_uint32), ('profile', c.c_wchar * 256),
                ('association', Association)]


MAX_NEIGHBORS = 5
SELECTION = {'missing_s': 90.0, 'join_s': 15.0, 'max_candidates': 12}


class NativeWifiSource:
    source = 'native_rssi'

    def __init__(self):
        self.api = c.WinDLL('wlanapi.dll')
        self.handle = c.c_void_p()
        self.lock = threading.Lock()
        self.link_lock = threading.Lock()
        u32, ptr = c.c_uint32, c.c_void_p
        self.api.WlanOpenHandle.argtypes = [u32, ptr, c.POINTER(u32), c.POINTER(ptr)]
        self.api.WlanEnumInterfaces.argtypes = [ptr, ptr, c.POINTER(ptr)]
        self.api.WlanQueryInterface.argtypes = [ptr, c.POINTER(GUID), u32, ptr, c.POINTER(u32), c.POINTER(ptr), c.POINTER(u32)]
        self.api.WlanCloseHandle.argtypes = [ptr, ptr]
        self.api.WlanFreeMemory.argtypes = [ptr]
        for name in ('WlanOpenHandle', 'WlanEnumInterfaces', 'WlanQueryInterface', 'WlanCloseHandle'):
            getattr(self.api, name).restype = u32
        self.api.WlanFreeMemory.restype = None
        self.neighbors = {}
        self.selected = []
        self.own_bssid = None
        self.link_failures = 0
        self.link_poll_s = max(0.0, float(os.getenv('WIWAVE_LINK_POLL_SECONDS', '30') or 0))
        if self.link_poll_s:
            threading.Thread(target=self._neighbor_loop, daemon=True).start()

    def check(self, code):
        if code:
            hint = ' Enable Windows Location access for desktop apps if access is denied.' if code == 5 else ''
            raise OSError(code, f'Windows Wi-Fi query failed ({code}).{hint}')

    def query(self, guid, opcode, structure):
        size, kind, memory = c.c_uint32(), c.c_uint32(), c.c_void_p()
        self.check(self.api.WlanQueryInterface(self.handle, c.byref(guid), opcode, None,
                                              c.byref(size), c.byref(memory), c.byref(kind)))
        try:
            if size.value < c.sizeof(structure):
                raise OSError('Wi-Fi driver returned a truncated response')
            return structure.from_buffer_copy(c.string_at(memory, c.sizeof(structure)))
        finally:
            self.api.WlanFreeMemory(memory)

    @staticmethod
    def visible_networks():
        """Parse the driver's cached BSSID list through netsh. Reads the cache
        only; no scan is triggered and the link is not disturbed. Field order
        differs across Windows builds (Signal may precede Channel), so each
        BSSID block is finalized before the next starts."""
        result = subprocess.run(['netsh', 'wlan', 'show', 'networks', 'mode=bssid'],
                                capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            raise OSError('netsh network list failed')
        networks = []
        current = {}
        ssid = None

        def flush():
            if current.get('bssid') and current.get('signal') is not None:
                networks.append({**current, 'ssid': ssid})
            current.clear()

        for line in result.stdout.splitlines():
            stripped = line.strip()
            ssid_match = re.fullmatch(r'SSID \d+ : (.*)', stripped)
            bssid_match = re.search(r'BSSID \d+\s*:\s*([0-9a-fA-F:]{17})', stripped)
            if ssid_match or bssid_match:
                flush()
                if ssid_match:
                    ssid = ssid_match.group(1)
                else:
                    current['bssid'] = bssid_match.group(1).upper()
                continue
            if not current.get('bssid'):
                continue
            channel_match = re.search(r'Channel\s*:\s*(\d+)', stripped)
            if channel_match and current.get('channel') is None:
                current['channel'] = int(channel_match.group(1))
            signal_match = re.search(r'Signal\s*:\s*(\d+)%', stripped)
            if signal_match and current.get('signal') is None:
                current['signal'] = int(signal_match.group(1))
        flush()
        return networks

    def _neighbor_loop(self):
        while True:
            started = time.monotonic()
            try:
                networks = self.visible_networks()
                now = time.monotonic()
                with self.link_lock:
                    self._update_links(networks, now)
                self.link_failures = 0
            except Exception:
                self.link_failures += 1
                if self.link_failures > 10:
                    with self.link_lock:
                        self.neighbors, self.selected = {}, []
                    self.link_failures = 0
            time.sleep(max(5.0, self.link_poll_s - (time.monotonic() - started)))

    def _update_links(self, networks, now):
        """Keep a stable neighbor set: drop a link only after it has been missing
        for a while, and add new links only after they have been seen long enough."""
        for link in networks:
            record = self.neighbors.get(link['bssid'])
            if record is None:
                self.neighbors[link['bssid']] = {**link, 'last_seen': now, 'first_seen': now}
            else:
                record.update(link, last_seen=now)
        if len(self.neighbors) > 64:
            stale = sorted(self.neighbors.items(), key=lambda item: item[1]['last_seen'])
            for bssid, _ in stale[:len(self.neighbors) - 64]:
                del self.neighbors[bssid]
        self.selected = [b for b in self.selected
                         if b != self.own_bssid and self.neighbors.get(b)
                         and now - self.neighbors[b]['last_seen'] < SELECTION['missing_s']]
        candidates = sorted((link for link in networks if link['bssid'] != self.own_bssid),
                            key=lambda link: link['signal'], reverse=True)[:SELECTION['max_candidates']]
        for link in candidates:
            if len(self.selected) >= MAX_NEIGHBORS:
                break
            if link['bssid'] not in self.selected \
                    and now - self.neighbors[link['bssid']]['first_seen'] >= SELECTION['join_s']:
                self.selected.append(link['bssid'])

    def read(self):
        with self.lock:
            if not self.handle.value:
                version = c.c_uint32()
                self.check(self.api.WlanOpenHandle(2, None, c.byref(version), c.byref(self.handle)))
            memory = c.c_void_p()
            self.check(self.api.WlanEnumInterfaces(self.handle, None, c.byref(memory)))
            try:
                count = c.c_uint32.from_address(memory.value).value
                interfaces = (Interface * min(count, 64)).from_address(memory.value + 8)
                connected = [Interface.from_buffer_copy(i) for i in interfaces if i.state == 1]
            finally:
                self.api.WlanFreeMemory(memory)
            if not connected:
                raise OSError('No connected Wi-Fi adapter. Connect to your router and retry.')
            interface = connected[0]
            rssi = self.query(interface.guid, 0x10000102, c.c_int32).value
            if not -127 <= rssi <= 0:
                raise OSError('Wi-Fi driver returned an invalid RSSI')
            connection = self.query(interface.guid, 7, Connection)
            association = connection.association
            bssid = ':'.join(f'{b:02X}' for b in association.bssid)
            self.own_bssid = bssid
            try:
                channel = self.query(interface.guid, 8, c.c_uint32).value
            except OSError:
                channel = None
            now = time.monotonic()
            with self.link_lock:
                links = []
                for b in self.selected:
                    record = self.neighbors.get(b)
                    if record is None or record.get('signal') is None:
                        continue
                    # netsh reports a 0-100 quality percentage; express it in the
                    # app's dBm convention (signal/2 - 100) so all channels share units.
                    links.append({'bssid': b, 'rssi_dbm': round(record['signal'] / 2 - 100, 1),
                                  'signal': record['signal'], 'channel': record.get('channel'),
                                  'ssid': record.get('ssid'),
                                  'age_s': round(now - record['last_seen'], 1)})
            ssid_bytes = bytes(association.ssid.data[:min(32, association.ssid.length)])
            return {'source': self.source, 'rssi_dbm': rssi, 'signal': association.quality,
                    'adapter': interface.description, 'link_id': bssid, 'channel': channel,
                    'ssid': ssid_bytes.decode('utf-8', errors='replace'), 'links': links}

    def close(self):
        with self.lock:
            if self.handle.value:
                self.api.WlanCloseHandle(self.handle, None)
                self.handle = c.c_void_p()
