#!/usr/bin/env python3
"""Audit whether peg/socket contact physics is real in recorded traces.

Both the peg and the socket guide walls are spawned with
``kinematic_enabled=True`` and the peg is teleported to the hand pose by
``sync_peg_to_hand`` each step. PhysX does not resolve kinematic-kinematic
pairs, so the guide walls may never have produced a reaction force. This
audit reconstructs the physical peg cylinder per step from trace data and
checks it against the authored wall boxes:

- "silent penetration": peg overlaps a wall volume while the contact
  sensor reads ~0 force (impossible if wall collision were active)
- "free-space contact": contact sensor reads force while the peg is far
  from every wall (force source cannot be the socket)
- correlation between geometric wall penetration and the contact reading
- whether the peg lower end ever truly entered the guide channel, and the
  classic two-point jamming bound for the steps that did

Pure stdlib; reads plain trace JSONs and Launchable result tarballs.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import tarfile
from pathlib import Path

PEG_RADIUS_M = 0.010
PEG_LENGTH_M = 0.080
SOCKET_GUIDE_CLEARANCE_M = 0.0015
SOCKET_GUIDE_WALL_THICKNESS_M = 0.0060
SOCKET_GUIDE_DEPTH_M = 0.060

TRACE_MEMBER_RE = re.compile(r"seed_\d+_trace[^/]*\.json$")

PEN_CONTACT_THRESHOLD = 0.10
FREE_CONTACT_THRESHOLD = 0.30
PEN_SILENT_MIN_M = 0.002
FREE_CLEARANCE_MIN_M = 0.002
AXIS_SAMPLES = 81


def quat_rotate(quat, vec, order):
    if order == "wxyz":
        w, x, y, z = quat
    else:
        x, y, z, w = quat
    t = (
        2.0 * (y * vec[2] - z * vec[1]),
        2.0 * (z * vec[0] - x * vec[2]),
        2.0 * (x * vec[1] - y * vec[0]),
    )
    return (
        vec[0] + w * t[0] + y * t[2] - z * t[1],
        vec[1] + w * t[1] + z * t[0] - x * t[2],
        vec[2] + w * t[2] + x * t[1] - y * t[0],
    )


def detect_quat_order(rows):
    """Pick the quaternion component order that reproduces the logged rot."""
    errors = {"xyzw": [], "wxyz": []}
    for row in rows[:: max(1, len(rows) // 50)]:
        quat = row.get("physical_tip_quat_w")
        socket_quat = row.get("socket_quat_w")
        rot = row.get("rot")
        if quat is None or socket_quat is None or rot is None:
            continue
        for order in errors:
            peg_axis = quat_rotate(quat, (0.0, 0.0, 1.0), order)
            sock_axis = quat_rotate(socket_quat, (0.0, 0.0, 1.0), order)
            dot = abs(sum(a * b for a, b in zip(peg_axis, sock_axis)))
            angle = math.acos(max(-1.0, min(1.0, dot)))
            errors[order].append(abs(angle - rot))
    if not errors["xyzw"]:
        return None, None
    means = {order: sum(v) / len(v) for order, v in errors.items()}
    order = min(means, key=means.get)
    return order, means[order]


def wall_boxes(socket_xy, inner_half_width, thickness):
    sx, sy = socket_xy
    ihw, t = inner_half_width, thickness
    ohw = ihw + t
    return {
        "left": (sx - ohw, sx - ihw, sy - ohw, sy + ohw),
        "right": (sx + ihw, sx + ohw, sy - ohw, sy + ohw),
        "front": (sx - ihw, sx + ihw, sy - ohw, sy - ihw),
        "back": (sx - ihw, sx + ihw, sy + ihw, sy + ohw),
    }


def max_wall_penetration(upper, lower, boxes, z_bottom, z_top):
    """Max cylinder-into-wall penetration (m); negative = clearance."""
    best = None
    for i in range(AXIS_SAMPLES):
        f = i / (AXIS_SAMPLES - 1.0)
        p = tuple(upper[j] + f * (lower[j] - upper[j]) for j in range(3))
        if not (z_bottom <= p[2] <= z_top):
            continue
        for box in boxes.values():
            dx = max(box[0] - p[0], 0.0, p[0] - box[1])
            dy = max(box[2] - p[1], 0.0, p[1] - box[3])
            pen = PEG_RADIUS_M - math.hypot(dx, dy)
            if best is None or pen > best:
                best = pen
    return best


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0.0 or vy <= 0.0:
        return None
    return cov / math.sqrt(vx * vy)


def analyze_trace(rows, label, frame_convention):
    order, order_err = detect_quat_order(rows)
    if order is None:
        return {"trace": label, "status": "skipped", "reason": "missing tip quat/rot fields"}

    first = next((r for r in rows if r.get("socket_pos_w")), None)
    if first is None:
        return {"trace": label, "status": "skipped", "reason": "missing socket_pos_w"}
    socket_pos = first["socket_pos_w"]
    clearance = first.get("socket_guide_clearance", SOCKET_GUIDE_CLEARANCE_M)
    inner_half_width = PEG_RADIUS_M + clearance
    boxes = wall_boxes((socket_pos[0], socket_pos[1]), inner_half_width, SOCKET_GUIDE_WALL_THICKNESS_M)
    if frame_convention == "centered":
        z_bottom = socket_pos[2] - 0.5 * SOCKET_GUIDE_DEPTH_M
        z_top = socket_pos[2] + 0.5 * SOCKET_GUIDE_DEPTH_M
    else:  # frame-at-bottom
        z_bottom = socket_pos[2]
        z_top = socket_pos[2] + SOCKET_GUIDE_DEPTH_M

    silent_pen_steps = 0
    silent_pen_max = 0.0
    free_contact_steps = 0
    free_contact_max = 0.0
    contact_steps = 0
    pen_series = []
    contact_series = []
    engaged_steps = 0
    engaged_min_tilt = None
    engaged_records = []
    lower_end_min_height = None
    near_depth_pen_steps = 0
    near_depth_steps = 0
    analyzed = 0

    for row in rows:
        tip = row.get("physical_tip_pos_w")
        quat = row.get("physical_tip_quat_w")
        contact = row.get("contact_force_magnitude")
        if tip is None or quat is None or contact is None:
            continue
        analyzed += 1
        axis = quat_rotate(quat, (0.0, 0.0, 1.0), order)
        # logged tip is the gripped upper end; the inserting end is one peg
        # length farther along local +z (which points away from the hand)
        if axis[2] > 0.0:
            axis = tuple(-a for a in axis)
        lower = tuple(tip[j] + PEG_LENGTH_M * axis[j] for j in range(3))
        pen = max_wall_penetration(tip, lower, boxes, z_bottom, z_top)
        height = lower[2] - z_bottom
        if lower_end_min_height is None or height < lower_end_min_height:
            lower_end_min_height = height

        if contact >= PEN_CONTACT_THRESHOLD:
            contact_steps += 1
        if pen is not None:
            pen_series.append(max(pen, -0.02))
            contact_series.append(contact)
            if pen >= PEN_SILENT_MIN_M and contact < PEN_CONTACT_THRESHOLD:
                silent_pen_steps += 1
                silent_pen_max = max(silent_pen_max, pen)
        if (pen is None or pen < -FREE_CLEARANCE_MIN_M) and contact >= FREE_CONTACT_THRESHOLD:
            free_contact_steps += 1
            free_contact_max = max(free_contact_max, contact)

        axial = row.get("axial")
        if axial is not None and axial < 0.08:
            near_depth_steps += 1
            if pen is not None and pen >= PEN_SILENT_MIN_M:
                near_depth_pen_steps += 1

        # true engagement: inserting end inside the channel interior
        lat = math.hypot(lower[0] - socket_pos[0], lower[1] - socket_pos[1])
        if z_bottom <= lower[2] <= z_top and lat < inner_half_width:
            engaged_steps += 1
            depth = z_top - lower[2]
            tilt = row.get("rot")
            if tilt is not None:
                if engaged_min_tilt is None or tilt < engaged_min_tilt:
                    engaged_min_tilt = tilt
                if depth > 1e-4:
                    bound = math.atan(2.0 * clearance / depth)
                    engaged_records.append(
                        {"step": row.get("step"), "depth_m": round(depth, 4),
                         "tilt_rad": round(tilt, 4), "two_point_bound_rad": round(bound, 4)}
                    )

    corr = pearson(pen_series, contact_series)
    if silent_pen_steps > 10 and free_contact_steps > 10:
        verdict = "no_wall_physics"
    elif silent_pen_steps > 10:
        verdict = "walls_inactive"
    elif free_contact_steps > 10:
        verdict = "contact_signal_not_socket"
    elif analyzed == 0:
        verdict = "no_data"
    else:
        verdict = "consistent"

    return {
        "trace": label,
        "status": "ok",
        "frame_convention": frame_convention,
        "quat_order": order,
        "quat_order_mean_rot_residual": round(order_err, 5) if order_err is not None else None,
        "steps_analyzed": analyzed,
        "socket_pos_w": [round(v, 4) for v in socket_pos],
        "channel_z_range_w": [round(z_bottom, 4), round(z_top, 4)],
        "contact_steps": contact_steps,
        "silent_penetration_steps": silent_pen_steps,
        "silent_penetration_max_m": round(silent_pen_max, 4),
        "free_space_contact_steps": free_contact_steps,
        "free_space_contact_max_force": round(free_contact_max, 3),
        "penetration_contact_correlation": round(corr, 3) if corr is not None else None,
        "near_depth_steps": near_depth_steps,
        "near_depth_penetration_steps": near_depth_pen_steps,
        "lower_end_min_height_above_channel_bottom_m": (
            round(lower_end_min_height, 4) if lower_end_min_height is not None else None
        ),
        "true_engagement_steps": engaged_steps,
        "true_engagement_min_tilt_rad": (
            round(engaged_min_tilt, 4) if engaged_min_tilt is not None else None
        ),
        "engagement_samples": engaged_records[:5],
        "verdict": verdict,
    }


def iter_traces(paths):
    for path in paths:
        if path.suffix == ".json":
            try:
                with open(path) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                yield str(path), None, f"unreadable: {exc}"
                continue
            rows = data.get("steps") if isinstance(data, dict) else data
            yield str(path), rows, None
        elif path.name.endswith(".tar.gz"):
            try:
                with tarfile.open(path) as tf:
                    members = [m for m in tf.getmembers() if TRACE_MEMBER_RE.search(m.name)]
                    for member in members:
                        f = tf.extractfile(member)
                        if f is None:
                            continue
                        try:
                            data = json.load(f)
                        except json.JSONDecodeError as exc:
                            yield f"{path.name}::{member.name}", None, f"unreadable: {exc}"
                            continue
                        rows = data.get("steps") if isinstance(data, dict) else data
                        yield f"{path.name}::{member.name}", rows, None
            except (tarfile.TarError, OSError, EOFError) as exc:
                yield str(path), None, f"unreadable archive: {exc}"


def default_inputs(repo_root):
    paths = []
    paths.extend(sorted((repo_root / "artifacts" / "launchable_logs").glob("*.tar.gz")))
    paths.extend(sorted((repo_root / "artifacts" / "evaluations" / "scripted").glob("*/seed_*_trace.json")))
    paths.extend(sorted((repo_root / "artifacts" / "preload_traces").glob("*trace*.json")))
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path,
                        help="trace JSONs or result tarballs (default: scan artifacts/)")
    parser.add_argument("--frame-convention", choices=["centered", "frame-at-bottom", "both"],
                        default="centered",
                        help="where the logged socket frame sits in the guide channel")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    inputs = args.inputs or default_inputs(repo_root)
    conventions = ["centered", "frame-at-bottom"] if args.frame_convention == "both" else [args.frame_convention]

    results = []
    for label, rows, error in iter_traces(inputs):
        if error is not None:
            results.append({"trace": label, "status": "skipped", "reason": error})
            continue
        if not rows:
            results.append({"trace": label, "status": "skipped", "reason": "empty trace"})
            continue
        for convention in conventions:
            results.append(analyze_trace(rows, label, convention))

    ok = [r for r in results if r.get("status") == "ok"]
    summary = {
        "traces_analyzed": len(ok),
        "traces_skipped": len(results) - len(ok),
        "traces_with_silent_penetration": sum(1 for r in ok if r["silent_penetration_steps"] > 10),
        "traces_with_free_space_contact": sum(1 for r in ok if r["free_space_contact_steps"] > 10),
        "traces_with_true_engagement": sum(1 for r in ok if r["true_engagement_steps"] > 0),
        "total_true_engagement_steps": sum(r["true_engagement_steps"] for r in ok),
        "verdict_counts": {},
    }
    for r in ok:
        summary["verdict_counts"][r["verdict"]] = summary["verdict_counts"].get(r["verdict"], 0) + 1

    report = {"summary": summary, "results": results}
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w") as f:
            json.dump(report, f, indent=2)
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Contact Physics Validity Audit", "", "## Summary", ""]
        for key, value in summary.items():
            lines.append(f"- {key}: {value}")
        lines += ["", "## Per-trace results", "",
                  "| trace | convention | steps | silent pen | max pen (m) | free contact | corr | engaged | verdict |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in results:
            if r.get("status") != "ok":
                lines.append(f"| {r['trace']} | - | - | - | - | - | - | - | skipped: {r.get('reason')} |")
                continue
            lines.append(
                f"| {r['trace']} | {r['frame_convention']} | {r['steps_analyzed']} "
                f"| {r['silent_penetration_steps']} | {r['silent_penetration_max_m']} "
                f"| {r['free_space_contact_steps']} | {r['penetration_contact_correlation']} "
                f"| {r['true_engagement_steps']} | {r['verdict']} |"
            )
        with open(args.output_markdown, "w") as f:
            f.write("\n".join(lines) + "\n")

    print(json.dumps(summary, indent=2))
    worst = sorted(ok, key=lambda r: -r["silent_penetration_steps"])[:5]
    for r in worst:
        print(f"{r['trace']}: silent_pen={r['silent_penetration_steps']} "
              f"(max {r['silent_penetration_max_m']}m) free_contact={r['free_space_contact_steps']} "
              f"corr={r['penetration_contact_correlation']} verdict={r['verdict']}")


if __name__ == "__main__":
    main()
