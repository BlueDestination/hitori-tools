from collections.abc import Sequence

import bpy
import numpy as np
from bpy.types import Bone, Object
from mathutils import Matrix

from hitori_addon.obj import (
    clear_parent,
    copy_obj,
    get_objs,
    move_to_bak_collection,
    reset_mode,
    reset_mode_and_selected,
    select_obj,
    set_mode,
)

DEFAULT_TAIL_OFFSET = np.array([0.0, 0.0, 0.05])
LEAF_BONE_SUFFIX = "_end"
# 末端骨长度 (沿世界 Z 轴, 与原脚本一致)
LEAF_BONE_LENGTH = 0.005


def get_children_recursive_bone_names(arm: Object, parent_bone_name: str) -> list[str]:
    parent_bone = arm.data.bones.get(parent_bone_name)
    if parent_bone:
        return [bone.name for bone in parent_bone.children_recursive]
    else:
        return []


def get_root_bones(arm: Object) -> list[Bone]:
    return [bone for bone in arm.data.bones if bone.parent is None]


def get_root_bone_names(arm: Object) -> list[str]:
    return [bone.name for bone in get_root_bones(arm)]


@reset_mode
def delete_bones(arm: Object, delete_bone_names: list[str] | set[str]):
    select_obj(arm)
    set_mode("EDIT")
    edit_bones = arm.data.edit_bones

    delete_bone_names = set(get_bone_names(arm)) & set(delete_bone_names)
    for delete_bone_name in delete_bone_names:
        edit_bones.remove(edit_bones[delete_bone_name])


def selected_arms() -> list[Object]:
    return [obj for obj in bpy.context.selected_objects if obj.type == "ARMATURE"]


def get_leaf_bone_names(arm: Object) -> list[str]:
    """叶子骨骼名 (用 parent 反推, Bone.children 在编辑模式改动后可能不同步)"""
    parents = {bone.parent.name for bone in arm.data.bones if bone.parent}
    return [bone.name for bone in arm.data.bones if bone.name not in parents]


def _add_leaf_bone_by_extrude(arm: Object, leaf_names: list[str]) -> list[str]:
    """编辑模式内给指定叶子骨挤出末端骨并改名, 返回新骨骼名"""
    edit_bones = arm.data.edit_bones
    for bone in edit_bones:
        bone.select = bone.select_head = bone.select_tail = False
    for name in leaf_names:
        edit_bones[name].select = True
        edit_bones[name].select_tail = True

    before_names = {bone.name for bone in edit_bones}
    bpy.ops.armature.extrude_move(
        TRANSFORM_OT_translate={"value": (0, 0, LEAF_BONE_LENGTH)}
    )
    created = [bone for bone in edit_bones if bone.name not in before_names]
    for bone in created:
        if bone.parent and bone.length > 0:
            bone.name = bone.parent.name + LEAF_BONE_SUFFIX

    # 只选中突出的关节 (末端骨的尾点), 不选中整个骨骼
    names = [bone.name for bone in created if bone.length > 0]
    created_names = set(names)
    for bone in edit_bones:
        is_new = bone.name in created_names
        bone.select = False
        bone.select_head = False
        bone.select_tail = is_new
    return names


@reset_mode_and_selected
def add_leaf_bones(arm: Object) -> tuple[list[str], int]:
    """给叶子骨骼各加一根末端骨 (名为 xxx_end), 返回 (新增骨骼名, 跳过的数量)

    已带 _end 的骨骼跳过, 可重复执行; 不改原有骨骼名 (网格顶点组仍然对得上骨骼)。
    只选中新增末端骨的尾点 (关节), 不选中整根骨骼; 没活干时不进编辑模式 (不动原有选择)。
    """
    leaves = get_leaf_bone_names(arm)
    todo = [name for name in leaves if not name.endswith(LEAF_BONE_SUFFIX)]
    skipped = len(leaves) - len(todo)
    if not todo:
        return [], skipped

    layers = list(arm.data.layers)
    select_obj(arm)
    set_mode("EDIT")
    # 隐藏层里的骨骼选不中 (挤不出末端骨), 临时全开
    arm.data.layers = [True] * len(layers)
    try:
        names = _add_leaf_bone_by_extrude(arm, todo)
    finally:
        arm.data.layers = layers
    set_mode("OBJECT")
    return [name for name in names if arm.data.bones.get(name)], skipped


def get_bone_names(arm: Object) -> list[str]:
    return [bone.name for bone in arm.data.bones]


def get_arm_meshes(arm: Object) -> list[Object]:
    """绑定到该骨架的网格(骨架修改器指向它, 或父级是它)"""
    return [
        obj
        for obj in get_objs("MESH")
        if obj.parent is arm
        or any(
            modifier.type == "ARMATURE" and modifier.object is arm
            for modifier in obj.modifiers
        )
    ]


