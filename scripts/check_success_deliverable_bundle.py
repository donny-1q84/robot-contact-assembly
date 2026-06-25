#!/usr/bin/env python3
"""Validate a peg-in-hole success deliverable as one evidence bundle.

This gate is intentionally stricter than checking a trace or a video alone. A
publishable success bundle must prove semantic insertion, final-contact safety,
trace-frame consistency, nonempty video media, checksum integrity, and paid
instance cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_SIBLINGS = (
    "../2026-06-21-peg-in-hole-success-trace/video_trace.json",
    "video_trace.json",
)
DEFAULT_VIDEO_NAMES = (
    "isaac_trace_replay_trimmed.mp4",
    "isaac_trace_replay_raw.mp4",
    "peg_in_hole_trace_render.mp4",
)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _run(args: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode == 0, result.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_from_checksum_entry(bundle: Path, entry_path: str) -> Path:
    raw = Path(entry_path)
    if raw.is_absolute():
        return raw
    if entry_path.startswith("./"):
        return bundle / entry_path[2:]
    repo_relative = REPO_ROOT / raw
    if repo_relative.exists():
        return repo_relative
    return bundle / raw


def verify_checksums(bundle: Path) -> dict[str, Any]:
    checksum_path = bundle / "SHA256SUMS.txt"
    if not checksum_path.is_file():
        raise RuntimeError(f"missing checksum manifest: {_rel(checksum_path)}")

    checked: list[str] = []
    failures: list[str] = []
    for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            failures.append(f"line {line_number}: malformed checksum entry")
            continue
        expected, entry_path = parts
        file_path = _path_from_checksum_entry(bundle, entry_path.strip())
        if not file_path.is_file():
            failures.append(f"line {line_number}: missing file {entry_path}")
            continue
        actual = _sha256(file_path)
        checked.append(_rel(file_path))
        if actual != expected:
            failures.append(
                f"line {line_number}: checksum mismatch for {entry_path} expected={expected} actual={actual}"
            )
    if failures:
        raise RuntimeError("; ".join(failures))
    if not checked:
        raise RuntimeError(f"checksum manifest has no file entries: {_rel(checksum_path)}")
    return {"checked_files": checked, "count": len(checked)}


def _trace_from_replay_summary(bundle: Path) -> Path | None:
    summary_path = bundle / "replay_summary_recovered.json"
    if not summary_path.is_file():
        return None
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    source = summary.get("source_trace_json")
    if not isinstance(source, str) or not source:
        return None
    candidate = REPO_ROOT / source
    return candidate if candidate.is_file() else None


def discover_trace(bundle: Path, explicit_trace: Path | None) -> Path:
    if explicit_trace is not None:
        trace = explicit_trace if explicit_trace.is_absolute() else REPO_ROOT / explicit_trace
        if not trace.is_file():
            raise RuntimeError(f"explicit source trace is missing: {_rel(trace)}")
        return trace

    for relative in DEFAULT_TRACE_SIBLINGS:
        candidate = (bundle / relative).resolve()
        if candidate.is_file():
            return candidate

    replay_source = _trace_from_replay_summary(bundle)
    if replay_source is not None:
        return replay_source

    raise RuntimeError(
        "could not locate source trace; pass --trace-json or include video_trace.json / sibling success trace"
    )


def discover_video(bundle: Path, explicit_video: Path | None) -> Path:
    if explicit_video is not None:
        video = explicit_video if explicit_video.is_absolute() else REPO_ROOT / explicit_video
        if not video.is_file():
            raise RuntimeError(f"explicit video is missing: {_rel(video)}")
        return video

    for name in DEFAULT_VIDEO_NAMES:
        candidate = bundle / name
        if candidate.is_file():
            return candidate

    raise RuntimeError(
        "could not locate success video; expected one of: " + ", ".join(DEFAULT_VIDEO_NAMES)
    )


def verify_video(video: Path) -> dict[str, Any]:
    ok, output = _run(
        [
            "ffprobe",
            "-hide_banner",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,nb_frames,duration,codec_name",
            "-of",
            "json",
            str(video),
        ]
    )
    if not ok:
        raise RuntimeError(f"ffprobe failed for {_rel(video)}:\n{output}")
    try:
        payload = json.loads(output)
        stream = payload["streams"][0]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"ffprobe did not return a usable video stream for {_rel(video)}: {exc}") from exc

    duration = float(stream.get("duration") or 0.0)
    try:
        frames = int(stream.get("nb_frames") or 0)
    except (TypeError, ValueError):
        frames = 0
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if duration <= 0.0 or frames <= 0 or width <= 0 or height <= 0:
        raise RuntimeError(
            f"video metadata is not positive for {_rel(video)}: "
            f"duration={duration} frames={frames} width={width} height={height}"
        )
    return {
        "codec_name": stream.get("codec_name"),
        "duration": duration,
        "frames": frames,
        "width": width,
        "height": height,
    }


def require_cleanup_snapshot(bundle: Path) -> dict[str, Any]:
    safety_path = bundle / "brev_paid_safety_status.txt"
    if not safety_path.is_file():
        raise RuntimeError(f"missing Brev safety snapshot: {_rel(safety_path)}")
    text = safety_path.read_text(encoding="utf-8", errors="replace")
    required = (
        "SAFE_NO_VISIBLE_PAID_INSTANCE",
        "visible_instances=0",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"Brev safety snapshot missing markers {missing}: {_rel(safety_path)}")
    return {"path": _rel(safety_path), "markers": list(required)}


def run_trace_gate(label: str, args: list[str]) -> dict[str, Any]:
    ok, output = _run(args)
    if not ok:
        raise RuntimeError(f"{label} failed:\n{output}")
    return {"label": label, "output": output.strip().splitlines()[:8]}


def validate_bundle(bundle: Path, *, trace_json: Path | None, video_path: Path | None) -> dict[str, Any]:
    if not bundle.is_dir():
        raise RuntimeError(f"bundle directory is missing: {_rel(bundle)}")

    trace = discover_trace(bundle, trace_json)
    video = discover_video(bundle, video_path)
    checksums = verify_checksums(bundle)
    video_metadata = verify_video(video)
    cleanup = require_cleanup_snapshot(bundle)

    gates = [
        run_trace_gate(
            "peg-video-candidate",
            [sys.executable, "scripts/check_peg_in_hole_video_candidate.py", str(trace)],
        ),
        run_trace_gate(
            "final-contact-boundary",
            [sys.executable, "scripts/check_final_contact_boundary_diagnostic.py", str(trace)],
        ),
        run_trace_gate(
            "trace-frame-alignment",
            [sys.executable, "scripts/audit_trace_frame_alignment.py", str(trace)],
        ),
    ]

    return {
        "bundle": _rel(bundle),
        "trace": _rel(trace),
        "video": _rel(video),
        "checksums": checksums,
        "video_metadata": video_metadata,
        "cleanup": cleanup,
        "gates": gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Deliverable bundle directory to validate.")
    parser.add_argument("--trace-json", type=Path, help="Override source trace JSON path.")
    parser.add_argument("--video", type=Path, help="Override success video path.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    try:
        report = validate_bundle(args.bundle.resolve(), trace_json=args.trace_json, video_path=args.video)
    except RuntimeError as exc:
        if args.json:
            print(json.dumps({"pass": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"[success-bundle] FAIL: {args.bundle}")
            print(f"  error: {exc}")
        return 1

    if args.json:
        print(json.dumps({"pass": True, "report": report}, indent=2, sort_keys=True))
    else:
        print(f"[success-bundle] PASS: {args.bundle}")
        print(f"  trace: {_rel(Path(report['trace']))}")
        print(f"  video: {_rel(Path(report['video']))}")
        video_metadata = report["video_metadata"]
        print(
            "  video_metadata: "
            f"{video_metadata['width']}x{video_metadata['height']} "
            f"frames={video_metadata['frames']} duration={video_metadata['duration']}"
        )
        print(f"  checksums: {report['checksums']['count']} files")
        print("  cleanup: SAFE_NO_VISIBLE_PAID_INSTANCE")
        for gate in report["gates"]:
            print(f"  gate: {gate['label']} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
