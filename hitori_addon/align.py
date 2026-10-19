"""对齐官方骨架

把 VRC / MMD 骨架对齐到官方骨架 `Armature`, 预处理 + 三步:
0. 预处理: 骨架沿 X 平移, 物体原点回到世界 x=0;
1. 位置: 右脚起点(距骨关节, VRC `Foot.R` / MMD `足首D.R`)的世界 Y / Z 对齐官方 `cf_j_leg03_R`;
2. 缩放: 以该脚点所在高度(Y / Z)为锚点在 x=0 轴上整体缩放, 让右上臂(`Upper_arm.R` / `腕.R`)的世界 Z
   对齐官方 `cf_j_arm00_R`;
3. 姿态: 左右大臂水平化(骨骼两端世界 Z 相同)。

第一步不动 X(两侧骨骼宽度本来就有差异)。预处理与前三步只改骨架物体的位置 / 缩放属性
(骨骼与旋转都不动, 网格随骨架一起移动与缩放), 第三步只改大臂的姿态数据。
"""

import re
from collections.abc import Sequence

import bpy
from bpy.types import Bone, Object
from mathutils import Matrix, Vector

from hitori_addon.error import ObjectError
from hitori_addon.obj import get_obj
from hitori_addon.template_link import ARMATURE_NAME

# 官方骨骼名固定不变: 右腿脚踝(距骨关节)与右上臂
OFFICIAL_FOOT_BONE_NAME = "cf_j_leg03_R"
OFFICIAL_UPPER_ARM_BONE_NAME = "cf_j_arm00_R"
# 脚部起点候选名(VRC -> MMD), 按优先级排列
FOOT_BONE_NAMES = ("Foot.R", "足首D.R", "足首.R")
# 上臂候选名(右 / 左; VRC -> MMD), 第一步用右大臂
UPPER_ARM_BONE_NAMES: tuple[tuple[str, ...], ...] = (
    ("Upper_arm.R", "腕.R"),
    ("Upper_arm.L", "腕.L"),
)
# 大臂与脚部高度差的下限, 防止贴合时算出无穷大的缩放
MIN_UPPER_ARM_SPAN = 1e-4
# 水平方向长度的下限, 大臂几乎竖直时无法水平化
MIN_HORIZONTAL_LENGTH = 1e-4
# 已经水平的容差, 在容差内不动姿态数据
LEVEL_TOLERANCE = 1e-6
_SEPARATORS = re.compile(r"[\s._\-]")


def strip_bone_name_separators(name: str) -> str:
    """去掉大小写与分隔符差异: `Foot.R` / `foot_R` / `Foot-R` 都归一成 footr"""
    return _SEPARATORS.sub("", name.lower())


def get_bone(obj: Object, name: str) -> Bone:
    bone = obj.data.bones.get(name)
    if bone is None:
        raise ObjectError(obj, f"骨架里没有骨骼 {name}")
    return bone


def find_bone(obj: Object, candidate_names: Sequence[str]) -> Bone | None:
    """按候选名的优先级找骨骼: 精确名 -> 归一化名 -> 带数字后缀的衍生命名(唯一时)"""
    bones = obj.data.bones
    for name in candidate_names:
        bone = bones.get(name)
        if bone is not None:
            return bone
        key = strip_bone_name_separators(name)
        matched = [bone for bone in bones if strip_bone_name_separators(bone.name) == key]
        if matched:
            return matched[0]

    for name in candidate_names:
        key = strip_bone_name_separators(name)
        matched = [
            bone
            for bone in bones
            if strip_bone_name_separators(bone.name).rstrip("0123456789") == key
        ]
        if len(matched) == 1:
            return matched[0]
    return None


def get_world_bone_head(obj: Object, bone: Bone) -> Vector:
    return obj.matrix_world @ bone.head_local


def get_world_pose_head(obj: Object, bone: Bone) -> Vector:
    """骨骼头部(含姿态)的世界坐标"""
    return obj.matrix_world @ obj.pose.bones[bone.name].head


def get_world_pose_tail(obj: Object, bone: Bone) -> Vector:
    """骨骼尾部(含姿态)的世界坐标"""
    return obj.matrix_world @ obj.pose.bones[bone.name].tail


def translate_world(obj: Object, delta: Vector):
    obj.matrix_world = Matrix.Translation(delta) @ obj.matrix_world
    bpy.context.view_layer.update()


def scale_world(obj: Object, factor: float, pivot: Vector):
    """以世界坐标 pivot 为锚点整体缩放"""
    matrix = (
        Matrix.Translation(pivot) @ Matrix.Scale(factor, 4) @ Matrix.Translation(-pivot)
    )
    obj.matrix_world = matrix @ obj.matrix_world
    bpy.context.view_layer.update()


def align_foot_position(obj: Object, foot_bone: Bone, target: Vector):
    """平移骨架, 让脚点落在官方脚点的 Y / Z 上(X 不动)"""
    foot = get_world_bone_head(obj, foot_bone)
    translate_world(obj, Vector((0.0, target.y - foot.y, target.z - foot.z)))


def center_world_x(obj: Object) -> float:
    """预处理: 沿 X 平移骨架, 让物体原点回到世界 x=0; 返回平移量"""
    x = obj.matrix_world.translation.x
    if abs(x) < LEVEL_TOLERANCE:
        return 0.0
    translate_world(obj, Vector((-x, 0.0, 0.0)))
    return -x


