#!/usr/bin/env python3
"""Pure command logic for the socket-frame insertion servo.

This module intentionally has no Isaac dependency so local tests can verify the
servo's semantic direction before paid GPU validation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SocketInsertionServoConfig:
    xy_gain: float = 0.85
    xy_clamp: float = 0.0025
    z_gain: float = 1.0
    z_step: float = 0.0015
    descend_xy_tolerance: float = 0.005
    descend_rot_tolerance: float = 0.18
    success_z_tolerance: float = 0.008
    contact_preload_step: float = 0.001
    success_min_contact_force: float = 0.5
    contact_boundary_min_force: float = 0.25
    contact_boundary_tolerance: float = 0.001
    contact_boundary_step: float = 0.00015
    contact_boundary_xy_gain: float = 0.0
    contact_boundary_xy_clamp: float = 0.0
    maintain_contact_preload: bool = False


def _clamp(values: torch.Tensor, limit: float) -> torch.Tensor:
    import torch

    limit = max(0.0, float(limit))
    return torch.clamp(values, min=-limit, max=limit)


def _clamp_scalar(value: float, limit: float) -> float:
    limit = max(0.0, float(limit))
    return min(limit, max(-limit, float(value)))


def compute_socket_insertion_servo_offset_scalar(
    metric_tip_rel_socket_pos: tuple[float, float, float],
    lateral_error: float,
    axial_error: float,
    orientation_error: float,
    contact_force_magnitude: float | None,
    active: bool,
    config: SocketInsertionServoConfig,
) -> tuple[tuple[float, float, float], dict[str, bool]]:
    """Scalar equivalent used by local offline gate tests."""

    contact_ready = (
        False
        if contact_force_magnitude is None
        else contact_force_magnitude >= max(0.0, float(config.success_min_contact_force))
    )
    boundary_contact_ready = (
        False
        if contact_force_magnitude is None
        else contact_force_magnitude >= max(0.0, float(config.contact_boundary_min_force))
    )
    xy_ready = lateral_error <= max(0.0, float(config.descend_xy_tolerance))
    rot_ready = orientation_error <= max(0.0, float(config.descend_rot_tolerance))
    axial_ready = axial_error <= max(0.0, float(config.success_z_tolerance))
    contact_boundary = (
        active
        and xy_ready
        and rot_ready
        and boundary_contact_ready
        and not axial_ready
        and (
            axial_error
            <= max(0.0, float(config.success_z_tolerance))
            + max(0.0, float(config.contact_boundary_tolerance))
        )
    )
    descend_ready = active and xy_ready and rot_ready and not axial_ready and not contact_boundary
    contact_preload = active and xy_ready and rot_ready and axial_ready and (
        not contact_ready or bool(config.maintain_contact_preload)
    )
    maintained_contact_preload = bool(config.maintain_contact_preload) and contact_preload and contact_ready
    contact_boundary_preload = contact_preload and boundary_contact_ready

    if not active:
        offset = (0.0, 0.0, 0.0)
    else:
        x, y, z = metric_tip_rel_socket_pos
        xy_gain = (
            max(0.0, float(config.contact_boundary_xy_gain))
            if contact_boundary or contact_boundary_preload
            else max(0.0, float(config.xy_gain))
        )
        xy_clamp = (
            max(0.0, float(config.contact_boundary_xy_clamp))
            if contact_boundary or contact_boundary_preload
            else max(0.0, float(config.xy_clamp))
        )
        z_command = min(_clamp_scalar(-max(0.0, float(config.z_gain)) * z, config.z_step), 0.0)
        if descend_ready:
            z_offset = z_command
        elif contact_boundary:
            boundary_excess = max(0.0, float(z) - max(0.0, float(config.success_z_tolerance)))
            z_offset = -min(
                max(0.0, float(config.contact_boundary_step)),
                boundary_excess,
            )
        elif contact_preload:
            preload_step = max(0.0, float(config.contact_preload_step))
            if contact_boundary_preload:
                preload_step = min(preload_step, max(0.0, float(config.contact_boundary_step)))
            z_offset = -preload_step
        else:
            z_offset = 0.0
        offset = (
            _clamp_scalar(-xy_gain * x, xy_clamp),
            _clamp_scalar(-xy_gain * y, xy_clamp),
            z_offset,
        )

    masks = {
        "xy_ready": bool(active and xy_ready),
        "rot_ready": bool(active and rot_ready),
        "axial_ready": bool(active and axial_ready),
        "contact_ready": bool(active and contact_ready),
        "boundary_contact_ready": bool(active and boundary_contact_ready),
        "descend_ready": bool(descend_ready),
        "contact_boundary": bool(contact_boundary),
        "contact_preload": bool(contact_preload),
        "maintained_contact_preload": bool(maintained_contact_preload),
        "contact_boundary_preload": bool(contact_boundary_preload),
        "hold_z": bool(active and not descend_ready and not contact_boundary and not contact_preload),
    }
    return offset, masks


def compute_socket_insertion_servo_offset(
    metric_tip_rel_socket_pos: torch.Tensor,
    lateral_error: torch.Tensor,
    axial_error: torch.Tensor,
    orientation_error: torch.Tensor,
    contact_force_magnitude: torch.Tensor | None,
    active_mask: torch.Tensor,
    config: SocketInsertionServoConfig,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Return a socket-frame command offset and semantic masks.

    Positive metric Z means the tip is still above the socket goal. The servo
    only commands negative socket-Z motion when XY and rotation are ready. This
    is the core negative-control guard: misaligned states may center/rotate, but
    must not spend insertion depth.
    """

    import torch

    if metric_tip_rel_socket_pos.ndim != 2 or metric_tip_rel_socket_pos.shape[-1] != 3:
        raise ValueError("metric_tip_rel_socket_pos must have shape (N, 3)")

    active_mask = active_mask.to(dtype=torch.bool, device=metric_tip_rel_socket_pos.device)
    lateral_error = lateral_error.to(device=metric_tip_rel_socket_pos.device)
    axial_error = axial_error.to(device=metric_tip_rel_socket_pos.device)
    orientation_error = orientation_error.to(device=metric_tip_rel_socket_pos.device)
    if contact_force_magnitude is None:
        contact_ready = torch.zeros_like(active_mask)
        boundary_contact_ready = torch.zeros_like(active_mask)
    else:
        contact_force = contact_force_magnitude.to(device=metric_tip_rel_socket_pos.device).reshape(-1)
        contact_ready = contact_force >= max(0.0, float(config.success_min_contact_force))
        boundary_contact_ready = contact_force >= max(0.0, float(config.contact_boundary_min_force))

    xy_ready = lateral_error <= max(0.0, float(config.descend_xy_tolerance))
    rot_ready = orientation_error <= max(0.0, float(config.descend_rot_tolerance))
    axial_ready = axial_error <= max(0.0, float(config.success_z_tolerance))
    contact_boundary = (
        active_mask
        & xy_ready
        & rot_ready
        & boundary_contact_ready
        & ~axial_ready
        & (
            axial_error
            <= max(0.0, float(config.success_z_tolerance))
            + max(0.0, float(config.contact_boundary_tolerance))
        )
    )
    descend_ready = active_mask & xy_ready & rot_ready & ~axial_ready & ~contact_boundary
    contact_preload = active_mask & xy_ready & rot_ready & axial_ready & (
        ~contact_ready if not config.maintain_contact_preload else torch.ones_like(contact_ready)
    )
    maintained_contact_preload = (
        contact_preload & contact_ready
        if config.maintain_contact_preload
        else torch.zeros_like(contact_preload)
    )
    contact_boundary_preload = contact_preload & boundary_contact_ready

    offset_socket = torch.zeros_like(metric_tip_rel_socket_pos)
    normal_xy_offset = _clamp(
        -max(0.0, float(config.xy_gain)) * metric_tip_rel_socket_pos[:, :2],
        config.xy_clamp,
    )
    boundary_xy_offset = _clamp(
        -max(0.0, float(config.contact_boundary_xy_gain)) * metric_tip_rel_socket_pos[:, :2],
        config.contact_boundary_xy_clamp,
    )
    offset_socket[:, :2] = torch.where(
        (contact_boundary | contact_boundary_preload)[:, None],
        boundary_xy_offset,
        normal_xy_offset,
    )
    z_command = _clamp(
        -max(0.0, float(config.z_gain)) * metric_tip_rel_socket_pos[:, 2],
        config.z_step,
    )
    z_command = torch.minimum(z_command, torch.zeros_like(z_command))
    boundary_excess = torch.clamp(
        metric_tip_rel_socket_pos[:, 2] - max(0.0, float(config.success_z_tolerance)),
        min=0.0,
        max=max(0.0, float(config.contact_boundary_step)),
    )
    z_boundary = -boundary_excess
    preload_step = max(0.0, float(config.contact_preload_step))
    maintained_preload_step = min(preload_step, max(0.0, float(config.contact_boundary_step)))
    z_preload = -torch.where(
        contact_boundary_preload,
        torch.full_like(z_command, maintained_preload_step),
        torch.full_like(z_command, preload_step),
    )
    offset_socket[:, 2] = torch.where(
        descend_ready,
        z_command,
        torch.where(
            contact_boundary,
            z_boundary,
            torch.where(contact_preload, z_preload, torch.zeros_like(z_command)),
        ),
    )
    offset_socket = torch.where(active_mask[:, None], offset_socket, torch.zeros_like(offset_socket))

    masks = {
        "xy_ready": xy_ready & active_mask,
        "rot_ready": rot_ready & active_mask,
        "axial_ready": axial_ready & active_mask,
        "contact_ready": contact_ready & active_mask,
        "boundary_contact_ready": boundary_contact_ready & active_mask,
        "descend_ready": descend_ready,
        "contact_boundary": contact_boundary,
        "contact_preload": contact_preload,
        "maintained_contact_preload": maintained_contact_preload,
        "contact_boundary_preload": contact_boundary_preload,
        "hold_z": active_mask & ~descend_ready & ~contact_boundary & ~contact_preload,
    }
    return offset_socket, masks
