from __future__ import annotations

import math
from dataclasses import MISSING

import isaaclab.envs.mdp as base_mdp
import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg, AssetBaseCfg, RigidObjectCfg
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
from isaaclab.sensors import ContactSensorCfg
from isaaclab.sim.spawners.from_files.from_files_cfg import UsdFileCfg
from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR

from robot_contact_assembly_tasks._compat import configclass

from . import mdp
from .constants import (
    IDENTITY_QUAT,
    PEG_LENGTH_M,
    PEG_RADIUS_M,
    PEG_ROOT_FROM_TIP_POS,
    PEG_ROOT_FROM_TIP_ROT,
    PEG_TIP_BODY_OFFSET_POS,
    PEG_TIP_BODY_OFFSET_ROT,
    SOCKET_FRAME_POS,
    SOCKET_FRAME_ROT,
    SOCKET_GUIDE_DEPTH_M,
    SOCKET_GUIDE_INNER_HALF_WIDTH_M,
    SOCKET_GUIDE_OUTER_HALF_WIDTH_M,
    SOCKET_GUIDE_WALL_THICKNESS_M,
)


@configclass
class PegInHoleSceneCfg(InteractiveSceneCfg):
    """Table-top scene with a physical peg and a simple fixed guide socket."""

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

    peg = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Peg",
        init_state=RigidObjectCfg.InitialStateCfg(pos=(0.45, 0.0, 0.35), rot=IDENTITY_QUAT),
        spawn=sim_utils.CylinderCfg(
            radius=PEG_RADIUS_M,
            height=PEG_LENGTH_M,
            axis="Z",
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.05),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.23, 0.46, 0.82)),
            activate_contact_sensors=True,
        ),
    )

    socket_frame = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/SocketFrame",
        init_state=RigidObjectCfg.InitialStateCfg(pos=SOCKET_FRAME_POS, rot=SOCKET_FRAME_ROT),
        spawn=sim_utils.CuboidCfg(
            size=(0.002, 0.002, 0.002),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.01),
            collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=False),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.95, 0.65, 0.10)),
        ),
    )

    socket_wall_left = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/SocketWallLeft",
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(
                SOCKET_FRAME_POS[0] - SOCKET_GUIDE_INNER_HALF_WIDTH_M - 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M,
                SOCKET_FRAME_POS[1],
                SOCKET_FRAME_POS[2],
            ),
            rot=IDENTITY_QUAT,
        ),
        spawn=sim_utils.CuboidCfg(
            size=(
                SOCKET_GUIDE_WALL_THICKNESS_M,
                2.0 * SOCKET_GUIDE_OUTER_HALF_WIDTH_M,
                SOCKET_GUIDE_DEPTH_M,
            ),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=1.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.55, 0.55, 0.55)),
        ),
    )

    socket_wall_right = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/SocketWallRight",
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(
                SOCKET_FRAME_POS[0] + SOCKET_GUIDE_INNER_HALF_WIDTH_M + 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M,
                SOCKET_FRAME_POS[1],
                SOCKET_FRAME_POS[2],
            ),
            rot=IDENTITY_QUAT,
        ),
        spawn=sim_utils.CuboidCfg(
            size=(
                SOCKET_GUIDE_WALL_THICKNESS_M,
                2.0 * SOCKET_GUIDE_OUTER_HALF_WIDTH_M,
                SOCKET_GUIDE_DEPTH_M,
            ),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=1.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.55, 0.55, 0.55)),
        ),
    )

    socket_wall_front = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/SocketWallFront",
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(
                SOCKET_FRAME_POS[0],
                SOCKET_FRAME_POS[1] - SOCKET_GUIDE_INNER_HALF_WIDTH_M - 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M,
                SOCKET_FRAME_POS[2],
            ),
            rot=IDENTITY_QUAT,
        ),
        spawn=sim_utils.CuboidCfg(
            size=(
                2.0 * SOCKET_GUIDE_INNER_HALF_WIDTH_M,
                SOCKET_GUIDE_WALL_THICKNESS_M,
                SOCKET_GUIDE_DEPTH_M,
            ),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=1.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.55, 0.55, 0.55)),
        ),
    )

    socket_wall_back = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/SocketWallBack",
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(
                SOCKET_FRAME_POS[0],
                SOCKET_FRAME_POS[1] + SOCKET_GUIDE_INNER_HALF_WIDTH_M + 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M,
                SOCKET_FRAME_POS[2],
            ),
            rot=IDENTITY_QUAT,
        ),
        spawn=sim_utils.CuboidCfg(
            size=(
                2.0 * SOCKET_GUIDE_INNER_HALF_WIDTH_M,
                SOCKET_GUIDE_WALL_THICKNESS_M,
                SOCKET_GUIDE_DEPTH_M,
            ),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=1.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.55, 0.55, 0.55)),
        ),
    )

    peg_contact = ContactSensorCfg(
        prim_path="{ENV_REGEX_NS}/Peg",
        update_period=0.0,
        history_length=1,
        filter_prim_paths_expr=[
            "{ENV_REGEX_NS}/SocketWallLeft",
            "{ENV_REGEX_NS}/SocketWallRight",
            "{ENV_REGEX_NS}/SocketWallFront",
            "{ENV_REGEX_NS}/SocketWallBack",
        ],
    )

    light = AssetBaseCfg(
        prim_path="/World/light",
        spawn=sim_utils.DomeLightCfg(color=(0.75, 0.75, 0.75), intensity=2500.0),
    )


