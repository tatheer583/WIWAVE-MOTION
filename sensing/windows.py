"""Read Native Wi-Fi RSSI directly, without launching netsh per sample."""
import ctypes as c
import threading


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


class NativeWifiSource:
    source = 'native_rssi'

    def __init__(self):
        self.api = c.WinDLL('wlanapi.dll')
        self.handle = c.c_void_p()
        self.lock = threading.Lock()
        u32, ptr = c.c_uint32, c.c_void_p
        self.api.WlanOpenHandle.argtypes = [u32, ptr, c.POINTER(u32), c.POINTER(ptr)]
        self.api.WlanEnumInterfaces.argtypes = [ptr, ptr, c.POINTER(ptr)]
        self.api.WlanQueryInterface.argtypes = [ptr, c.POINTER(GUID), u32, ptr, c.POINTER(u32), c.POINTER(ptr), c.POINTER(u32)]
        self.api.WlanCloseHandle.argtypes = [ptr, ptr]
        self.api.WlanFreeMemory.argtypes = [ptr]
        for name in ('WlanOpenHandle', 'WlanEnumInterfaces', 'WlanQueryInterface', 'WlanCloseHandle'):
            getattr(self.api, name).restype = u32
        self.api.WlanFreeMemory.restype = None

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
            bssid = ':'.join(f'{b:02x}' for b in association.bssid)
            try:
                channel = self.query(interface.guid, 8, c.c_uint32).value
            except OSError:
                channel = None
            return {'source': self.source, 'rssi_dbm': rssi, 'signal': association.quality,
                    'adapter': interface.description, 'link_id': bssid, 'channel': channel,
                    'ssid': bytes(association.ssid.data[:min(32, association.ssid.length)]).decode('utf-8', errors='replace')}

    def close(self):
        with self.lock:
            if self.handle.value:
                self.api.WlanCloseHandle(self.handle, None)
                self.handle = c.c_void_p()
