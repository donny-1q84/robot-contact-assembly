from __future__ import annotations

import math

from isaaclab.controllers.differential_ik_cfg import DifferentialIKControllerCfg
from isaaclab.envs.mdp.actions.actions_cfg import DifferentialInverseKinematicsActionCfg
from isaaclab.utils import configclass

from ...constants import PEG_TIP_BODY_OFFSET_POS
from ...peg_in_hole_env_cfg import PegInHoleEnvCfg

##
# Pre-defined configs
##
from isaaclab_assets.robots.franka import FRANKA_PANDA_HIGH_PD_CFG  # isort: skip


@configclass
class FrankaPegInHoleEnvCfg(PegInHoleEnvCfg):
    """Franka insertion-stage peg-in-hole task using relative differential IK."""

    def __post_init__(self):
        super().__post_init__()

        self.scene.robot = FRANKA_PANDA_HIGH_PD_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")

        self.actions.arm_action = DifferentialInverseKinematicsActionCfg(
            asset_name="robot",
            joint_names=["panda_joint.*"],
            body_name="panda_hand",
            controller=DifferentialIKControllerCfg(command_type="pose", use_relative_mode=True, ik_method="dls"),
            scale=0.5,
            body_offset=DifferentialInverseKinematicsActionCfg.OffsetCfg(pos=PEG_TIP_BODY_OFFSET_POS),
        )

        self.commands.socket_pose.body_name = "panda_hand"
        self.commands.socket_pose.ranges.pitch = (math.pi, math.pi)
        self.commands.socket_pose.ranges.pos_x = (0.46, 0.58)
        self.commands.socket_pose.ranges.pos_y = (-0.08, 0.08)
        self.commands.socket_pose.ranges.pos_z = (0.16, 0.22)
        self.commands.socket_pose.ranges.yaw = (-math.pi / 12.0, math.pi / 12.0)

        for term in (
            self.observations.policy.tip_to_socket_position,
            self.observations.policy.tip_to_socket_orientation,
            self.rewards.tip_position_tracking,
            self.rewards.tip_position_tracking_fine,
            self.rewards.tip_orientation_tracking,
            self.rewards.insertion_progress,
            self.rewards.insertion_success,
            self.terminations.insertion_success,
        ):
            term.params["asset_cfg"].body_names = ["panda_hand"]

        self.scene.num_envs = 256
        self.scene.env_spacing = 2.5


@configclass
class FrankaPegInHoleEnvCfg_PLAY(FrankaPegInHoleEnvCfg):
    """Smaller scene for interactive debugging and teleop."""

    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5
        self.observations.policy.enable_corruption = False