@configclass
class CommandsCfg:
    """Compatibility target pose mirrored from the physical socket frame."""

    socket_pose = UniformPoseCommandCfg(
        asset_name="robot",
        body_name=MISSING,
        resampling_time_range=(1.0e6, 1.0e6),
        debug_vis=True,
        ranges=UniformPoseCommandCfg.Ranges(
            pos_x=(SOCKET_FRAME_POS[0], SOCKET_FRAME_POS[0]),
            pos_y=(SOCKET_FRAME_POS[1], SOCKET_FRAME_POS[1]),
            pos_z=(SOCKET_FRAME_POS[2], SOCKET_FRAME_POS[2]),
            roll=(0.0, 0.0),
            pitch=(math.pi, math.pi),
            yaw=(0.0, 0.0),
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
        socket_pose = ObsTerm(
            func=mdp.socket_pose,
            params={"asset_cfg": SceneEntityCfg("robot"), "socket_cfg": SceneEntityCfg("socket_frame")},
        )
        tip_to_socket_position = ObsTerm(
            func=mdp.tip_to_socket_position,
            params={"peg_cfg": SceneEntityCfg("peg"), "socket_cfg": SceneEntityCfg("socket_frame")},
        )
        tip_to_socket_orientation = ObsTerm(
            func=mdp.tip_to_socket_orientation,
            params={"peg_cfg": SceneEntityCfg("peg"), "socket_cfg": SceneEntityCfg("socket_frame")},
        )
        actions = ObsTerm(func=base_mdp.last_action)

        def __post_init__(self):
            # Keep the Phase 1 policy observation width unchanged so legacy checkpoints can be
            # evaluated in the new contact shell before adding force signals to the actor.
            self.enable_corruption = True
            self.concatenate_terms = True

    policy: PolicyCfg = PolicyCfg()


@configclass
class ContactObservationsCfg:
    """Force-aware observation specs for direct contact training."""

    @configclass
    class PolicyCfg(ObsGroup):
        joint_pos = ObsTerm(func=base_mdp.joint_pos_rel)
        joint_vel = ObsTerm(func=base_mdp.joint_vel_rel)
        socket_pose = ObsTerm(
            func=mdp.socket_pose,
            params={"asset_cfg": SceneEntityCfg("robot"), "socket_cfg": SceneEntityCfg("socket_frame")},
        )
        tip_to_socket_position = ObsTerm(
            func=mdp.tip_to_socket_position,
            params={"peg_cfg": SceneEntityCfg("peg"), "socket_cfg": SceneEntityCfg("socket_frame")},
        )
        tip_to_socket_orientation = ObsTerm(
            func=mdp.tip_to_socket_orientation,
            params={"peg_cfg": SceneEntityCfg("peg"), "socket_cfg": SceneEntityCfg("socket_frame")},
        )
        peg_contact_force_socket = ObsTerm(
            func=mdp.peg_contact_force_socket,
            params={
                "sensor_cfg": SceneEntityCfg("peg_contact"),
                "socket_cfg": SceneEntityCfg("socket_frame"),
                "force_scale": 20.0,
            },
        )
        peg_contact_force_magnitude = ObsTerm(
            func=mdp.peg_contact_force_magnitude_scaled,
            params={"sensor_cfg": SceneEntityCfg("peg_contact"), "force_scale": 20.0},
        )
        actions = ObsTerm(func=base_mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    policy: PolicyCfg = PolicyCfg()


@configclass
class EventCfg:
    """Reset and rigid-attachment events."""

    reset_robot_joints = EventTerm(
        func=base_mdp.reset_joints_by_scale,
        mode="reset",
        params={
            "position_range": (0.9, 1.1),
            "velocity_range": (0.0, 0.0),
        },
    )
    sync_peg_on_reset = EventTerm(
        func=mdp.sync_peg_to_hand,
        mode="reset",
        params={
            "robot_cfg": SceneEntityCfg("robot", body_names=MISSING),
            "peg_cfg": SceneEntityCfg("peg"),
            "body_offset": PEG_TIP_BODY_OFFSET_POS,
            "body_rot_offset": PEG_TIP_BODY_OFFSET_ROT,
            "peg_root_from_tip_pos": PEG_ROOT_FROM_TIP_POS,
            "peg_root_from_tip_rot": PEG_ROOT_FROM_TIP_ROT,
        },
    )
    sync_peg_each_step = EventTerm(
        func=mdp.sync_peg_to_hand,
        mode="interval",
        interval_range_s=(0.0, 0.0),
        params={
            "robot_cfg": SceneEntityCfg("robot", body_names=MISSING),
            "peg_cfg": SceneEntityCfg("peg"),
            "body_offset": PEG_TIP_BODY_OFFSET_POS,
            "body_rot_offset": PEG_TIP_BODY_OFFSET_ROT,
            "peg_root_from_tip_pos": PEG_ROOT_FROM_TIP_POS,
            "peg_root_from_tip_rot": PEG_ROOT_FROM_TIP_ROT,
        },
    )


@configclass
class RewardsCfg:
    """Simplified reward terms for the physical contact shell."""

    approach_pose = RewTerm(
        func=mdp.approach_pose_reward,
        weight=8.0,
        params={
            "lateral_std": 0.05,
            "axial_std": 0.05,
            "rot_std": 1.20,
            "peg_cfg": SceneEntityCfg("peg"),
            "socket_cfg": SceneEntityCfg("socket_frame"),
            "axial_weight": 0.35,
        },
    )
    tip_position_tracking = RewTerm(
        func=mdp.tip_position_error_tanh,
        weight=2.0,
        params={
            "std": 0.08,
            "peg_cfg": SceneEntityCfg("peg"),
            "socket_cfg": SceneEntityCfg("socket_frame"),
        },
    )
    tip_position_tracking_fine = RewTerm(
        func=mdp.tip_position_error_tanh,
        weight=5.0,
        params={
            "std": 0.015,
            "peg_cfg": SceneEntityCfg("peg"),
            "socket_cfg": SceneEntityCfg("socket_frame"),
        },
    )
    tip_orientation_tracking = RewTerm(
        func=mdp.tip_orientation_error_tanh,
        weight=2.0,
        params={
            "std": 1.0,
            "peg_cfg": SceneEntityCfg("peg"),
            "socket_cfg": SceneEntityCfg("socket_frame"),
        },
    )
    insertion_progress = RewTerm(
        func=mdp.insertion_progress_reward,
        weight=8.0,
        params={
            "std": 0.010,
            "peg_cfg": SceneEntityCfg("peg"),
            "socket_cfg": SceneEntityCfg("socket_frame"),
            "lateral_tolerance": 0.015,
            "lateral_std": 0.008,
            "rot_tolerance": 0.30,
            "rot_std": 0.15,
        },
    )
    insertion_success = RewTerm(
        func=mdp.insertion_success_reward,
        weight=40.0,
        params={
            "peg_cfg": SceneEntityCfg("peg"),
            "socket_cfg": SceneEntityCfg("socket_frame"),
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
            "peg_cfg": SceneEntityCfg("peg"),
            "socket_cfg": SceneEntityCfg("socket_frame"),
        },
    )


@configclass
class CurriculumCfg:
    """Light curriculum for the first contact-shell runs."""

    action_rate = CurrTerm(
        func=base_mdp.modify_reward_weight,
        params={"term_name": "action_rate", "weight": -0.005, "num_steps": 5000},
    )


@configclass
class PegInHoleEnvCfg(ManagerBasedRLEnvCfg):
    """Contact-guided peg-in-hole environment with a rigidly attached peg."""

    scene: PegInHoleSceneCfg = PegInHoleSceneCfg(num_envs=256, env_spacing=2.5)
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
        self.teleop_devices = DevicesCfg(
            devices={
                "keyboard": Se3KeyboardCfg(gripper_term=False, sim_device=self.sim.device),
                "gamepad": Se3GamepadCfg(gripper_term=False, sim_device=self.sim.device),
                "spacemouse": Se3SpaceMouseCfg(gripper_term=False, sim_device=self.sim.device),
            }
        )


@configclass
class PegInHoleContactEnvCfg(PegInHoleEnvCfg):
    """Contact-shell environment with force-aware policy observations."""

    observations: ContactObservationsCfg = ContactObservationsCfg()
