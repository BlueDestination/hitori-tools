from collections.abc import Callable, Iterable, Sequence
from functools import wraps
from typing import Any

import bpy
from bpy.types import Collection, Object
from mathutils import Matrix, Quaternion, Vector

from hitori_addon.acc import KkAcc
from hitori_addon.types import BLENDER_MODES, OBJECT_TYPES

IDENTITY_MATRIX: Matrix = Matrix.Identity(4)
UNITY_MATRIX: Matrix = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
BAK_COLLECTION_NAME = "bak"


def get_root_objs(selected: bool = False) -> list[Object] | Iterable[Object]:
    objs = bpy.context.selected_objects if selected else bpy.data.objects
    return [obj for obj in objs if obj.parent is None]


def get_obj(name: str) -> Object | None:
    return bpy.data.objects.get(name)


def get_objs(
    type_name: str | None = None, selected: bool = False
) -> list[Object] | Iterable[Object]:
    objs = bpy.context.selected_objects if selected else bpy.data.objects
    if type_name:
        return [obj for obj in objs if obj.type == type_name]
    else:
        return objs


def selected_objs() -> list[Object] | Iterable[Object]:
    return bpy.context.selected_objects


def set_mode(
    mode: BLENDER_MODES,
    active_object: Object | None = None,
    check: bool = True,
):
    if not check:
        bpy.ops.object.mode_set(mode=mode)
        return

    if active_object is None:
        active_object = bpy.context.active_object

    if active_object and active_object.mode != mode:
        bpy.ops.object.mode_set(mode=mode)


