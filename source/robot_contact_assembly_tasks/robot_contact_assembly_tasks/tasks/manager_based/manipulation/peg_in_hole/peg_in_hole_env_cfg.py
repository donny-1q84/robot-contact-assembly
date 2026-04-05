from __future__ import annotations

import math
from dataclasses import MISSING

from isaaclab_physx.physics import PhysxCfg

import isaaclab.envs.mdp as base_mdp
import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg, AssetBaseCfg
from isaaclab.devices import DevicesCfg
from isaaclab.devices.gamepad import Se3GamepadCfg
from isaaclab.devices.keyboard import Se3KeyboardCfg
from isaaclab.devices.spacemouse import Se3SpaceMouseCfg
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab.envs.mdp.commands.commands_cfg import UniformPoseCommandCfg
from isaaclab.managers import ActionTermCfg as ActionTerm
from isaaclab.managers import CurriculumTermCfg as CurrTerm
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sim.spawners.from_files.from_files_cfg import UsdFileCfg
from isaaclab.utils import configclass
from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR

from . import mdp


@configclass
class PegInHoleSceneCfg(InteractiveSceneCfg):
    """Basic table-top scene for the insertion-only peg-in-hole baseline."""

    ground = AssetBaseCfg(
        prim_path="/World/ground",
        spawn=sim_utils.GroundPlaneCfg(),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, -1.05)),
    )

    table = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Table",
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.5, 0.0, 0.0), rot=(0.0, 0.0, 0.707, 0.707)),
        spawn=UsdFileCfg(usd_path=f"{ISAAC_NUCLEUS_DIR}/Props/Mounts/SeattleLabTable/table_instanceable.usd"),
    )

    robot: ArticulationCfg = MISSING

    light = AssetBaseCfg(
        prim_path="/World/light",
        spawn=sim_utils.DomeLightCfg(color=(0.75, 0.75, 0.75), intensity=2500.0),
    )


@configclass
class CommandsCfg:
    """Target socket pose for the peg tip."""

    socket_pose = UniformPoseCommandCfg(
        asset_name="robot",
        body_name=MISSING,
        resampling_time_range=(4.0, 4.0),
        debug_vis=True,
        ranges=UniformPoseCommandCfg.Ranges(
            pos_x=(0.48, 0.60),
            pos_y=(-0.12, 0.12),
            pos_z=(0.18, 0.26),
            roll=(0.0, 0.0),
            pitch=MISSING,
            yaw=(-math.pi / 6.0, math.pi / 6.0),
        ),
    )


@configclass
class ActionsCfg:
    """Action specifications for the MDP."""

    arm_action: ActionTerm = MISSING


