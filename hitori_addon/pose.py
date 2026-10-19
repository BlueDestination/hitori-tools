"""姿态编辑: 选中骨骼的镜像 / 水平化"""

import math

import bpy
from bpy.types import Bone, Object, PoseBone
from mathutils import Matrix, Quaternion, Vector

from hitori_addon.error import ObjectError

# 常见左右骨骼标记, 顺序即优先级 (先试通用后缀, 再试英文单词, 最后中文)
MIRROR_MARKERS: tuple[tuple[str, str], ...] = (
    (".L", ".R"),
    (".l", ".r"),
    ("_L", "_R"),
    ("_l", "_r"),
    ("-L", "-R"),
    (" L", " R"),
    ("L_", "R_"),
    ("Left", "Right"),
    ("left", "right"),
    ("左", "右"),
)
# 以骨架局部 X=0 平面镜像
MIRROR_MATRIX = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
MIRROR_MATRIX_3 = Matrix.Diagonal((-1.0, 1.0, 1.0))


def get_roll_fix(rest_src: Matrix, rest_dst: Matrix) -> Matrix:
    """左右静止帧绕骨骼轴的扭转差, 抵消骨架左右 roll 约定不一致 (mmd 左右差 180 度)"""
    diff = (MIRROR_MATRIX_3 @ rest_src.to_3x3() @ MIRROR_MATRIX_3).inverted() @ rest_dst.to_3x3()
    quat = diff.to_quaternion()
    twist = Quaternion((quat.w, 0.0, quat.y, 0.0))
    if twist.magnitude < 1e-6:
        return Matrix.Identity(4)
    twist.normalize()
    if twist.w < 0.0:
        twist.negate()
    return twist.to_matrix().to_4x4()


def find_mirror_bone(arm: Object, name: str) -> Bone | None:
    """按命名约定找镜像骨骼, 找不到返回 None

    同一个标记可能在名字里出现多次 (`Bon_Lolip01_L` 的 `Bon_L` 也含 `_L`), 只换第一处会换错位置,
    所以逐个位置换一遍, 取第一个真存在的骨骼。
    """
    bones = arm.data.bones
    for marker, counterpart in MIRROR_MARKERS:
        for source, target in ((marker, counterpart), (counterpart, marker)):
            start = 0
            while (index := name.find(source, start)) >= 0:
                start = index + 1
                swapped = name[:index] + target + name[index + len(source) :]
                bone = bones.get(swapped)
                if bone is not None:
                    return bone
    return None


def get_bone_depth(bone: Bone) -> int:
    depth = 0
    while bone.parent:
        depth += 1
        bone = bone.parent
    return depth


def require_pose_position(arm: Object) -> None:
    """骨架在静止姿态显示 (REST) 时看不到姿态改动"""
    if arm.data.pose_position == "REST":
        raise ObjectError(
            arm,
            "骨架在静止姿态显示 (REST), 看不到姿态变化, "
            "请先把骨架数据属性 > 姿态位置 切回 姿态",
        )


def mirror_selected_pose() -> tuple[int, list[str]]:
    """把选中骨架里选中的骨骼镜像到命名对应的镜像骨骼

    返回 (镜像骨骼数, 找不到镜像骨骼的骨骼名)。支持多骨架多骨骼, 父子可以同时选中:
    先把所有源矩阵算出来, 再按目标骨骼深度从浅到深写入, 写入时才不会被已改动的父级带偏。
    """
    arms = [obj for obj in bpy.context.selected_objects if obj.type == "ARMATURE"]
    tasks: list[tuple[Object, Bone, Matrix]] = []
    missing: list[str] = []
    conflicts: list[str] = []
    sources: dict[tuple[str, str], str] = {}

    for arm in arms:
        selected = get_selected_pose_bones(arm)
        if not selected:
            continue
        require_pose_position(arm)
        for pose_bone in selected:
            mirror_bone = find_mirror_bone(arm, pose_bone.name)
            if mirror_bone is None:
                missing.append(pose_bone.name)
                continue
            key = (arm.name, mirror_bone.name)
            if key in sources:
                conflicts.append(
                    f"{sources[key]} 和 {pose_bone.name} 都镜像到 {mirror_bone.name}"
                )
                continue
            sources[key] = pose_bone.name
            matrix = MIRROR_MATRIX @ pose_bone.matrix @ MIRROR_MATRIX
            matrix = matrix @ get_roll_fix(pose_bone.bone.matrix_local, mirror_bone.matrix_local)
            tasks.append((arm, mirror_bone, matrix))

    if not any(get_selected_pose_bones(arm) for arm in arms):
        raise ObjectError(arms, "请先选中要镜像的骨骼")
    if conflicts:
        raise ObjectError(arms, "多个骨骼镜像到同一根骨骼: " + "; ".join(conflicts))

    # 父级先写: 子级的姿态矩阵依赖父级当前姿态
    tasks.sort(key=lambda task: get_bone_depth(task[1]))
    for arm, mirror_bone, matrix in tasks:
        arm.pose.bones[mirror_bone.name].matrix = matrix
        bpy.context.view_layer.update()
    return len(tasks), missing


