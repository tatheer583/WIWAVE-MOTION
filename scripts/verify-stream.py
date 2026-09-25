"""Inspect a running WiWave stream without modifying calibration or sessions."""
import argparse
import asyncio
import json
import time
from urllib.request import urlopen
import websockets


async def verify(base, seconds):
    sequences, rates, rssi, ages, states = set(), [], [], [], set()
    deadline = time.monotonic() + seconds
    first = None
    async with websockets.connect(base.replace('http', 'ws', 1) + '/ws/radar') as socket:
        while time.monotonic() < deadline:
            payload = json.loads(await asyncio.wait_for(socket.recv(), 3))
            first = first or payload
            assert payload['person_count'] is None and payload['distance'] is None
            if payload['system_status'] == 'ok':
                sequences.add(payload['sequence'])
                rssi.append(payload['rssi_dbm'])
                rates.append(payload['read_rate_hz'])
                ages.append(payload['sample_age_ms'])
                states.add(payload['state'])
    with urlopen(base + '/api/health', timeout=3) as response:
        health = json.load(response)
    result = {'source': first['source'], 'is_simulation': first['is_simulation'],
              'duration_seconds': seconds, 'distinct_samples': len(sequences),
              'rssi_min_dbm': min(rssi) if rssi else None, 'rssi_max_dbm': max(rssi) if rssi else None,
              'mean_read_rate_hz': round(sum(rates) / len(rates), 2) if rates else 0,
              'max_sample_age_ms': max(ages) if ages else None,
              'states': sorted(states), 'health': health}
    print(json.dumps(result, indent=2))
    if not rssi or health['status'] != 'ok':
        raise SystemExit('No healthy sensor stream was observed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--seconds', type=float, default=30)
    args = parser.parse_args()
    asyncio.run(verify(args.base, args.seconds))
