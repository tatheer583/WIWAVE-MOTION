"""
Quick live smoke test against a running WiWave server.

Usage:
  python scripts/live_test.py
  python scripts/live_test.py --base http://127.0.0.1:8000 --samples 6
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def get_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="WiWave live smoke test")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1.5)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    print(f"[*] Health: {base}/api/health")
    try:
        health = get_json(f"{base}/api/health")
    except urllib.error.URLError as e:
        print(f"[FAIL] Server not reachable: {e}")
        return 1

    print(json.dumps(health, indent=2))
    if health.get("status") != "ok":
        print("[FAIL] Health status is not ok")
        return 1

    print(f"\n[*] Polling {args.samples} samples from /api/poll ...")
    statuses = []
    for i in range(args.samples):
        payload = get_json(f"{base}/api/poll")
        row = {
            "n": i + 1,
            "is_simulation": payload.get("is_simulation"),
            "signal": payload.get("signal"),
            "rtt": payload.get("rtt"),
            "status": payload.get("status"),
            "motion": payload.get("motion_detected"),
            "variance": payload.get("variance"),
        }
        statuses.append(row)
        print(
            f"  #{row['n']}: sim={row['is_simulation']} "
            f"sig={row['signal']} rtt={row['rtt']} "
            f"var={row['variance']} | {row['status']}"
        )
        if i + 1 < args.samples:
            time.sleep(args.interval)

    sims = {r["is_simulation"] for r in statuses}
    if None in sims or len([r for r in statuses if r["signal"] is None]) > 0:
        print("[FAIL] Incomplete poll payloads")
        return 1

    changing = len({(r["signal"], r["rtt"]) for r in statuses}) > 1
    if not changing:
        print("[WARN] signal/rtt did not change across samples (may be calm hardware)")
    else:
        print("[OK] Live samples are updating")

    print("[OK] Live test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