def get_selected_pose_bones(arm: Object) -> list[PoseBone]:
    return [pose_bone for pose_bone in arm.pose.bones if pose_bone.bone.select]


def find_parent_child_pair(selected: list[PoseBone]) -> tuple[PoseBone, PoseBone] | None:
    """选中的骨骼里存在父子关系时返回 (父, 子)"""
    names = {pose_bone.name for pose_bone in selected}
    for pose_bone in selected:
        parent = pose_bone.parent
        while parent:
            if parent.name in names:
                return parent, pose_bone
            parent = parent.parent
    return None


def get_world_level_matrix(arm: Object, pose_bone: PoseBone) -> Matrix | None:
    """绕世界 Y 轴把骨骼转到水平 (前视图的 X 轴) 的世界矩阵; 方向正对前视图时返回 None"""
    matrix_world = arm.matrix_world
    head = matrix_world @ pose_bone.head
    direction = matrix_world @ pose_bone.tail - head
    direction_xz = Vector((direction.x, direction.z))
    if direction_xz.length < 1e-6:
        # 骨骼沿世界 Y (正对 / 背对前视图), 绕 Y 轴转动不会改变方向
        return None
    # 绕世界 Y 转 angle 等价于把 (x, z) 的极角减去 angle, 所以直接取极角
    angle = math.atan2(direction_xz.y, direction_xz.x)
    # 收到 [-pi/2, pi/2]: 朝 -X 的骨骼转到 +X 侧同样算水平, 少转 180 度
    if angle > math.pi / 2:
        angle -= math.pi
    elif angle < -math.pi / 2:
        angle += math.pi
    rotation = Matrix.Rotation(angle, 4, "Y")
    # 绕骨骼头部转, 头部位置不变, 只改方向
    return Matrix.Translation(head) @ rotation @ Matrix.Translation(-head)


def level_selected_pose_bones() -> int:
    """把选中骨架里选中的骨骼转到水平, 返回转动的骨骼数

    支持多骨架多骨骼, 但同一棵骨骼树上不能同时选父子: 父级转动会带偏子级。
    """
    arms = [obj for obj in bpy.context.selected_objects if obj.type == "ARMATURE"]
    tasks: list[tuple[Object, PoseBone, Matrix]] = []

    for arm in arms:
        selected = get_selected_pose_bones(arm)
        if not selected:
            continue
        require_pose_position(arm)
        pair = find_parent_child_pair(selected)
        if pair:
            parent, child = pair
            raise ObjectError(
                arm,
                f"{child.name} 是 {parent.name} 的子级, "
                "同一棵树上的骨骼不能同时水平化 (父级转动会带偏子级), 请分两次执行",
            )
        for pose_bone in selected:
            matrix = get_world_level_matrix(arm, pose_bone)
            if matrix is not None:
                tasks.append((arm, pose_bone, matrix))

    if not any(get_selected_pose_bones(arm) for arm in arms):
        raise ObjectError(arms, "请先选中要水平化的骨骼")

    for arm, pose_bone, matrix in tasks:
        matrix_world = arm.matrix_world
        pose_bone.matrix = matrix_world.inverted() @ matrix @ matrix_world @ pose_bone.matrix
        bpy.context.view_layer.update()
    return len(tasks)
