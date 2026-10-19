from collections.abc import Callable, Iterable, Sequence

from bpy.types import Material, Object

from hitori_addon.error import ObjectError
from hitori_addon.sb3u import ACC_MESH_NAMES, CLOTH_MESH_NAMES


def is_cloth_mesh(obj: Object) -> bool:
    return obj.name in CLOTH_MESH_NAMES


def is_acc_mesh(obj: Object) -> bool:
    return obj.name in ACC_MESH_NAMES


def is_mmd_material(material: Material) -> bool:
    return any(node.name == "mmd_base_tex" for node in material.node_tree.nodes)


def require_meshes(
    objs: Iterable[Object],
    is_valid: Callable[[Object], bool],
    kind: str,
    valid_names: Sequence[str],
) -> None:
    """选中的网格里有名称不合法的就直接报错, 报错里列出合法名"""
    invalid_objs = [obj for obj in objs if not is_valid(obj)]
    if invalid_objs:
        raise ObjectError(
            invalid_objs,
            f"选中的网格中包含非{kind}网格\n合法{kind}网格名称: {', '.join(valid_names)}",
        )


def require_cloth_meshes(objs: Iterable[Object]) -> None:
    require_meshes(objs, is_cloth_mesh, "服装", CLOTH_MESH_NAMES)


def require_acc_meshes(objs: Iterable[Object]) -> None:
    require_meshes(objs, is_acc_mesh, "饰品", ACC_MESH_NAMES)