def reset_mode(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        obj = bpy.context.active_object
        previous_mode = obj.mode if obj else "OBJECT"

        result = func(*args, **kwargs)

        obj_after = bpy.context.active_object
        if obj_after and obj_after.mode != previous_mode:
            set_mode(previous_mode, obj_after, check=False)

        return result

    return wrapper


def reset_mode_and_selected(func: Callable) -> Callable:
    @reset_selected
    @reset_mode
    def wrapper(*args, **kwargs) -> Any:
        return func(*args, **kwargs)

    return wrapper


def reset_selected(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        obj = bpy.context.active_object
        objs = bpy.context.selected_objects

        result = func(*args, **kwargs)

        obj_after = bpy.context.active_object
        objs_after = bpy.context.selected_objects

        if obj is obj_after and set(objs) == set(objs_after):
            return result

        select_objs(objs)
        activate_obj(obj)
        return result

    return wrapper


class ObjectState:
    """记录运行前视图层里各物体的 active 物体 / 模式 / 选择 / 可见性, 用于运行后还原

    只记录进入时在视图层里的物体, 运行中新建的物体不受影响
    """

    def __init__(self):
        view_layer = bpy.context.view_layer
        self.active_obj = view_layer.objects.active
        self.mode = self.active_obj.mode if self.active_obj else "OBJECT"
        self.states = [
            (obj, obj.select_get(), obj.hide_get(), obj.hide_viewport, obj.hide_render)
            for obj in view_layer.objects
        ]

    def restore(self):
        active_obj = bpy.context.view_layer.objects.active
        if active_obj and active_obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        for obj in bpy.context.view_layer.objects:
            obj.select_set(False)

        for obj, selected, hidden, hide_viewport, hide_render in self.states:
            obj.hide_viewport = hide_viewport
            obj.hide_render = hide_render
            obj.hide_set(hidden)
            if selected:
                obj.select_set(True)

        if self.active_obj:
            bpy.context.view_layer.objects.active = self.active_obj
            if self.mode != "OBJECT":
                bpy.ops.object.mode_set(mode=self.mode)


def deselect_obj(obj: Object):
    obj.select_set(False)


def select_obj(obj: Object, deselect_others: bool = True, active: bool = True):
    if deselect_others:
        for any_obj in bpy.data.objects:
            any_obj.select_set(False)

    obj.hide_set(False)
    obj.select_set(True)

    if active:
        activate_obj(obj)


def select_objs(objs: list[Object] | Iterable[Object]):
    for i, obj in enumerate(objs):
        if i == 0:
            select_obj(obj, deselect_others=True, active=True)
        else:
            select_obj(obj, deselect_others=False, active=False)


def hide_obj(obj: Object):
    obj.hide_set(True)


def hide_objs(objs: list[Object] | Iterable[Object]):
    for obj in objs:
        obj.hide_set(True)


def hide_render_objs(objs: list[Object] | Iterable[Object]):
    for obj in objs:
        obj.hide_render = True


def show_obj(obj: Object):
    obj.hide_set(False)


def show_objs(objs: list[Object] | Iterable[Object]):
    for obj in objs:
        obj.hide_set(False)


def only_show_objs(objs: list[Object] | Iterable[Object]):
    show_names = {obj.name for obj in objs}
    for obj in bpy.context.view_layer.objects:
        obj.hide_set(obj.name not in show_names)


def move_obj(obj: Object, translation: Sequence[float]):
    obj.matrix_world = Matrix.Translation(translation) @ obj.matrix_world


def get_inverse_acc_matrix(kk_acc: KkAcc) -> Matrix:
    """饰品挂点的逆变换: 游戏把饰品 parent 到挂点, 位置和旋转都完整继承"""
    rot_x, rot_y, rot_z, rot_w = kk_acc.rot
    rot_unity = Quaternion((rot_w, rot_x, rot_y, rot_z)).to_matrix().to_4x4()
    rot_blender = UNITY_MATRIX @ rot_unity @ UNITY_MATRIX.inverted()
    return rot_blender.inverted() @ Matrix.Translation(Vector(kk_acc.pos) * -1)


def set_acc_matrix(obj: Object, kk_acc: KkAcc):
    obj.matrix_world = get_inverse_acc_matrix(kk_acc) @ obj.matrix_world


def set_matrix(obj: Object, matrix: Matrix):
    if obj.type == "MESH":
        obj.data.transform(matrix.inverted() @ obj.matrix_world, shape_keys=True)
    else:
        obj.data.transform(matrix.inverted() @ obj.matrix_world)

    obj.matrix_world = matrix


def reset_matrix(obj: Object):
    set_matrix(obj, IDENTITY_MATRIX)


def set_unity_matrix(obj: Object):
    set_matrix(obj, UNITY_MATRIX)


def apply_transform(obj: Object):
    """只应用当前物体变换,子物体会保持原样"""
    reset_matrix(obj)


def clear_parent(obj: Object):
    obj.parent, obj.matrix_world = None, obj.matrix_world


def copy_obj(obj: Object, name: str | None = None) -> Object:
    new_obj = obj.copy()
    new_obj.data = obj.data.copy()

    if name:
        new_obj.name = name

    bpy.context.collection.objects.link(new_obj)
    return new_obj


def copy_objs(objs: list[Object] | Iterable[Object]) -> list[Object]:
    new_objs = []
    for obj in objs:
        new_obj = copy_obj(obj)
        new_objs.append(new_obj)

    return new_objs


def get_bak_collection() -> Collection:
    bak_collection = bpy.data.collections.get(BAK_COLLECTION_NAME)
    if bak_collection is None:
        bak_collection = bpy.data.collections.new(BAK_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(bak_collection)
    return bak_collection


def move_to_bak_collection(obj: Object) -> None:
    """隐藏后放进 bak 集合(整个集合从视图层排除, 相当于不可见)"""
    # 隐藏必须在物体还在视图层里时做, 排除了就无法 hide_set
    hide_obj(obj)

    for collection in obj.users_collection:
        collection.objects.unlink(obj)
    get_bak_collection().objects.link(obj)

    bak_layer_collection = bpy.context.view_layer.layer_collection.children.get(
        BAK_COLLECTION_NAME
    )
    if bak_layer_collection:
        bak_layer_collection.exclude = True


def backup_obj(obj: Object, name: str | None = None) -> Object:
    """复制为 bak_<名> 放进 bak 集合备查"""
    backup = copy_obj(obj, name=name or f"bak_{obj.name}")
    deselect_obj(backup)
    move_to_bak_collection(backup)
    return backup


def activate_obj(obj: Object):
    bpy.context.view_layer.objects.active = obj


@reset_mode
def merge_objs(
    objs: list[Object] | Iterable[Object],
    target_obj: Object | None = None,
) -> Object | None:
    objs_len = len(objs)

    if objs_len == 0:
        return None

    if objs_len == 1:
        return objs[0]

    if not target_obj:
        active_obj = bpy.context.active_object

        if active_obj in objs:
            target_obj = active_obj
        else:
            target_obj = objs[0]

    set_mode("OBJECT")
    select_objs(objs)
    activate_obj(target_obj)
    bpy.ops.object.join()


def delete_obj(obj: Object) -> None:
    bpy.data.objects.remove(obj)


def create_obj(obj_name: str, obj_type: OBJECT_TYPES) -> Object:
    if obj_type == "MESH":
        obj_data = bpy.data.meshes.new(obj_name)
    elif obj_type == "ARMATURE":
        obj_data = bpy.data.armatures.new(obj_name)
    elif obj_type == "EMPTY":
        obj_data = None
    elif obj_type == "CAMERA":
        obj_data = bpy.data.cameras.new(obj_name)
    elif obj_type == "CURVE":
        obj_data = bpy.data.curves.new(obj_name, "CURVE")
    elif obj_type == "SURFACE":
        obj_data = bpy.data.curves.new(obj_name, "SURFACE")
    elif obj_type == "META":
        obj_data = bpy.data.metaballs.new(obj_name)
    elif obj_type == "LATTICE":
        obj_data = bpy.data.lattices.new(obj_name)
    elif obj_type == "LIGHT":
        obj_data = bpy.data.lights.new(name=obj_name, type="POINT")
    elif obj_type == "SPEAKER":
        obj_data = bpy.data.speakers.new(obj_name)
    else:
        raise TypeError(f"创建的物体类型无效: {obj_type}")

    obj = bpy.data.objects.new(name=obj_name, object_data=obj_data)
    bpy.context.collection.objects.link(obj)
    return obj