@configclass
class ObservationsCfg:
    """Observation specifications for policy training."""

    @configclass
    class PolicyCfg(ObsGroup):
        joint_pos = ObsTerm(func=base_mdp.joint_pos_rel)
        joint_vel = ObsTerm(func=base_mdp.joint_vel_rel)
        socket_pose = ObsTerm(func=base_mdp.generated_commands, params={"command_name": "socket_pose"})
        tip_to_socket_position = ObsTerm(
            func=mdp.tip_to_socket_position,
            params={"command_name": "socket_pose", "asset_cfg": SceneEntityCfg("robot", body_names=MISSING)},
        )
        tip_to_socket_orientation = ObsTerm(
            func=mdp.tip_to_socket_orientation,
            params={"command_name": "socket_pose", "asset_cfg": SceneEntityCfg("robot", body_names=MISSING)},
        )
        actions = ObsTerm(func=base_mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    policy: PolicyCfg = PolicyCfg()


@configclass
class EventCfg:
    """Reset events."""

    reset_robot_joints = EventTerm(
        func=base_mdp.reset_joints_by_scale,
        mode="reset",
        params={
            "position_range": (0.9, 1.1),
            "velocity_range": (0.0, 0.0),
        },
    )


@configclass
class RewardsCfg:
    """Reward terms specialized for insertion-stage control."""

    tip_position_tracking = RewTerm(
        func=mdp.tip_position_error_tanh,
        weight=2.0,
        params={
            "std": 0.02,
            "command_name": "socket_pose",
            "asset_cfg": SceneEntityCfg("robot", body_names=MISSING),
        },
    )
    tip_position_tracking_fine = RewTerm(
        func=mdp.tip_position_error_tanh,
        weight=4.0,
        params={
            "std": 0.005,
            "command_name": "socket_pose",
            "asset_cfg": SceneEntityCfg("robot", body_names=MISSING),
        },
    )
    tip_orientation_tracking = RewTerm(
        func=mdp.tip_orientation_error_tanh,
        weight=0.5,
        params={
            "std": 0.25,
            "command_name": "socket_pose",
            "asset_cfg": SceneEntityCfg("robot", body_names=MISSING),
        },
    )
    insertion_progress = RewTerm(
        func=mdp.insertion_progress_reward,
        weight=12.0,
        params={
            "std": 0.015,
            "command_name": "socket_pose",
            "asset_cfg": SceneEntityCfg("robot", body_names=MISSING),
            "lateral_tolerance": 0.015,
            "lateral_std": 0.025,
            "rot_tolerance": 0.35,
            "rot_std": 0.35,
        },
    )
    insertion_success = RewTerm(
        func=mdp.insertion_success_reward,
        weight=40.0,
        params={
            "command_name": "socket_pose",
            "asset_cfg": SceneEntityCfg("robot", body_names=MISSING),
            "xy_tolerance": 0.006,
            "z_tolerance": 0.012,
            "rot_tolerance": 0.20,
        },
    )
    action_rate = RewTerm(func=base_mdp.action_rate_l2, weight=-1e-4)
    joint_vel = RewTerm(
        func=base_mdp.joint_vel_l2,
        weight=-1e-4,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )


@configclass
class TerminationsCfg:
    """Termination terms."""

    time_out = DoneTerm(func=base_mdp.time_out, time_out=True)
    insertion_success = DoneTerm(
        func=mdp.insertion_success,
        params={
            "command_name": "socket_pose",
            "asset_cfg": SceneEntityCfg("robot", body_names=MISSING),
            "xy_tolerance": 0.006,
            "z_tolerance": 0.012,
            "rot_tolerance": 0.20,
        },
    )


@configclass
class CurriculumCfg:
    """Light curriculum for the first PPO smoke test."""

    action_rate = CurrTerm(
        func=base_mdp.modify_reward_weight,
        params={"term_name": "action_rate", "weight": -0.005, "num_steps": 5000},
    )


@configclass
class PegInHoleEnvCfg(ManagerBasedRLEnvCfg):
    """Insertion-stage peg-in-hole environment with a fixed peg tip offset."""

    scene: PegInHoleSceneCfg = PegInHoleSceneCfg(num_envs=1024, env_spacing=2.5)
    observations: ObservationsCfg = ObservationsCfg()
    actions: ActionsCfg = ActionsCfg()
    commands: CommandsCfg = CommandsCfg()
    rewards: RewardsCfg = RewardsCfg()
    terminations: TerminationsCfg = TerminationsCfg()
    events: EventCfg = EventCfg()
    curriculum: CurriculumCfg = CurriculumCfg()

    def __post_init__(self):
        self.decimation = 2
        self.sim.render_interval = self.decimation
        self.episode_length_s = 8.0
        self.viewer.eye = (2.5, 2.5, 1.8)
        self.sim.dt = 1.0 / 60.0
        self.sim.physics = PhysxCfg(bounce_threshold_velocity=0.2)
        self.teleop_devices = DevicesCfg(
            devices={
                "keyboard": Se3KeyboardCfg(gripper_term=False, sim_device=self.sim.device),
                "gamepad": Se3GamepadCfg(gripper_term=False, sim_device=self.sim.device),
                "spacemouse": Se3SpaceMouseCfg(gripper_term=False, sim_device=self.sim.device),
            }
        )
