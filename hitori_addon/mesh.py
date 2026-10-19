from collections.abc import Iterable, Sequence

import bpy
import numpy as np
from bpy.types import MeshVertex, Modifier, Object, ShapeKey, bpy_prop_collection
from mathutils import Vector

from hitori_addon.const import AXIS_INDEX_MAP
from hitori_addon.error import ObjectError
from hitori_addon.math import vecs_apply_mat
from hitori_addon.obj import (
    reset_mode,
    reset_mode_and_selected,
    select_obj,
    select_objs,
    set_mode,
)
from hitori_addon.types import AXIS, DATA_TRANSFER_VERT_MAPPING


@reset_mode_and_selected
def remove_unused_material_slot(objs: Iterable[Object] | Object):
    if not isinstance(objs, Iterable):
        objs = [objs]
    set_mode("OBJECT")
    select_objs(objs)
    bpy.ops.object.material_slot_remove_unused()


def get_axis_range(
    obj: Object,
    axis: AXIS,
    local: bool = True,
) -> tuple[float, float]:
    axis_index = AXIS_INDEX_MAP.get(axis)
    if axis_index is None:
        raise ValueError('axis must be "x", "y", or "z"')

    coordinates_arr = np.asarray(get_coordinates_arr(obj))
    if not local:
        coordinates_arr = vecs_apply_mat(coordinates_arr, obj.matrix_world)

    axis_values = coordinates_arr[:, axis_index]
    return np.min(axis_values), np.max(axis_values)


def get_coordinates_arr(obj: Object) -> np.ndarray:
    """使用foreach_get获取'co'比使用vertex.co列表推导式获取坐标快20倍"""
    vertices_collection: bpy_prop_collection = obj.data.vertices
    coordinates_arr = np.empty((len(vertices_collection), 3), "f")
    vertices_collection.foreach_get("co", coordinates_arr.ravel())
    return coordinates_arr


def get_face_normals_arr(obj: Object) -> np.ndarray:
    faces_collection: bpy_prop_collection = obj.data.polygons
    face_normals_arr = np.empty((len(faces_collection), 3), "f")
    faces_collection.foreach_get("normal", face_normals_arr.ravel())
    return face_normals_arr


def get_face_centers_arr(obj: Object) -> np.ndarray:
    faces_collection: bpy_prop_collection = obj.data.polygons
    face_centers_arr = np.empty((len(faces_collection), 3), "f")
    faces_collection.foreach_get("center", face_centers_arr.ravel())
    return face_centers_arr


def get_vertex_normals_arr(obj: Object) -> np.ndarray:
    vertices_collection: bpy_prop_collection = obj.data.vertices
    vertex_normals_arr = np.empty((len(vertices_collection), 3), "f")
    vertices_collection.foreach_get("normal", vertex_normals_arr.ravel())
    return vertex_normals_arr


@reset_mode
def delete_faces(obj: Object, indices: np.ndarray | list[int]) -> None:
    # 在物体模式修改物体数据(在编辑模式修改物体数据会在退出编辑模式后被覆盖)
    set_mode("OBJECT")

    # 生成面选中状态布尔数组,然后使用foreach_set设置数据
    faces_collection: bpy_prop_collection = obj.data.polygons
    face_select_state_arr = np.zeros((len(faces_collection),), dtype=bool)
    face_select_state_arr[indices] = True
    faces_collection.foreach_set("select", face_select_state_arr)

    # 进入编辑模式刷新选中状态,然后删除选中的面
    select_obj(obj)
    set_mode("EDIT")
    bpy.ops.mesh.delete(type="FACE")


def add_key(
    obj: Object,
    key_name: str = "Key",
    from_mix: bool = True,
    select: bool = False,
) -> ShapeKey:
    new_key = obj.shape_key_add(name=key_name, from_mix=from_mix)

    if select:
        keys = get_keys(obj)
        new_key_index = len(keys) - 1
        obj.active_shape_key_index = new_key_index

    return new_key


