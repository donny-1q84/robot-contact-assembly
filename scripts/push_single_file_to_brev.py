#!/usr/bin/env python3
"""Push a single local file into the Brev project repo without relying on brev copy."""

from __future__ import annotations

import argparse
import base64
import pathlib
import shlex
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("local_file", help="Absolute or repo-relative file to upload.")
    parser.add_argument(
        "--env-name",
        default="isaac-l40s",
        help="Brev instance name.",
    )
    parser.add_argument(
        "--remote-root",
        default="/home/ubuntu/projects/robot-contact-assembly/repo/robot-contact-assembly",
        help="Remote project root inside the Brev instance.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(pathlib.Path(__file__).resolve().parents[1]),
        help="Local repo root used to compute remote relative paths.",
    )
    args = parser.parse_args()

    repo_root = pathlib.Path(args.repo_root).resolve()
    local_path = pathlib.Path(args.local_file)
    if not local_path.is_absolute():
        local_path = repo_root / local_path
    local_path = local_path.resolve()

    if not local_path.is_file():
        raise FileNotFoundError(f"local file not found: {local_path}")

    rel_path = local_path.relative_to(repo_root).as_posix()
    remote_path = f"{args.remote_root}/{rel_path}"
    payload = base64.b64encode(local_path.read_bytes()).decode()
    mode = local_path.stat().st_mode & 0o777

    python_expr = (
        "import base64,os,pathlib;"
        f"pathlib.Path({remote_path!r}).parent.mkdir(parents=True, exist_ok=True);"
        f"pathlib.Path({remote_path!r}).write_bytes(base64.b64decode({payload!r}));"
        f"os.chmod({remote_path!r}, {mode})"
    )
    remote_cmd = f"bash -lc {shlex.quote('python3 -c ' + shlex.quote(python_expr))}"

    completed = subprocess.run(
        ["/Users/Shenghan/bin/brev", "exec", args.env_name, remote_cmd],
        text=True,
    )
    if completed.returncode != 0:
        return completed.returncode

    print(f"[push-single-file] uploaded {rel_path} -> {args.env_name}:{remote_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
