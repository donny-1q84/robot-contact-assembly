"""Shared geometry constants for the contact-guided peg-in-hole shell."""

# Controller-side tip frame used by the relative IK action. This stays aligned with the
# Phase 1 proxy task so old checkpoints still target the same nominal tip pose.
PEG_TIP_BODY_OFFSET_POS = (0.0, 0.0, 0.1034)
PEG_TIP_BODY_OFFSET_ROT = (0.0, 0.0, 0.41435253798529015, 0.9101164619240488)
PEG_TIP_YAW_OFFSET_RAD = 0.8544625639915466

# Physical peg geometry.
PEG_RADIUS_M = 0.010
PEG_LENGTH_M = 0.080
PEG_CENTER_BODY_OFFSET_POS = (0.0, 0.0, PEG_TIP_BODY_OFFSET_POS[2] - 0.5 * PEG_LENGTH_M)
PEG_CENTER_BODY_OFFSET_ROT = PEG_TIP_BODY_OFFSET_ROT
PEG_TIP_FROM_CENTER_POS = (0.0, 0.0, 0.5 * PEG_LENGTH_M)

# Fixed contact guide geometry. This is intentionally a simple square guide channel rather
# than a CAD-accurate socket so the first contact milestone stays easy to debug.
SOCKET_FRAME_POS = (0.520, 0.000, 0.190)
SOCKET_FRAME_ROT = (0.0, 0.0, 1.0, 0.0)
SOCKET_GUIDE_CLEARANCE_M = 0.0015
SOCKET_GUIDE_WALL_THICKNESS_M = 0.0060
SOCKET_GUIDE_DEPTH_M = 0.060
SOCKET_GUIDE_INNER_HALF_WIDTH_M = PEG_RADIUS_M + SOCKET_GUIDE_CLEARANCE_M
SOCKET_GUIDE_OUTER_HALF_WIDTH_M = SOCKET_GUIDE_INNER_HALF_WIDTH_M + SOCKET_GUIDE_WALL_THICKNESS_M

# Success tolerances are now evaluated against the physical socket frame instead of the
# old commanded proxy target.
SOCKET_SUCCESS_XY_TOLERANCE_M = 0.005
SOCKET_SUCCESS_Z_TOLERANCE_M = 0.008
SOCKET_SUCCESS_ROT_TOLERANCE_RAD = 0.18
