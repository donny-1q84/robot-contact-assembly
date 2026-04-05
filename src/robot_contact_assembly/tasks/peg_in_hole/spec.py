from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ObservationSpec:
    joint_positions: bool = True
    joint_velocities: bool = True
    ee_pose: bool = True
    peg_pose: bool = True
    socket_pose: bool = True
    relative_pose: bool = True
    vision: bool = False


@dataclass
class ActionSpec:
    mode: str = "ee_delta_pose"
    rate_hz: int = 20
    pos_limit_m: float = 0.01
    rot_limit_rad: float = 0.1


@dataclass
class RewardSpec:
    reach_weight: float = 1.0
    align_weight: float = 2.0
    insert_weight: float = 5.0
    success_bonus: float = 20.0
    action_penalty: float = 0.01
    collision_penalty: float = 0.5


@dataclass
class TerminationSpec:
    timeout_s: float = 10.0
    unstable_contact_threshold: float = 1.0


@dataclass
class PegInHoleTaskSpec:
    task_name: str = "peg_in_hole"
    robot_name: str = "isaac_arm_tbd"
    table_height_m: float = 0.75
    peg_radius_m: float = 0.01
    peg_length_m: float = 0.08
    hole_radius_m: float = 0.0105
    insertion_depth_m: float = 0.03
    observations: ObservationSpec = field(default_factory=ObservationSpec)
    actions: ActionSpec = field(default_factory=ActionSpec)
    rewards: RewardSpec = field(default_factory=RewardSpec)
    termination: TerminationSpec = field(default_factory=TerminationSpec)


def build_default_spec() -> PegInHoleTaskSpec:
    """Return the phase-1 peg-in-hole task contract."""
    return PegInHoleTaskSpec()
