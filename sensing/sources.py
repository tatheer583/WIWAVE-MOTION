"""Explicit source selection. Hardware errors never enable synthetic samples."""
import csv
import io
import json
import math
import os
import platform
import time


class EspCsiParser:
    """Parse header-labelled Espressif csi_recv_router serial CSV.

    Use the firmware's emitted header so ESP32 and C5/C6 layouts can differ.
    Frames with incompatible layouts are rejected rather than guessed.
    """
    def __init__(self):
        self.header = None
        self.last_packet = None

    def parse(self, line):
        if not line.startswith(('type,', 'CSI_DATA,')):
            return None
        row = next(csv.reader(io.StringIO(line)))
        if row[0] == 'type':
            if not {'mac', 'rssi', 'channel', 'len', 'first_word', 'data'}.issubset(row):
                raise ValueError('Unsupported ESP CSI header')
            self.header = row
            return None
        if self.header is None:
            raise ValueError('Waiting for CSI CSV header: reset the ESP32 after connecting')
        if len(row) != len(self.header):
            raise ValueError('CSI row does not match firmware header')
        fields = dict(zip(self.header, row))
        packet = (fields['mac'], fields.get('local_timestamp'), fields.get('id', fields.get('seq')))
        if packet == self.last_packet:
            return None
        raw = json.loads(fields['data'])
        if not isinstance(raw, list) or not 32 <= len(raw) <= 4096 or len(raw) % 2 or len(raw) != int(fields['len']):
            raise ValueError('Invalid CSI byte count')
        if any(type(v) is not int or not -128 <= v <= 127 for v in raw):
            raise ValueError('CSI values must be signed bytes')
        first_word = int(fields['first_word'])
        if first_word not in (0, 1):
            raise ValueError('Invalid CSI first-word flag')
        if first_word:
            raw = raw[4:]
        amplitudes = [math.hypot(raw[i], raw[i + 1]) for i in range(0, len(raw), 2)]
        # Retain zero subcarriers to keep dimensions stable across frames.
        if not any(amplitudes):
            raise ValueError('Empty CSI signal')
        rssi, channel = int(fields['rssi']), int(fields['channel'])
        if not -127 <= rssi <= 0 or not 1 <= channel <= 196:
            raise ValueError('Invalid CSI radio metadata')
        self.last_packet = packet
        return {'source': 'esp32_csi', 'rssi_dbm': rssi, 'signal': max(0, min(100, 2 * (rssi + 100))),
                'channel': channel, 'link_id': fields['mac'], 'amplitudes': amplitudes,
                'adapter': 'ESP32 CSI receiver', 'ssid': None}


class SerialCsiSource:
    source = 'esp32_csi'

    def __init__(self, port, baud):
        self.port, self.baud = port, baud
        self.serial = None
        self.parser = EspCsiParser()
        self.buffer = b''

    def read(self):
        import serial
        if self.serial is None:
            self.serial = serial.Serial(self.port, self.baud, timeout=0.25)
            self.parser = EspCsiParser()
            self.buffer = b''
        try:
            raw = self.serial.read_until(b'\n', size=20000)
        except serial.SerialException:
            self.close()
            raise
        self.buffer += raw
        if len(self.buffer) >= 20000:
            self.buffer = b''
            raise ValueError('CSI serial frame exceeds size limit')
        if not self.buffer.endswith(b'\n'):
            return None
        line, self.buffer = self.buffer, b''
        return self.parser.parse(line.decode('utf-8', errors='replace').strip())

    def close(self):
        if self.serial is not None:
            self.serial.close()
            self.serial = None


class DemoSource:
    source = 'simulation'

    def __init__(self):
        self.started = time.monotonic()

    def read(self):
        t = time.monotonic() - self.started
        change = 8 * math.sin(4 * t) if t % 60 > 30 else 0
        rssi = -55 + 0.3 * math.sin(t) + change
        return {'source': self.source, 'rssi_dbm': rssi, 'signal': 2 * (rssi + 100),
                'adapter': 'Synthetic demo', 'link_id': 'demo', 'ssid': 'Simulated signal', 'channel': None}

    def close(self):
        pass


class UnavailableSource:
    source = 'unavailable'

    def read(self):
        raise OSError('Native RSSI currently supports Windows. Use an ESP32 CSI serial receiver on this OS.')

    def close(self):
        pass


def create_source():
    mode = os.getenv('WIWAVE_SOURCE', 'native_rssi')
    if os.getenv('SIMULATION_MODE', '').lower() in {'true', '1', 'yes'}:
        mode = 'simulation'
    if mode == 'simulation':
        return DemoSource()
    if mode == 'esp32_csi':
        port = os.getenv('WIWAVE_CSI_PORT')
        if not port:
            raise ValueError('WIWAVE_CSI_PORT is required for esp32_csi')
        return SerialCsiSource(port, int(os.getenv('WIWAVE_CSI_BAUD', '115200')))
    if mode != 'native_rssi':
        raise ValueError('WIWAVE_SOURCE must be native_rssi, esp32_csi, or simulation')
    if platform.system() != 'Windows':
        return UnavailableSource()
    from sensing.windows import NativeWifiSource
    return NativeWifiSource()
