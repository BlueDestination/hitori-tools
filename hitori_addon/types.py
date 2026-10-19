from typing import Literal

AXIS = Literal["x", "y", "z"]

DATA_TRANSFER_VERT_MAPPING = Literal[
    "TOPOLOGY",
    "NEAREST",
    "EDGE_NEAREST",
    "EDGEINTERP_NEAREST",
    "POLY_NEAREST",
    "POLYINTERP_NEAREST",
    "POLYINTERP_VNORPROJ",
]

BLENDER_MODES = Literal[
    "OBJECT",
    "EDIT",
    "SCULPT",
    "VERTEX_PAINT",
    "WEIGHT_PAINT",
    "TEXTURE_PAINT",
    "POSE",
]

OBJECT_TYPES = Literal[
    "MESH",
    "ARMATURE",
    "EMPTY",
    "CAMERA",
    "CURVE",
    "SURFACE",
    "META",
    "LATTICE",
    "LIGHT",
    "SPEAKER",
]
