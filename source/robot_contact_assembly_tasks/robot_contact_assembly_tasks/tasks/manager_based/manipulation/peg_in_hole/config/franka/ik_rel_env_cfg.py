from __future__ import annotations

from isaaclab.controllers.differential_ik_cfg import DifferentialIKControllerCfg
from isaaclab.envs.mdp.actions.actions_cfg import DifferentialInverseKinematicsActionCfg, JointPositionActionCfg
from isaaclab.utils import configclass

from ...constants import PEG_TIP_BODY_OFFSET_POS, PEG_TIP_BODY_OFFSET_ROT
from ...peg_in_hole_env_cfg import PegInHoleEnvCfg
from ...peg_in_hole_env_cfg import PegInHoleContactEnvCfg

##
# Pre-defined configs
##
from isaaclab_assets.robots.franka import FRANKA_PANDA_HIGH_PD_CFG  # isort: skip


@configclass
class FrankaPegInHoleEnvCfg(PegInHoleEnvCfg):
    """Franka contact-guided peg-in-hole task using relative differential IK."""

    def __post_init__(self):
        super().__post_init__()

        self.scene.robot = FRANKA_PANDA_HIGH_PD_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")

        self.actions.arm_action = DifferentialInverseKinematicsActionCfg(
            asset_name="robot",
            joint_names=["panda_joint.*"],
            body_name="panda_hand",
            controller=DifferentialIKControllerCfg(command_type="pose", use_relative_mode=True, ik_method="dls"),
            scale=0.5,
            body_offset=DifferentialInverseKinematicsActionCfg.OffsetCfg(
                pos=PEG_TIP_BODY_OFFSET_POS,
                rot=PEG_TIP_BODY_OFFSET_ROT,
            ),
        )

        self.commands.socket_pose.body_name = "panda_hand"
        self.events.sync_peg_on_reset.params["robot_cfg"].body_names = ["panda_hand"]
        self.events.sync_peg_each_step.params["robot_cfg"].body_names = ["panda_hand"]

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
    """Deprecated alias kept only so existing scripts can still point at the old task id."""

    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5


@configclass
class FrankaPegInHoleContactEnvCfg(PegInHoleContactEnvCfg):
    """Franka contact task with force-aware observations for direct contact training."""

    def __post_init__(self):
        super().__post_init__()

        self.scene.robot = FRANKA_PANDA_HIGH_PD_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")

        self.actions.arm_action = DifferentialInverseKinematicsActionCfg(
            asset_name="robot",
            joint_names=["panda_joint.*"],
            body_name="panda_hand",
            controller=DifferentialIKControllerCfg(command_type="pose", use_relative_mode=True, ik_method="dls"),
            scale=0.2,
            body_offset=DifferentialInverseKinematicsActionCfg.OffsetCfg(
                pos=PEG_TIP_BODY_OFFSET_POS,
                rot=PEG_TIP_BODY_OFFSET_ROT,
            ),
        )

        self.commands.socket_pose.body_name = "panda_hand"
        self.events.sync_peg_on_reset.params["robot_cfg"].body_names = ["panda_hand"]
        self.events.sync_peg_each_step.params["robot_cfg"].body_names = ["panda_hand"]
        self.events.reset_robot_joints.params["position_range"] = (0.97, 1.03)
        self.observations.policy.enable_corruption = False

        self.scene.num_envs = 256
        self.scene.env_spacing = 2.5


@configclass
class FrankaPegInHoleContactEnvCfg_PLAY(FrankaPegInHoleContactEnvCfg):
    """Smaller force-aware contact task for smoke tests and debugging."""

    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5
        self.observations.policy.enable_corruption = False


@configclass
class FrankaPegInHoleContactAbsEnvCfg(FrankaPegInHoleContactEnvCfg):
    """Force-aware contact task using absolute pose IK targets."""

    def __post_init__(self):
        super().__post_init__()

        self.actions.arm_action = DifferentialInverseKinematicsActionCfg(
            asset_name="robot",
            joint_names=["panda_joint.*"],
            body_name="panda_hand",
            controller=DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls"),
            scale=1.0,
            body_offset=DifferentialInverseKinematicsActionCfg.OffsetCfg(
                pos=PEG_TIP_BODY_OFFSET_POS,
                rot=PEG_TIP_BODY_OFFSET_ROT,
            ),
        )


@configclass
class FrankaPegInHoleContactAbsEnvCfg_PLAY(FrankaPegInHoleContactAbsEnvCfg):
    """Smaller absolute-pose IK contact task for scripted validation."""

    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5
        self.observations.policy.enable_corruption = False


@configclass
class FrankaPegInHoleContactJointPosEnvCfg(FrankaPegInHoleContactEnvCfg):
    """Force-aware contact task using direct Franka arm joint-position targets."""

    def __post_init__(self):
        super().__post_init__()

        self.actions.arm_action = JointPositionActionCfg(
            asset_name="robot",
            joint_names=[
                "panda_joint1",
                "panda_joint2",
                "panda_joint3",
                "panda_joint4",
                "panda_joint5",
                "panda_joint6",
                "panda_joint7",
            ],
            scale=1.0,
            offset=0.0,
            preserve_order=True,
            use_default_offset=False,
        )


@configclass
class FrankaPegInHoleContactJointPosEnvCfg_PLAY(FrankaPegInHoleContactJointPosEnvCfg):
    """Smaller joint-position contact task for deterministic scripted validation."""

    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5
        self.observations.policy.enable_corruption = False
