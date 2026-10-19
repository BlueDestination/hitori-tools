import bpy
from bpy.types import Object

from hitori_addon.mesh import get_axis_range
from hitori_addon.obj import select_objs, set_mode


def fit_screen_view(
    objs: list[Object],
    min_z: float | None = None,
    max_z: float | None = None,
    view_ratio: float = 1.3044,
    view_margin: float = -0.0015,
):
    z_ranges = [
        get_axis_range(obj, axis="z", local=False) for obj in objs if obj.type == "MESH"
    ]

    if min_z is None:
        min_z = min(z_ranges, key=lambda x: x[0])[0]
    if max_z is None:
        max_z = max(z_ranges, key=lambda x: x[1])[1]

    center_z = (min_z + max_z) / 2
    view_distance = view_ratio * (max_z - min_z) + view_margin

    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.region_3d.view_location = [0, 0, center_z]
                space.region_3d.view_distance = view_distance


def set_view_shading(shading_type: str) -> None:
    """所有 3D 视图的着色方式 (WIREFRAME / SOLID ...)"""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.shading.type = shading_type


def enter_weight_paint(objs: list[Object], vg_name: str) -> bool:
    """切到线框着色 + 权重模式, 激活顶点组设为 vg_name (多选网格一起看), 返回是否切换了

    线框着色能透视看到背面的顶点组, 省得用户自己按 Shift+Z 和找权重模式。
    """
    if bpy.app.background:
        return False

    meshes = [obj for obj in objs if obj.type == "MESH"]
    if not meshes:
        return False

    set_mode("OBJECT")
    for obj in meshes:
        vg = obj.vertex_groups.get(vg_name)
        if vg is not None:
            obj.vertex_groups.active = vg
    select_objs(meshes)
    set_mode("WEIGHT_PAINT")
    set_view_shading("WIREFRAME")
    return True