def get_bones_with_weighted_subtree(
    arm: Object, weighted_names: set[str]
) -> set[str]:
    """自身或子树里含这些权重的骨骼(即有权重的骨骼 + 它们的全部祖先)"""
    bones = arm.data.bones
    kept: set[str] = set()
    for name in weighted_names:
        bone = bones.get(name)
        while bone is not None and bone.name not in kept:
            kept.add(bone.name)
            bone = bone.parent
    return kept


def delete_unweighted_bone_trees(
    arm: Object, weighted_names: set[str], backup: bool = False
) -> list[str]:
    """删除所有分支都没有权重的骨骼树, 返回被删的骨骼名"""
    if not weighted_names:
        # 没有任何权重信息时不动骨架, 避免误删整个骨架
        return []

    kept = get_bones_with_weighted_subtree(arm, weighted_names)
    deleted_names = [name for name in get_bone_names(arm) if name not in kept]
    if deleted_names:
        if backup:
            backup_bones(arm, set(deleted_names), name=f"bak_{arm.name}_deleted")
        # edit_bones.remove 会把子骨接到父骨的父级上, 不传子骨就会残留下来
        delete_bones(arm, deleted_names)
    return deleted_names


def backup_bones(arm: Object, bone_names: set[str], name: str | None = None) -> Object:
    """复制骨架, 只留下 bone_names 里的骨骼(其余删掉), 放进 bak 集合备查"""
    backup_arm = copy_obj(arm, name=name or f"bak_{arm.name}")
    # 不跟着原骨架的父级(空物体之后会被删掉), 保持世界位置
    clear_parent(backup_arm)

    kept_names = [name for name in get_bone_names(backup_arm) if name not in bone_names]
    delete_bones(backup_arm, kept_names)

    move_to_bak_collection(backup_arm)
    return backup_arm


@reset_mode
def rest_arm(arm: Object):
    if arm.data.pose_position != "REST":
        arm.data.pose_position = "REST"


@reset_mode
def apply_arm(arm: Object):
    select_obj(arm)
    set_mode("POSE")
    bpy.ops.pose.armature_apply()


@reset_mode
def clear_pose(arm: Object) -> None:
    """清空姿态通道(骨架回到静置)"""
    for pose_bone in arm.pose.bones:
        pose_bone.matrix_basis = Matrix.Identity(4)


def freeze_pose(arm: Object) -> None:
    """把当前可视状态固化成静置骨架, 并清空姿态通道

    `apply_arm` 把姿态写进 rest 并把姿态通道归零; 但骨架显示为静置(`pose_position` 是 REST)
    时姿态本身看不见, 此时只清空姿态通道, rest 保持原样。
    """
    if arm.data.pose_position == "REST":
        clear_pose(arm)
    else:
        apply_arm(arm)


@reset_mode
def create_parent_bone(
    arm: Object,
    parent_bone_name: str,
    child_bone_names: list[str],
    set_x_zero: bool = False,
    tail_offset: Sequence[float] | np.ndarray = DEFAULT_TAIL_OFFSET,
    select: bool = False,
) -> Bone:
    # 只有在EDIT模式才能获取EditBones对象
    select_obj(arm)
    set_mode("EDIT")
    edit_bones = arm.data.edit_bones

    parent_edit_bone = edit_bones.new(parent_bone_name)
    child_edit_bones = [edit_bones[name] for name in child_bone_names]

    # 设置父级
    for child_edit_bone in child_edit_bones:
        child_edit_bone.parent = parent_edit_bone

    # 父级骨骼的头尾位置用原来的多个子级骨骼的均值(x除外,x取0)
    parent_edit_bone_head = np.mean(
        [child_edit_bone.head for child_edit_bone in child_edit_bones], axis=0
    )
    if set_x_zero:
        parent_edit_bone_head[0] = 0
    parent_edit_bone_tail = parent_edit_bone_head + np.asarray(tail_offset)

    parent_edit_bone.head = parent_edit_bone_head
    parent_edit_bone.tail = parent_edit_bone_tail

    # 选中父级骨骼(如需)
    if select:
        for edit_bone in edit_bones:
            edit_bone.select = False
        parent_edit_bone.select = True

    # 编辑完EditBones后需要退出Edit模式后Bones对象才会刷新
    # 退出Edit模式后EditBones会清空,需要提前存储EditBones数据
    parent_edit_bone_name = parent_edit_bone.name
    set_mode("OBJECT")
    return arm.data.bones[parent_edit_bone_name]
