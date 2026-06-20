"""Spawners for the physically attached peg.

The peg must be a dynamic rigid body so PhysX resolves peg/socket-wall
contacts (the 2026-06-11 audit showed kinematic-kinematic pairs produce no
reaction at all). It is rigidly attached to the robot hand with a USD
``PhysicsFixedJoint`` authored at spawn time, inside the ``env_0`` template,
so the scene cloner replicates the joint per environment exactly like the
robot's own joints. Authoring before the simulation starts avoids the
runtime-joint-creation pitfalls of doing this in a startup event.

The first maximal-coordinate variant marked the joint
``excludeFromArticulation`` so the peg remained a standalone ``RigidObject``.
The 2026-06-20 Launchable smoke showed that model did not constrain the peg to
the hand. The default now keeps the peg in the articulation tree so PhysX has a
single reduced-coordinate chain to solve. ``exclude_from_articulation`` remains
available only as a legacy diagnostic switch for A/B smoke runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import isaaclab.sim as sim_utils
from isaaclab.sim.utils import find_matching_prim_paths
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

from robot_contact_assembly_tasks._compat import configclass

if TYPE_CHECKING:
    from pxr import Usd


def _gf_quat_from_wxyz(quat_wxyz: tuple[float, float, float, float]) -> Gf.Quatf:
    """Convert Isaac Lab WXYZ quaternions to USD's scalar-first Gf.Quatf."""

    w, x, y, z = (float(v) for v in quat_wxyz)
    return Gf.Quatf(w, Gf.Vec3f(x, y, z))


def _gf_quatd_from_wxyz(quat_wxyz: tuple[float, float, float, float]) -> Gf.Quatd:
    """Convert Isaac Lab WXYZ quaternions to USD's scalar-first Gf.Quatd."""

    w, x, y, z = (float(v) for v in quat_wxyz)
    return Gf.Quatd(w, Gf.Vec3d(x, y, z))


def _matrix_from_pos_quat_wxyz(
    pos: tuple[float, float, float],
    quat_wxyz: tuple[float, float, float, float],
) -> Gf.Matrix4d:
    """Build a USD transform matrix from the repo's calibrated local joint frame."""

    matrix = Gf.Matrix4d(1.0)
    matrix.SetRotate(_gf_quatd_from_wxyz(quat_wxyz))
    matrix.SetTranslateOnly(Gf.Vec3d(*(float(v) for v in pos)))
    return matrix


def _compute_local_matrix_for_world_pose(prim: "Usd.Prim", world_matrix: Gf.Matrix4d) -> Gf.Matrix4d:
    """Convert a target world matrix into the prim parent's local space."""

    parent = prim.GetParent()
    if not parent or not parent.IsValid():
        return world_matrix

    parent_xform = UsdGeom.Xformable(parent)
    if not parent_xform:
        return world_matrix

    parent_world = parent_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    return world_matrix * parent_world.GetInverse()


def _align_peg_prim_to_joint_frame(
    peg_prim: "Usd.Prim",
    hand_prim: "Usd.Prim",
    cfg: "AttachedPegCylinderCfg",
) -> None:
    """Seed the peg pose so the fixed-joint frames coincide before PhysX starts.

    OpenUSD/Gf matrices use row-vector composition: the left matrix is the more
    local transform. The desired peg world pose is therefore
    ``joint_local_frame * hand_world`` because ``localPos1/localRot1`` are the
    peg body origin. Starting there avoids PhysX creating a disjointed joint and
    snapping the peg before the reset event can seed the runtime state.
    """

    hand_world = UsdGeom.Xformable(hand_prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    joint_local = _matrix_from_pos_quat_wxyz(cfg.joint_local_pos0, cfg.joint_local_rot0_wxyz)
    peg_world = joint_local * hand_world
    peg_local = _compute_local_matrix_for_world_pose(peg_prim, peg_world)

    peg_xform = UsdGeom.Xformable(peg_prim)
    peg_xform.ClearXformOpOrder()
    peg_xform.MakeMatrixXform().Set(peg_local)


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
        peg_prim = stage.GetPrimAtPath(Sdf.Path(peg_path))
        hand_prim = stage.GetPrimAtPath(Sdf.Path(hand_path))
        _align_peg_prim_to_joint_frame(peg_prim, hand_prim, cfg)

        joint = UsdPhysics.FixedJoint.Define(stage, Sdf.Path(f"{peg_path}/{cfg.attach_joint_name}"))
        joint.CreateBody0Rel().SetTargets([Sdf.Path(hand_path)])
        joint.CreateBody1Rel().SetTargets([Sdf.Path(peg_path)])
        joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*(float(v) for v in cfg.joint_local_pos0)))
        joint.CreateLocalRot0Attr().Set(_gf_quat_from_wxyz(cfg.joint_local_rot0_wxyz))
        joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
        joint.CreateLocalRot1Attr().Set(Gf.Quatf(1.0))
        joint.CreateExcludeFromArticulationAttr().Set(bool(cfg.exclude_from_articulation))

        if cfg.filtered_robot_links:
            filtered = UsdPhysics.FilteredPairsAPI.Apply(stage.GetPrimAtPath(Sdf.Path(peg_path)))
            pairs_rel = filtered.CreateFilteredPairsRel()
            for link_name in cfg.filtered_robot_links:
                pairs_rel.AddTarget(Sdf.Path(f"{robot_path}/{link_name}"))

    return prim


@configclass
class AttachedPegCylinderCfg(sim_utils.CylinderCfg):
    """Cylinder spawn config that also welds the peg to the robot hand.

    ``joint_local_pos0`` / ``joint_local_rot0_wxyz`` define the peg-root
    (cylinder center) frame relative to the hand body frame, i.e. the same
    transform the old kinematic ``sync_peg_to_hand`` event enforced. The
    rotation uses Isaac Lab's WXYZ convention, which is also USD's scalar-first
    quaternion convention.
    """

    func: Callable = spawn_attached_peg_cylinder

    robot_prim_name: str = "Robot"
    hand_link_name: str = "panda_hand"
    attach_joint_name: str = "PegHandFixedJoint"
    joint_local_pos0: tuple[float, float, float] = (0.0, 0.0, 0.0)
    joint_local_rot0_wxyz: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    # Default False is the next physical-model candidate after the excluded
    # maximal joint failed the remote attach/contact smoke on 2026-06-20.
    exclude_from_articulation: bool = False
    # The gripper fingers interpenetrate the welded peg by construction; their
    # contacts are parasitic (they fight the joint and pollute force readings).
    filtered_robot_links: tuple[str, ...] = ("panda_hand", "panda_leftfinger", "panda_rightfinger")
