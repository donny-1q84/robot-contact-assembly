from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from send_live_app_script import send_script


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the scripted peg-in-hole live baseline in the current Isaac Sim app.")
    parser.add_argument("--iterations", type=int, default=60, help="Number of incremental control steps to send.")
    parser.add_argument("--sleep", type=float, default=0.05, help="Sleep time between step injections.")
    parser.add_argument("--host", default="127.0.0.1", help="Local forwarded code-execution host.")
    parser.add_argument("--port", type=int, default=8226, help="Local forwarded code-execution port.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_path = Path(__file__).with_name("live_step_scripted_baseline.py")
    script = script_path.read_text()

    for index in range(args.iterations):
        reply = send_script(script, host=args.host, port=args.port)
        status = reply.get("status", "unknown")
        output = reply.get("output", "").strip()
        if status != "ok":
            print(json.dumps(reply, indent=2))
            return 1
        print(f"[{index + 1:03d}/{args.iterations:03d}] {output}")
        time.sleep(args.sleep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
