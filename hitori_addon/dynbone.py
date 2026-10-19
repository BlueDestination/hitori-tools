"""动骨骨架保守清理

模型骨架里除了服装动骨, 还残留以下几类无用骨:
1. 整棵子树都没有权重(纯骨骼/控制骨);
2. 标准人形骨(身体 / 腿 / 手), 服装 mod 只需要动骨;
3. 首词带 `hip(s)` / `tail(s)` 的骨骼(臀部几乎不挂服装动骨, 尾巴通常是饰品), 连同子树一起删;
4. 脖子以上(头 / 头发 / 发饰)的骨骼: 不再属于服装, 整枝删除。

判据保守: 一根人形骨只有当它整棵子树里都没有"非人形骨"(动骨)时才删, 所以
任何动骨链的祖先都会被保留; 第 3 / 4 条是用户确认过的例外(臀部 / 尾巴 / 头颈)。
第 4 条本身只删"非人形骨"(手臂抬得比脖子高也不会误删), 全部规则算完后再回头清掉
只剩人形骨的空枝(如 `Neck -> Head`)。

前面为动骨链保住的人形骨祖先(`Spine` / `Chest` / `Upper_leg.L` 等)另有
`find_body_bone_names` 在清理末尾统一删掉: 动骨骨架只留动骨链与接骨(链根骨),
链根骨删完各自成为根骨。`edit_bones.remove` 会把子骨挂到被删骨骼的父级上,
所以动骨链本身不受影响。
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import bpy
import numpy as np
from bpy.types import Object

from hitori_addon import bonenames
from hitori_addon.arm import (
    delete_bones,
    get_bone_names,
    get_bones_with_weighted_subtree,
    get_children_recursive_bone_names,
)
from hitori_addon.bonegroup import get_group_bone_names
from hitori_addon.obj import get_objs
from hitori_addon.sb3u import get_cloth_type
from hitori_addon.template_link import ARMATURE_NAME
from hitori_addon.vg import get_meshes_weighted_vg_names, get_weighted_vg_names

# 已确认命名与 VRC_MMD_BONES_SET 不重合、但确定属于人形骨的词 (面部骨见 docs/automation.md)
HUMANOID_KEYWORDS = (
    "twist",
    "breast",
    "hoppe",
    "eye",
    "bip001",
    # 面部骨: KK 的 cf_J_Mouth* / cf_J_Tang* 靠 cf_ 前缀覆盖, 这里补 MMD 的罗马字写法
    "jaw",
    "lip",
    "tongue",
    "tooth",
    "teeth",
    "cheek",
    "brow",
    "yachi",
    "zuiba",
)

# 一般不挂服装动骨的部位: 臀部(几乎见不到臀部服装动骨)与尾巴(尾巴通常是饰品)
_NO_CLOTH_TOKEN_PATTERN = re.compile(r"^(hips?|tails?)(l|r|left|right|\d+)?$")
# 标准人形骨盆骨, 不能因为名字带 hips 就删掉整棵身体
EXACT_HUMANOID_NAMES: frozenset[str] = frozenset({"hip", "hips"})

# 颈部骨骼命名; 用来确定"脖子以上"的高度
NECK_TOKEN_KEYWORDS = ("neck", "首")
# 判断两套骨架同源(清理前后的副本)的名称重合率下限
SAME_RIG_OVERLAP = 0.9


def is_humanoid_bone_name(name: str) -> bool:
    """是否标准人形骨(与动骨相对)"""
    if name.lower().startswith("cf_"):
        return True
    if bonenames.is_humanoid_bone_name(name):
        return True
    return any(keyword in bonenames.normalize_bone_name(name) for keyword in HUMANOID_KEYWORDS)


def get_bone_name_tokens(name: str) -> list[str]:
    """按大小写与 . - _ 空格 / 数字切词: Hips_L.001 -> ['hips', 'l'], TailRoot -> ['tail', 'root']"""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return [token for token in re.split(r"[^a-zA-Z]+", spaced.lower()) if token]


def is_no_cloth_bone_name(name: str) -> bool:
    """首词是 hip(s)/tail(s) 时认为不会挂服装动骨; 只认首词, 避免误删 shirt_tail 这类衣摆"""
    lower = name.lower()
    if lower.startswith("cf_") or lower in EXACT_HUMANOID_NAMES:
        return False
    tokens = get_bone_name_tokens(name)
    return bool(tokens and _NO_CLOTH_TOKEN_PATTERN.match(tokens[0]))


def find_neck_bone(obj: Object):
    """骨架里的颈部骨骼(Neck / 首 / cf_j_neck), 没有返回 None"""
    for bone in obj.data.bones:
        if "neck" in get_bone_name_tokens(bone.name) or "首" in bone.name:
            return bone
    return None


def get_world_bone_z(obj: Object, bone, tail: bool = False) -> float:
    """骨骼头(或尾)在世界坐标下的 Z"""
    return (obj.matrix_world @ (bone.tail_local if tail else bone.head_local)).z


def get_same_rig_armature(arm: Object) -> Object | None:
    """同源原始骨架: 名称基本包含当前骨架(清理前后的副本), 且带颈部骨骼"""
    own_names = {bone.name for bone in arm.data.bones}
    best, best_shared = None, 0
    for obj in get_objs("ARMATURE"):
        if obj is arm or obj.type != "ARMATURE" or find_neck_bone(obj) is None:
            continue
        shared = len(own_names & {bone.name for bone in obj.data.bones})
        if shared / max(len(own_names), 1) >= SAME_RIG_OVERLAP and shared > best_shared:
            best, best_shared = obj, shared
    return best


def find_neck_z(arm: Object) -> float | None:
    """颈部高度(世界 Z): 自身 -> 同源原始骨架 -> 对齐后的官方骨架; 都没有返回 None"""
    neck_bone = find_neck_bone(arm)
    if neck_bone is not None:
        return get_world_bone_z(arm, neck_bone)
    source = get_same_rig_armature(arm)
    if source is not None:
        return get_world_bone_z(source, find_neck_bone(source))
    official = bpy.data.objects.get(ARMATURE_NAME)
    if official is not None and official.type == "ARMATURE":
        bone = official.data.bones.get("cf_j_neck")
        if bone is not None:
            return get_world_bone_z(official, bone)
    return None


def get_weighted_bone_names(meshes: Sequence[Object] | None = None) -> set[str]:
    """带非零权重的骨骼名合集"""
    return get_meshes_weighted_vg_names(get_objs("MESH") if meshes is None else meshes)


# 接骨脚本给根骨打的骨骼组名, 注册时靠它找根骨
ROOT_BONE_GROUP_NAME = "db_root"


@dataclass
class ClothRootBoneInfo:
    """一根接骨根骨的自动分类结果"""

    cloth_types: set[str] = field(default_factory=set)
    # 子树里有非零权重的网格名 (含饰品 / 非法名网格), 用来说明为什么没分类
    mesh_names: set[str] = field(default_factory=set)


def find_cloth_root_bone_types(
    arm: Object, root_bone_names: Sequence[str] | None = None
) -> dict[str, ClothRootBoneInfo]:
    """每根根骨 -> 它的自动分类结果

    root_bone_names 为空时取接骨脚本标的 `db_root` 组骨骼。类型不看骨名, 全部由
    "子树 ∩ 有权重的服装网格 -> 网格名" 反推 (`sb3u.get_cloth_type`):
    只挂在饰品 / 未定名网格(如 `_pants`)上的链会得到空类型, 由调用方决定跳过还是报错;
    `mesh_names` 记下命中过的网格名, 跳过的链靠它解释原因。
    """
    if root_bone_names is None:
        root_bone_names = get_group_bone_names(arm, ROOT_BONE_GROUP_NAME)

    weighted_names_by_mesh_name: dict[str, set[str]] = {}
    for obj in get_objs("MESH"):
        if obj.vertex_groups:
            weighted_names_by_mesh_name[obj.name] = get_weighted_vg_names(obj)

    root_bone_infos: dict[str, ClothRootBoneInfo] = {}
    for root_bone_name in root_bone_names:
        subtree_names = {root_bone_name} | set(
            get_children_recursive_bone_names(arm, root_bone_name)
        )
        mesh_names = {
            mesh_name
            for mesh_name, weighted_names in weighted_names_by_mesh_name.items()
            if subtree_names & weighted_names
        }
        root_bone_infos[root_bone_name] = ClothRootBoneInfo(
            cloth_types={
                cloth_type
                for mesh_name in mesh_names
                if (cloth_type := get_cloth_type(mesh_name)) is not None
            },
            mesh_names=mesh_names,
        )
    return root_bone_infos


def is_dynbone_holder_name(name: str) -> bool:
    """名字以 `root` 结尾的是锤点 (`Back_root` / `Side_root`): 不是动骨链起点

    这类骨的权重是跟着头皮 / 身体不动的底座, 真正要摆的是它的子骨。前缀写法 (`Root_Skirt`)
    是动骨链的根骨, 不算锤点。

    只能用于饰品: 服装的链根骨也常以 `Root` 结尾 (`Panty_Ribbon_Root`), 但服装根骨是靠接骨固定住的
    锤点 (`bi_mono`), 它本来就该注册进去当动骨链的父级, 不能拿这个函数判断。
    """
    return get_bone_name_tokens(name)[-1:] == ["root"]


def find_acc_dynbone_names(parents: Mapping[str, str | None]) -> list[str]:
    """饰品动骨 (`db_mono` 的 `m_Root`): 从根骨往下, 第一个非人形骨(非身体骨)就是链起点

    官方饰品 mod 的 `m_Root` 写的是链起点本身 (被物理驱动的第一根骨), 它的父骨
    (身体挂点 / mod 自己的 holder) 不注册。导出时的骨架只剩有权重的骨, 所以跳过人形骨
    (`Head` / `Chest` 这类身体骨) 与骨架根骨后踩到的第一根就是链起点; 命中后不再往下,
    免得把一条链拆成多份注册。只有身体骨的饰品没有动骨, 返回空列表。

    名字以 `root` 结尾的锤点 (`Back_root` / `Side_root` / `Ahoge_root`) 也要跳过: 它们的权重
    是跟着头皮不动的底座, 注册了会把后脑勺 / 侧发的头皮整块抽起来, 要注册的是它们下面的子骨。

    `parents` 是骨名 -> 父骨名 (根骨为 `None`) 的骨架层级; 只看名字不看坐标, 所以不需要骨架物体。
    """
    children: dict[str, list[str]] = {name: [] for name in parents}
    for name in sorted(parents):
        parent = parents[name]
        if parent is not None:
            children[parent].append(name)
    names: list[str] = []

    def visit(name: str) -> None:
        if (
            parents[name] is not None
            and not is_humanoid_bone_name(name)
            and not is_dynbone_holder_name(name)
        ):
            names.append(name)
            return
        for child in children[name]:
            visit(child)

    for name in sorted(parents):
        if parents[name] is None:
            visit(name)
    return sorted(names)


def find_acc_dynbone_bone_names(arm: Object) -> list[str]:
    """`find_acc_dynbone_names` 的骨架版 (规则见该函数的文档)"""
    parents = {
        bone.name: (bone.parent.name if bone.parent is not None else None)
        for bone in arm.data.bones
    }
    return find_acc_dynbone_names(parents)


def find_humanoid_useless_bone_names(arm: Object) -> list[str]:
    """子树里没有任何非人形骨(动骨)的人形骨"""
    dynamic_descendants: dict[str, bool] = {}

    def visit(bone) -> bool:
        # 返回该骨骼子树里是否含非人形骨
        has_dynamic = not is_humanoid_bone_name(bone.name)
        for child in bone.children:
            has_dynamic = visit(child) or has_dynamic
        dynamic_descendants[bone.name] = has_dynamic
        return has_dynamic

    for bone in arm.data.bones:
        if bone.parent is None:
            visit(bone)

    return sorted(
        name
        for name, has_dynamic in dynamic_descendants.items()
        if is_humanoid_bone_name(name) and not has_dynamic
    )


def find_no_cloth_bone_names(arm: Object) -> list[str]:
    """臀部/尾巴词缀的骨骼及其整棵子树"""
    names: set[str] = set()
    for bone in arm.data.bones:
        if is_no_cloth_bone_name(bone.name):
            names.add(bone.name)
            names.update(child.name for child in bone.children_recursive)
    return sorted(names)


def find_above_neck_bone_names(arm: Object, neck_z: float) -> list[str]:
    """骨的头或尾高于颈部、且不是标准人形骨的骨骼及其整棵子树"""
    names: set[str] = set()
    for bone in arm.data.bones:
        if is_humanoid_bone_name(bone.name):
            continue
        if (
            get_world_bone_z(arm, bone) > neck_z
            or get_world_bone_z(arm, bone, tail=True) > neck_z
        ):
            names.add(bone.name)
            names.update(child.name for child in bone.children_recursive)
    return sorted(names)


def find_body_bone_names(arm: Object) -> list[str]:
    """剩下的标准人形骨(身体骨), 动骨骨架不需要它们"""
    return sorted(name for name in get_bone_names(arm) if is_humanoid_bone_name(name))


def add_dangling_humanoid_names(arm: Object, names: set[str]) -> None:
    """规则 1-4 删完后只剩人形骨的空枝(如 Neck -> Head)一起删, 原地修改 names"""
    changed = True
    while changed:
        changed = False
        for bone in arm.data.bones:
            if bone.name in names or not is_humanoid_bone_name(bone.name):
                continue
            if all(child.name in names for child in bone.children):
                names.add(bone.name)
                changed = True


def find_useless_bone_names(
    arm: Object,
    weighted_names: set[str] | None = None,
    include_humanoid: bool = True,
) -> list[str]:
    if weighted_names is None:
        weighted_names = get_weighted_bone_names()
    useful = get_bones_with_weighted_subtree(arm, weighted_names)
    names = {name for name in get_bone_names(arm) if name not in useful}
    if include_humanoid:
        names |= set(find_humanoid_useless_bone_names(arm))
    # 臀部/尾巴即使带权重也删(服装几乎不会挂到这两处)
    names |= set(find_no_cloth_bone_names(arm))
    # 脖子以上不是服装: 头发 / 发饰动骨整枝删
    neck_z = find_neck_z(arm)
    if neck_z is not None:
        names |= set(find_above_neck_bone_names(arm, neck_z))
    # 头 / 发删干净后, Neck -> Head 会剩成空枝, 一起删
    add_dangling_humanoid_names(arm, names)
    return sorted(names)


def prune_useless_bones(
    arm: Object,
    meshes: Sequence[Object] | None = None,
    include_humanoid: bool = True,
) -> list[str]:
    """删掉无用骨骼, 返回被删骨骼名列表"""
    weighted_names = get_weighted_bone_names(meshes)
    useless = find_useless_bone_names(arm, weighted_names, include_humanoid)
    if useless:
        delete_bones(arm, useless)
    return useless


# 接骨时给根骨挑 KK 关节骨; 这里也是距离数组的顺序
KK_JOINT_BONE_NAMES: tuple[str, ...] = (
    "cf_j_spine03",
    "cf_j_spine02",
    "cf_j_waist01",
    "cf_j_waist02",
    "cf_j_arm00_L",
    "cf_j_forearm01_L",
    "cf_j_arm00_R",
    "cf_j_forearm01_R",
    "cf_j_thigh00_L",
    "cf_j_leg01_L",
    "cf_j_thigh00_R",
    "cf_j_leg01_R",
)

# 长骨区域: 本关节 -> 同肢体更远端的关节。整段都算近端关节的地盘 ("就上"):
# 大腿中段 / 大臂中段的根骨要挂到髋 / 肩, 只比关节头距离会二选一输给膝 / 肘。
# 骨架里的骨骼 tail 方向不可靠(cf_j_thigh00_L 的 tail 反而朝上), 所以只用关节头连线。
KK_JOINT_LONG_BONE_NAMES: Mapping[str, str] = {
    "cf_j_thigh00_L": "cf_j_leg01_L",
    "cf_j_leg01_L": "cf_j_leg03_L",
    "cf_j_thigh00_R": "cf_j_leg01_R",
    "cf_j_leg01_R": "cf_j_leg03_R",
    "cf_j_arm00_L": "cf_j_forearm01_L",
    "cf_j_forearm01_L": "cf_j_hand_L",
    "cf_j_arm00_R": "cf_j_forearm01_R",
    "cf_j_forearm01_R": "cf_j_hand_R",
}


def get_point_to_segment_distance(point, start, end) -> float:
    """点到线段 (start -> end) 的距离"""
    direction = end - start
    length_squared = float(direction @ direction)
    if length_squared == 0:
        return float(np.linalg.norm(point - start))
    ratio = float(np.clip((point - start) @ direction / length_squared, 0.0, 1.0))
    return float(np.linalg.norm(point - (start + ratio * direction)))


def get_kk_joint_bone_distances(
    root_bone_position, kk_joint_bone_position_map: Mapping[str, object]
) -> np.ndarray:
    """每个候选关节到根骨的区域距离

    长骨关节算到 [关节头 -> 远端关节头] 线段的距离 (所以整段长骨都归它),
    其余关节算到关节头的距离; 远端关节缺失时退回关节头距离。
    """
    distances = np.empty(len(KK_JOINT_BONE_NAMES))
    for index, kk_joint_bone_name in enumerate(KK_JOINT_BONE_NAMES):
        start = kk_joint_bone_position_map[kk_joint_bone_name]
        far_name = KK_JOINT_LONG_BONE_NAMES.get(kk_joint_bone_name)
        far = kk_joint_bone_position_map.get(far_name) if far_name else None
        if far is None:
            distances[index] = np.linalg.norm(root_bone_position - start)
        else:
            distances[index] = get_point_to_segment_distance(
                root_bone_position, start, far
            )
    return distances


def find_kk_joint_bone_names(
    root_bone_position_map: Mapping[str, object],
    kk_joint_bone_position_map: Mapping[str, object],
) -> dict[str, str]:
    """给每根接骨根骨挑 KK 关节骨: 就近 + 长骨就上, 平手时取表中靠前的关节"""
    return {
        root_bone_name: KK_JOINT_BONE_NAMES[
            int(np.argmin(get_kk_joint_bone_distances(position, kk_joint_bone_position_map)))
        ]
        for root_bone_name, position in root_bone_position_map.items()
    }