def align_upper_arm_height(
    obj: Object, foot_bone: Bone, upper_arm_bone: Bone, target_z: float
) -> float:
    """以脚点在 x=0 轴上(Y / Z)为锚点整体缩放, 让大臂高度对齐官方目标; 返回缩放系数"""
    foot = get_world_bone_head(obj, foot_bone)
    span = get_world_pose_head(obj, upper_arm_bone).z - foot.z
    if abs(span) < MIN_UPPER_ARM_SPAN:
        raise ObjectError(obj, "大臂与脚部高度几乎重合, 无法按大臂高度缩放")
    factor = (target_z - foot.z) / span
    # 锚点取 x=0 轴, 否则缩放会把 X 居中带偏
    scale_world(obj, factor, Vector((0.0, foot.y, foot.z)))
    return factor


def horizontalize_pose_bone(obj: Object, bone: Bone) -> float:
    """绕骨骼头部旋转姿态, 让骨骼两端的世界 Z 相同; 返回旋转前两端的高度差"""
    head = get_world_pose_head(obj, bone)
    tail = get_world_pose_tail(obj, bone)
    direction = tail - head
    if abs(direction.z) < LEVEL_TOLERANCE:
        return 0.0
    horizontal = Vector((direction.x, direction.y, 0.0))
    if horizontal.length < MIN_HORIZONTAL_LENGTH:
        raise ObjectError(obj, f"{bone.name} 几乎竖直, 无法水平化")

    rotation = direction.rotation_difference(horizontal).to_matrix().to_4x4()
    pivot = Matrix.Translation(head)
    matrix = pivot @ rotation @ pivot.inverted()
    pose_bone = obj.pose.bones[bone.name]
    pose_bone.matrix = obj.matrix_world.inverted() @ matrix @ obj.matrix_world @ pose_bone.matrix
    bpy.context.view_layer.update()
    return tail.z - head.z


def horizontalize_upper_arms(obj: Object) -> list[str]:
    """左右大臂水平化, 返回逐个骨骼的报告行"""
    lines = []
    for candidate_names in UPPER_ARM_BONE_NAMES:
        bone = find_bone(obj, candidate_names)
        if bone is None:
            lines.append(f"    大臂 {candidate_names}: 找不到骨骼")
            continue
        before = horizontalize_pose_bone(obj, bone)
        after = get_world_pose_tail(obj, bone).z - get_world_pose_head(obj, bone).z
        lines.append(f"    {bone.name}: 大臂 Z 差 {before:+.3f} -> {after:+.4f}")
    return lines


def align_armature(arm: Object, foot_target: Vector, upper_arm_target_z: float) -> str:
    """对齐一套骨架, 返回报告"""
    foot_bone = find_bone(arm, FOOT_BONE_NAMES)
    if foot_bone is None:
        raise ObjectError(arm, f"找不到脚部骨骼 {FOOT_BONE_NAMES}")
    upper_arm_bone = find_bone(arm, UPPER_ARM_BONE_NAMES[0])
    if upper_arm_bone is None:
        raise ObjectError(arm, f"找不到大臂骨骼 {UPPER_ARM_BONE_NAMES[0]}")

    foot_before = get_world_bone_head(arm, foot_bone)
    upper_arm_z_before = get_world_pose_head(arm, upper_arm_bone).z

    x_shift = center_world_x(arm)
    align_foot_position(arm, foot_bone, foot_target)
    factor = align_upper_arm_height(
        arm, foot_bone, upper_arm_bone, upper_arm_target_z
    )
    upper_arm_z_after = get_world_pose_head(arm, upper_arm_bone).z

    lines = [
        f"{arm.name} ({foot_bone.name} / {upper_arm_bone.name})",
        (
            f"    X 居中 {x_shift:+.3f}; "
            f"脚 Y {foot_target.y - foot_before.y:+.3f} "
            f"Z {foot_target.z - foot_before.z:+.3f}; "
            f"大臂 Z {upper_arm_z_before:.3f} -> {upper_arm_z_after:.3f} "
            f"(官方 {upper_arm_target_z:.3f}); 缩放 x{factor:.4f}"
        ),
    ]
    lines.extend(horizontalize_upper_arms(arm))
    return "\n".join(lines)


def align_armatures(
    arms: Sequence[Object], official: Object | None = None
) -> str:
    """对齐多套骨架, 返回逐行报告; 单套骨架出错只记一行, 不影响其他骨架"""
    official = official or get_obj(ARMATURE_NAME)
    if official is None or official.type != "ARMATURE":
        raise ObjectError(arms, f"场景里没有官方骨架 {ARMATURE_NAME}")

    foot_target = get_world_bone_head(
        official, get_bone(official, OFFICIAL_FOOT_BONE_NAME)
    )
    upper_arm_target_z = get_world_pose_head(
        official, get_bone(official, OFFICIAL_UPPER_ARM_BONE_NAME)
    ).z

    lines = []
    for arm in arms:
        if arm == official:
            lines.append(f"{arm.name}: 官方骨架本身, 跳过")
            continue
        try:
            lines.append(align_armature(arm, foot_target, upper_arm_target_z))
        except ObjectError as error:
            lines.append(str(error))
    return "\n".join(lines)
