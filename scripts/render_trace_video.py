#!/usr/bin/env python3
"""Render a verified scripted trace into a lightweight diagnostic MP4.

This is intentionally not an Isaac viewport recorder. It visualizes the trace
metrics and poses already emitted by ``scripts/scripted_agent.py`` so a human can
inspect the successful peg-in-hole process without launching Isaac again.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Iterable


Color = tuple[int, int, int]

WHITE: Color = (255, 255, 255)
BLACK: Color = (24, 28, 35)
GRAY: Color = (118, 128, 141)
LIGHT_GRAY: Color = (222, 226, 232)
PALE_GRAY: Color = (244, 246, 248)
GREEN: Color = (35, 150, 88)
LIGHT_GREEN: Color = (215, 243, 226)
BLUE: Color = (42, 111, 219)
LIGHT_BLUE: Color = (218, 231, 252)
ORANGE: Color = (221, 123, 34)
RED: Color = (203, 57, 70)
PURPLE: Color = (116, 75, 184)


FONT_5X7: dict[str, tuple[str, ...]] = {
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "11110", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "/": ("00001", "00010", "00100", "01000", "10000", "00000", "00000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "=": ("00000", "11110", "00000", "11110", "00000", "00000", "00000"),
    "<": ("00010", "00100", "01000", "10000", "01000", "00100", "00010"),
    ">": ("01000", "00100", "00010", "00001", "00010", "00100", "01000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "11100"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10011", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00001", "00001", "00001", "00001", "10001", "10001", "01110"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
}


class Canvas:
    def __init__(self, width: int, height: int, bg: Color = WHITE) -> None:
        self.width = width
        self.height = height
        self.data = bytearray(bg * (width * height))

    def pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = (y * self.width + x) * 3
            self.data[offset : offset + 3] = bytes(color)

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: Color, *, fill: bool = False) -> None:
        x0, x1 = sorted((max(0, x0), min(self.width - 1, x1)))
        y0, y1 = sorted((max(0, y0), min(self.height - 1, y1)))
        if fill:
            for y in range(y0, y1 + 1):
                start = (y * self.width + x0) * 3
                end = (y * self.width + x1 + 1) * 3
                self.data[start:end] = bytes(color) * (x1 - x0 + 1)
            return
        self.line(x0, y0, x1, y0, color)
        self.line(x1, y0, x1, y1, color)
        self.line(x1, y1, x0, y1, color)
        self.line(x0, y1, x0, y0, color)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx: int, cy: int, radius: int, color: Color, *, fill: bool = False) -> None:
        r2 = radius * radius
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy)
                if (fill and d2 <= r2) or (not fill and abs(d2 - r2) <= max(radius, 2)):
                    self.pixel(x, y, color)

    def polyline(self, points: Iterable[tuple[int, int]], color: Color) -> None:
        iterator = iter(points)
        try:
            prev = next(iterator)
        except StopIteration:
            return
        for point in iterator:
            self.line(prev[0], prev[1], point[0], point[1], color)
            prev = point

    def text(self, x: int, y: int, text: str, color: Color = BLACK, *, scale: int = 2) -> None:
        cursor = x
        for raw_ch in text.upper():
            glyph = FONT_5X7.get(raw_ch, FONT_5X7[" "])
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        self.rect(
                            cursor + gx * scale,
                            y + gy * scale,
                            cursor + (gx + 1) * scale - 1,
                            y + (gy + 1) * scale - 1,
                            color,
                            fill=True,
                        )
            cursor += 6 * scale


def _float(row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _metric_xyz(row: dict) -> tuple[float, float, float]:
    value = row.get("post_metric_tip_rel_socket_pos") or row.get("metric_tip_rel_socket_pos")
    if isinstance(value, list) and len(value) >= 3:
        return float(value[0]), float(value[1]), float(value[2])
    lateral = _float(row, "lateral")
    return lateral, 0.0, _float(row, "axial")


def _first_success_step(steps: list[dict], summary: dict) -> int | None:
    value = summary.get("success_step")
    if isinstance(value, int):
        return value
    for idx, row in enumerate(steps):
        if row.get("success") or row.get("post_success_hold"):
            return int(row.get("step", idx))
    return None


def _safe_range(values: list[float], minimum: float = 0.0) -> tuple[float, float]:
    if not values:
        return minimum, 1.0
    lo = min(min(values), minimum)
    hi = max(values)
    if math.isclose(lo, hi):
        hi = lo + 1.0
    return lo, hi


def _map(value: float, src0: float, src1: float, dst0: int, dst1: int) -> int:
    if math.isclose(src0, src1):
        return (dst0 + dst1) // 2
    t = (value - src0) / (src1 - src0)
    t = max(0.0, min(1.0, t))
    return round(dst0 + t * (dst1 - dst0))


def _panel(canvas: Canvas, x0: int, y0: int, x1: int, y1: int, title: str) -> None:
    canvas.rect(x0, y0, x1, y1, PALE_GRAY, fill=True)
    canvas.rect(x0, y0, x1, y1, LIGHT_GRAY)
    canvas.text(x0 + 14, y0 + 12, title, BLACK, scale=2)


def _draw_top_down(canvas: Canvas, rows: list[dict], idx: int, box: tuple[int, int, int, int], xy_tol: float) -> None:
    x0, y0, x1, y1 = box
    _panel(canvas, x0, y0, x1, y1, "TOP DOWN XY IN SOCKET FRAME")
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2 + 24
    half_px = min(x1 - x0, y1 - y0) // 2 - 52
    xy_span = max(0.014, xy_tol * 2.8)

    def project(row: dict) -> tuple[int, int]:
        mx, my, _ = _metric_xyz(row)
        return cx + round(mx / xy_span * half_px), cy - round(my / xy_span * half_px)

    tol_px = max(4, round(xy_tol / xy_span * half_px))
    canvas.rect(cx - tol_px, cy - tol_px, cx + tol_px, cy + tol_px, LIGHT_GREEN, fill=True)
    canvas.rect(cx - tol_px, cy - tol_px, cx + tol_px, cy + tol_px, GREEN)
    canvas.line(cx - half_px, cy, cx + half_px, cy, LIGHT_GRAY)
    canvas.line(cx, cy - half_px, cx, cy + half_px, LIGHT_GRAY)
    canvas.circle(cx, cy, 4, BLACK, fill=True)

    path_points = [project(row) for row in rows[: idx + 1]]
    canvas.polyline(path_points, BLUE)
    px, py = path_points[-1]
    success = bool(rows[idx].get("success") or rows[idx].get("post_success_hold"))
    canvas.circle(px, py, 8, GREEN if success else ORANGE, fill=True)
    canvas.text(x0 + 14, y1 - 34, f"GREEN BOX XY<= {xy_tol * 1000:.1f}MM", GRAY, scale=1)


def _draw_side_view(canvas: Canvas, rows: list[dict], idx: int, box: tuple[int, int, int, int], z_tol: float) -> None:
    x0, y0, x1, y1 = box
    _panel(canvas, x0, y0, x1, y1, "SIDE VIEW AXIAL DESCENT")
    chart_x0, chart_y0 = x0 + 52, y0 + 58
    chart_x1, chart_y1 = x1 - 38, y1 - 44
    axial_values = [_float(row, "axial") for row in rows]
    _, axial_hi = _safe_range(axial_values, minimum=0.0)
    axial_hi = max(axial_hi, z_tol * 4.0, 0.055)
    lateral_span = max(0.012, max(_float(row, "lateral") for row in rows) * 2.4)

    def project(row: dict) -> tuple[int, int]:
        mx, my, _ = _metric_xyz(row)
        lateral = math.sqrt(mx * mx + my * my)
        x = _map(lateral, -lateral_span, lateral_span, chart_x0, chart_x1)
        y = _map(_float(row, "axial"), axial_hi, 0.0, chart_y0, chart_y1)
        return x, y

    lip_y = _map(0.0, axial_hi, 0.0, chart_y0, chart_y1)
    success_y = _map(z_tol, axial_hi, 0.0, chart_y0, chart_y1)
    canvas.rect(chart_x0, success_y, chart_x1, lip_y, LIGHT_GREEN, fill=True)
    canvas.line(chart_x0, lip_y, chart_x1, lip_y, BLACK)
    canvas.line((chart_x0 + chart_x1) // 2, chart_y0, (chart_x0 + chart_x1) // 2, chart_y1, LIGHT_GRAY)
    canvas.polyline([project(row) for row in rows[: idx + 1]], PURPLE)
    px, py = project(rows[idx])
    canvas.rect(px - 11, py - 36, px + 11, py, BLUE, fill=True)
    canvas.rect(px - 11, py - 36, px + 11, py, BLACK)
    canvas.text(x0 + 14, y1 - 34, f"SUCCESS BAND AXIAL<= {z_tol * 1000:.1f}MM", GRAY, scale=1)


def _draw_graph(
    canvas: Canvas,
    rows: list[dict],
    idx: int,
    box: tuple[int, int, int, int],
    title: str,
    key: str,
    color: Color,
    threshold: float | None = None,
) -> None:
    x0, y0, x1, y1 = box
    _panel(canvas, x0, y0, x1, y1, title)
    gx0, gy0 = x0 + 38, y0 + 44
    gx1, gy1 = x1 - 16, y1 - 24
    values = [_float(row, key) for row in rows]
    lo, hi = _safe_range(values, minimum=0.0)
    if threshold is not None:
        hi = max(hi, threshold * 1.25)
    canvas.rect(gx0, gy0, gx1, gy1, WHITE, fill=True)
    canvas.rect(gx0, gy0, gx1, gy1, LIGHT_GRAY)
    if threshold is not None:
        ty = _map(threshold, hi, lo, gy0, gy1)
        canvas.line(gx0, ty, gx1, ty, GREEN)
    points = []
    for i, value in enumerate(values[: idx + 1]):
        x = _map(i, 0, max(1, len(rows) - 1), gx0, gx1)
        y = _map(value, hi, lo, gy0, gy1)
        points.append((x, y))
    canvas.polyline(points, color)
    cx, cy = points[-1]
    canvas.circle(cx, cy, 4, color, fill=True)
    canvas.text(x0 + 38, y1 - 18, f"NOW {values[idx]:.4F}", GRAY, scale=1)


def _draw_status(canvas: Canvas, rows: list[dict], idx: int, box: tuple[int, int, int, int], first_success: int | None) -> None:
    x0, y0, x1, y1 = box
    _panel(canvas, x0, y0, x1, y1, "CURRENT GATES")
    row = rows[idx]
    lines = [
        f"STEP {idx}/{len(rows) - 1}",
        f"PHASE {str(row.get('phase', 'N/A'))[:20]}",
        f"LATERAL {_float(row, 'lateral') * 1000:.2F} MM",
        f"AXIAL {_float(row, 'axial') * 1000:.2F} MM",
        f"ROT {_float(row, 'rot'):.3F} RAD",
        f"FORCE {_float(row, 'contact_force_magnitude'):.2F} N",
        f"SUCCESS {bool(row.get('success') or row.get('post_success_hold'))}",
    ]
    if first_success is not None:
        lines.append(f"FIRST SUCCESS STEP {first_success}")
    for line_idx, line in enumerate(lines):
        color = GREEN if line.endswith("TRUE") or "FIRST SUCCESS" in line else BLACK
        canvas.text(x0 + 18, y0 + 54 + line_idx * 28, line, color, scale=2)


def render_frame(
    rows: list[dict],
    summary: dict,
    idx: int,
    width: int,
    height: int,
    source_label: str,
    first_success: int | None,
) -> Canvas:
    canvas = Canvas(width, height, WHITE)
    canvas.rect(0, 0, width - 1, 72, BLACK, fill=True)
    canvas.text(24, 18, "TRACE-RENDERED PEG-IN-HOLE DIAGNOSTIC", WHITE, scale=2)
    canvas.text(width - 462, 20, "SOURCE TRACE - NOT ISAAC VIEWPORT", LIGHT_GRAY, scale=1)
    canvas.text(24, 52, source_label[-118:], LIGHT_GRAY, scale=1)

    xy_tol = float(summary.get("active_success_xy_tolerance") or rows[idx].get("active_success_xy_tolerance") or 0.005)
    z_tol = float(summary.get("active_success_z_tolerance") or rows[idx].get("active_success_z_tolerance") or 0.008)
    rot_tol = float(summary.get("active_success_rot_tolerance") or rows[idx].get("active_success_rot_tolerance") or 0.18)
    force_tol = float(summary.get("success_min_contact_force") or rows[idx].get("success_min_contact_force") or 0.5)

    _draw_top_down(canvas, rows, idx, (24, 92, 408, 392), xy_tol)
    _draw_side_view(canvas, rows, idx, (432, 92, 816, 392), z_tol)
    _draw_status(canvas, rows, idx, (840, 92, width - 24, 392), first_success)

    graph_top = 414
    graph_bottom = height - 24
    graph_w = (width - 72) // 4
    graph_boxes = []
    for i in range(4):
        gx0 = 24 + i * (graph_w + 8)
        graph_boxes.append((gx0, graph_top, gx0 + graph_w, graph_bottom))
    _draw_graph(canvas, rows, idx, graph_boxes[0], "LATERAL M", "lateral", BLUE, xy_tol)
    _draw_graph(canvas, rows, idx, graph_boxes[1], "AXIAL M", "axial", PURPLE, z_tol)
    _draw_graph(canvas, rows, idx, graph_boxes[2], "ROT RAD", "rot", ORANGE, rot_tol)
    _draw_graph(canvas, rows, idx, graph_boxes[3], "CONTACT N", "contact_force_magnitude", GREEN, force_tol)
    return canvas


def write_mp4(
    rows: list[dict],
    summary: dict,
    trace_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    fps: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    first_success = _first_success_step(rows, summary)
    source_label = str(trace_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
        assert proc.stdin is not None
        for idx in range(len(rows)):
            frame = render_frame(rows, summary, idx, width, height, source_label, first_success)
            proc.stdin.write(frame.data)
        proc.stdin.close()
        status = proc.wait()
    if status != 0:
        raise RuntimeError(f"ffmpeg failed with status {status}")


def write_render_summary(trace_path: Path, output_path: Path, rows: list[dict], summary: dict, fps: int) -> None:
    first_success = _first_success_step(rows, summary)
    final = rows[-1]
    payload = {
        "source_trace": str(trace_path),
        "output_mp4": str(output_path),
        "renderer": "trace-rendered diagnostic, not Isaac viewport footage",
        "fps": fps,
        "frame_count": len(rows),
        "duration_seconds": len(rows) / fps,
        "first_success_step": first_success,
        "final_lateral": _float(final, "lateral"),
        "final_axial": _float(final, "axial"),
        "final_rot": _float(final, "rot"),
        "final_contact_force_magnitude": _float(final, "contact_force_magnitude"),
        "summary_success_step": summary.get("success_step"),
        "summary_final_success_rate": summary.get("final_success_rate"),
    }
    output_path.with_suffix(".summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_json", type=Path, help="Path to a scripted video_trace.json file.")
    parser.add_argument("output_mp4", type=Path, help="Output MP4 path.")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=20)
    args = parser.parse_args()

    data = json.loads(args.trace_json.read_text(encoding="utf-8"))
    rows = data.get("steps")
    if not isinstance(rows, list) or not rows:
        raise SystemExit("trace JSON must contain a non-empty 'steps' array")
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    write_mp4(rows, summary, args.trace_json, args.output_mp4, width=args.width, height=args.height, fps=args.fps)
    write_render_summary(args.trace_json, args.output_mp4, rows, summary, args.fps)
    print(f"[trace-render] wrote {args.output_mp4}")
    print(f"[trace-render] summary {args.output_mp4.with_suffix('.summary.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
