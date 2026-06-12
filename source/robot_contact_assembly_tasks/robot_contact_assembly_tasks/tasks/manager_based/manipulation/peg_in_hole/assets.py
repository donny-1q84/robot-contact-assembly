"""Spawners for the physically attached peg.

The peg must be a dynamic rigid body so PhysX resolves peg/socket-wall
contacts (the 2026-06-11 audit showed kinematic-kinematic pairs produce no
reaction at all). It is rigidly attached to the robot hand with a USD
``PhysicsFixedJoint`` authored at spawn time, inside the ``env_0`` template,
so the scene cloner replicates the joint per environment exactly like the
robot's own joints. Authoring before the simulation starts avoids the
runtime-joint-creation pitfalls of doing this in a startup event.

The joint is marked ``excludeFromArticulation`` so PhysX keeps the peg a
standalone rigid body (maximal-coordinate joint) instead of folding it into
the Franka articulation; otherwise the ``peg`` RigidObject view would fail to
initialize and every observation/reward/termination reading the peg pose
would break.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import isaaclab.sim as sim_utils
from isaaclab.sim.utils import find_matching_prim_paths
from pxr import Gf, Sdf, UsdPhysics

from robot_contact_assembly_tasks._compat import configclass

if TYPE_CHECKING:
    from pxr import Usd


def _gf_quat_from_xyzw(quat_xyzw: tuple[float, float, float, float]) -> Gf.Quatf:
    """Convert this repo's calibrated XYZW quaternions to USD's scalar-first Gf.Quatf."""

    x, y, z, w = (float(v) for v in quat_xyzw)
    return Gf.Quatf(w, Gf.Vec3f(x, y, z))


def spawn_attached_peg_cylinder(
    prim_path: str,
    cfg: "AttachedPegCylinderCfg",
    translation: tuple[float, float, float] | None = None,
    orientation: tuple[float, float, float, float] | None = None,
) -> "Usd.Prim":
    """Spawn the peg cylinder and weld it to the robot hand with a fixed joint.

    The robot articulation must be declared before the peg in the scene config
    so its prim already exists when this spawner runs.
    """

    prim = sim_utils.spawn_cylinder(prim_path, cfg, translation, orientation)
    stage = prim.GetStage()

    try:
        peg_paths = find_matching_prim_paths(prim_path)
    except ValueError:
        peg_paths = [prim_path]
    if not peg_paths:
        peg_paths = [prim.GetPath().pathString]

    for peg_path in peg_paths:
        env_path = peg_path.rsplit("/", 1)[0]
        robot_path = f"{env_path}/{cfg.robot_prim_name}"
        hand_path = f"{robot_path}/{cfg.hand_link_name}"
        if not stage.GetPrimAtPath(hand_path).IsValid():
            raise ValueError(
                f"Cannot attach peg: robot hand prim '{hand_path}' does not exist. "
                "The robot must be declared before the peg in the scene config."
            )

        joint = UsdPhysics.FixedJoint.Define(stage, Sdf.Path(f"{peg_path}/{cfg.attach_joint_name}"))
        joint.CreateBody0Rel().SetTargets([Sdf.Path(hand_path)])
        joint.CreateBody1Rel().SetTargets([Sdf.Path(peg_path)])
        joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*(float(v) for v in cfg.joint_local_pos0)))
        joint.CreateLocalRot0Attr().Set(_gf_quat_from_xyzw(cfg.joint_local_rot0_xyzw))
        joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
        joint.CreateLocalRot1Attr().Set(Gf.Quatf(1.0))
        # Keep the peg out of the Franka articulation so it stays a plain rigid body.
        joint.CreateExcludeFromArticulationAttr().Set(True)

        if cfg.filtered_robot_links:
            filtered = UsdPhysics.FilteredPairsAPI.Apply(stage.GetPrimAtPath(Sdf.Path(peg_path)))
            pairs_rel = filtered.CreateFilteredPairsRel()
            for link_name in cfg.filtered_robot_links:
                pairs_rel.AddTarget(Sdf.Path(f"{robot_path}/{link_name}"))

    return prim


@configclass
class AttachedPegCylinderCfg(sim_utils.CylinderCfg):
    """Cylinder spawn config that also welds the peg to the robot hand.

    ``joint_local_pos0`` / ``joint_local_rot0_xyzw`` define the peg-root
    (cylinder center) frame relative to the hand body frame, i.e. the same
    transform the old kinematic ``sync_peg_to_hand`` event enforced. The
    rotation uses this repo's calibrated XYZW convention and is converted to
    USD's scalar-first quaternion at authoring time.
    """

    func: Callable = spawn_attached_peg_cylinder

    robot_prim_name: str = "Robot"
    hand_link_name: str = "panda_hand"
    attach_joint_name: str = "PegHandFixedJoint"
    joint_local_pos0: tuple[float, float, float] = (0.0, 0.0, 0.0)
    joint_local_rot0_xyzw: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    # The gripper fingers interpenetrate the welded peg by construction; their
    # contacts are parasitic (they fight the joint and pollute force readings).
    filtered_robot_links: tuple[str, ...] = ("panda_hand", "panda_leftfinger", "panda_rightfinger")
