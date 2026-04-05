"""Send a Python script into a running Isaac Sim app through the VS Code extension port."""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script_path", type=Path, help="Path to the Python file to execute inside Isaac Sim.")
    parser.add_argument("--host", default="127.0.0.1", help="Local forwarded code-execution host.")
    parser.add_argument("--port", type=int, default=8226, help="Local forwarded code-execution port.")
    return parser.parse_args()


def send_script(script: str, host: str = "127.0.0.1", port: int = 8226) -> dict:
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(script.encode())
        sock.settimeout(5)
        chunks: list[bytes] = []
        while True:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)

    if not chunks:
        return {"status": "unknown", "output": ""}

    return json.loads(b"".join(chunks).decode())


def main() -> int:
    args = parse_args()
    script = args.script_path.read_text()
    print(json.dumps(send_script(script, host=args.host, port=args.port)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