def get_keys(
    obj: Object,
    create_if_none: bool = False,
    create_name: str = "Basis",
) -> Sequence[ShapeKey] | dict[str, ShapeKey]:
    Key = obj.data.shape_keys
    if not Key:
        if create_if_none:
            obj.shape_key_add(name=create_name)
            Key = obj.data.shape_keys
        else:
            raise ObjectError(obj, "选中的物体没有形态键")

    keys = Key.key_blocks
    return keys


def get_key_names(obj: Object) -> list[str]:
    return [key.name for key in get_keys(obj)]


def set_armature_modifier(obj: Object, arm: Object) -> Modifier:
    modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = arm
    return modifier


def selected_meshes() -> list[Object]:
    return [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]


@reset_mode
def transfer_weight(
    obj: Object,
    target_obj: Object,
    use_vg: str | None = None,
    vert_mapping: DATA_TRANSFER_VERT_MAPPING = "POLYINTERP_NEAREST",
    invert_vg: bool = False,
):
    """从 target_obj 传顶点组权重给 obj, use_vg 限定范围, invert_vg 时只传范围外的顶点"""
    modifier = obj.modifiers.new(name="DataTransfer", type="DATA_TRANSFER")
    if use_vg:
        modifier.vertex_group = use_vg
        modifier.invert_vertex_group = invert_vg

    modifier.object = target_obj
    modifier.use_vert_data = True
    modifier.data_types_verts = {"VGROUP_WEIGHTS"}
    modifier.vert_mapping = vert_mapping

    select_obj(obj)
    if obj.mode == "EDIT":
        # 如果在编辑模式会无法应用修改器,需要进入物体模式
        set_mode("OBJECT")
    bpy.ops.object.datalayout_transfer(modifier=modifier.name)
    bpy.ops.object.modifier_apply(modifier=modifier.name)


@reset_mode
def apply_mesh(obj: Object):
    apply_meshes([obj])


@reset_mode
def apply_meshes(objs: list[Object]):
    set_mode("OBJECT")
    select_objs(objs)
    bpy.ops.object.convert(target="MESH")


def get_clipping_vertex_indices(obj: Object, compare_obj: Object) -> list[int]:
    clipping_vertex_indexes = [
        i
        for i, vertex in enumerate(obj.data.vertices)
        if is_vertex_inside_mesh(vertex.co, compare_obj)
    ]
    return clipping_vertex_indexes


def get_clipping_vertex_indices_new_slower(
    obj: Object, compare_obj: Object
) -> list[int]:
    coordinates_arr = get_coordinates_arr(obj)
    coordinates_arr = list(map(Vector, coordinates_arr))
    clipping_vertex_indexes = [
        i
        for i, coordinate in enumerate(coordinates_arr)
        if is_vertex_inside_mesh(coordinate, compare_obj)
    ]
    return clipping_vertex_indexes


def is_vertex_inside_mesh(
    vertex_co: Vector,
    mesh: Object,
    directions: tuple[Vector, ...] = (
        Vector((0, 2, 0)),
        Vector((0, -2, 0)),
        Vector((2, 0, 0)),
        Vector((-2, 0, 0)),
        Vector((0, 0, 2)),
        Vector((0, 0, -2)),
    ),
    distance: float = 2.0,
) -> bool:
    # 从容易为False的开始判断以节约时间,任何方向未命中网格则说明在网格外,提前返回False
    for direction in directions:
        if not is_ray_hit_mesh(vertex_co, direction, distance, mesh):
            return False
    return True


def is_ray_hit_mesh(
    origin: Vector,
    direction: Vector,
    distance: float,
    mesh: Object,
) -> bool:
    # mesh.ray_cast返回hit_flag, _location, _normal, _face_index
    return mesh.ray_cast(origin, origin + direction, distance=distance)[0]


def selected_vertices(obj: Object) -> list[MeshVertex]:
    return [vertex for vertex in obj.data.vertices if vertex.select]


def selected_vertex_indices_arr(obj: Object) -> np.ndarray:
    vertices_collection: bpy_prop_collection = obj.data.vertices
    selects_arr = np.empty((len(vertices_collection),), bool)
    vertices_collection.foreach_get("select", selects_arr.ravel())
    return np.where(selects_arr)[0]


def get_vertex_indices(obj: Object) -> list[int]:
    return list(range(len(obj.data.vertices)))
