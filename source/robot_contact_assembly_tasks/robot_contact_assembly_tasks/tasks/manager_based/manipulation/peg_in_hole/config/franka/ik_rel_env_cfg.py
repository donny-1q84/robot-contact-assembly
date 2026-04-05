from __future__ import annotations

import math

from isaaclab.controllers.differential_ik_cfg import DifferentialIKControllerCfg
from isaaclab.envs.mdp.actions.actions_cfg import DifferentialInverseKinematicsActionCfg
from isaaclab.utils import configclass

from ... import mdp
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

        # Keep a single socket target for the whole episode; resampling mid-episode makes the
        # insertion proxy chase a moving goal and destroys any chance of learning completion.
        self.commands.socket_pose.resampling_time_range = (1.0e6, 1.0e6)
        self.commands.socket_pose.body_name = "panda_hand"
        self.commands.socket_pose.ranges.pitch = (math.pi, math.pi)
        self.commands.socket_pose.ranges.pos_x = (0.48, 0.56)
        self.commands.socket_pose.ranges.pos_y = (-0.05, 0.05)
        self.commands.socket_pose.ranges.pos_z = (0.17, 0.21)
        self.commands.socket_pose.ranges.yaw = (-math.pi / 24.0, math.pi / 24.0)

        for term in (
            self.observations.policy.tip_to_socket_position,
            self.observations.policy.tip_to_socket_orientation,
            self.rewards.approach_pose,
            self.rewards.tip_position_tracking,
            self.rewards.tip_position_tracking_fine,
            self.rewards.tip_orientation_tracking,
            self.rewards.insertion_orientation_fine,
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


@configclass
class FrankaPegInHoleEnvCfg_POLISH(FrankaPegInHoleEnvCfg):
    """Narrow late-stage curriculum for polishing insertion from a near-success checkpoint."""

    def __post_init__(self):
        super().__post_init__()

        # The base Phase 1 task still samples a fairly broad socket neighborhood so PPO can
        # learn coarse approach. For checkpoint fine-tuning we want a strictly narrower regime
        # that keeps the policy near the socket and spends most of its capacity on the final
        # orientation / insertion refinement.
        self.commands.socket_pose.ranges.pos_x = (0.505, 0.545)
        self.commands.socket_pose.ranges.pos_y = (-0.025, 0.025)
        self.commands.socket_pose.ranges.pos_z = (0.178, 0.202)
        self.commands.socket_pose.ranges.yaw = (-math.pi / 48.0, math.pi / 48.0)

        # Replace the broad approach reward with a tighter joint pose reward that
        # only pays simultaneous lateral, axial, and rotational convergence.
        self.rewards.approach_pose.func = mdp.late_stage_pose_reward
        self.rewards.approach_pose.weight = 12.0
        self.rewards.approach_pose.params = {
            "lateral_std": 0.012,
            "axial_std": 0.008,
            "rot_std": 0.40,
            "command_name": "socket_pose",
            "asset_cfg": self.rewards.approach_pose.params["asset_cfg"],
        }

        # In polish mode keep the separate coarse tracking terms weaker so the
        # coupled late-stage reward and insertion-specific terms dominate.
        self.rewards.tip_position_tracking.weight = 1.5
        self.rewards.tip_position_tracking_fine.weight = 5.0
        self.rewards.tip_orientation_tracking.weight = 1.5
        self.rewards.insertion_orientation_fine.weight = 10.0
        self.rewards.insertion_progress.weight = 12.0
        self.rewards.insertion_success.weight = 80.0

        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5
