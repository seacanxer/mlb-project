import argparse
import os
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from server import execute_live_scan_sync, load_config


def run_worker_loop(interval_minutes: int = 15, once: bool = False):
    now_str = datetime.now(timezone.utc).isoformat()
    print(f"[{now_str}] 🚀 FC Betting Machine worker started.")
    print(f"Interval: {interval_minutes} minutes | Run once: {once}")

    while True:
        start_ts = time.time()
        now_str = datetime.now(timezone.utc).isoformat()
        print(f"\n[{now_str}] 📡 Triggering live odds scan...")
        try:
            execute_live_scan_sync()
            cfg = load_config()
            now_str = datetime.now(timezone.utc).isoformat()
            print(f"[{now_str}] ✅ Scan complete. Processed in {time.time() - start_ts:.2f}s")
        except Exception as e:
            now_str = datetime.now(timezone.utc).isoformat()
            print(f"[{now_str}] ❌ Worker scan error: {e}")

        if once:
            print("Finished single worker execution. Exiting.")
            break

        sleep_seconds = interval_minutes * 60
        print(f"Sleeping for {interval_minutes} minutes until next scheduled scan...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Football Betting Machine Background Ingestion Worker")
    parser.add_argument("--interval", type=int, default=15, help="Scan interval in minutes (default: 15)")
    parser.add_argument("--once", action="store_true", help="Run once and exit immediately")
    args = parser.parse_args()

    run_worker_loop(interval_minutes=args.interval, once=args.once)
