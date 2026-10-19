from collections.abc import Iterable, Mapping, Sequence

import bpy
import numpy as np
from bpy.types import Object

from hitori_addon.bonenames import is_humanoid_bone_name
from hitori_addon.template_link import SKIP_TRANSFER_GROUP_NAME


def get_vg_names(obj: Object) -> list[str]:
    return [vg.name for vg in obj.vertex_groups]


def get_weight_matrix(obj: Object) -> np.ndarray:
    weight_matrix = np.zeros((len(obj.data.vertices), len(obj.vertex_groups)))
    for vertex_index, vertex in enumerate(obj.data.vertices):
        row = weight_matrix[vertex_index]
        for g in vertex.groups:
            row[g.group] = g.weight
    return weight_matrix


def get_weighted_vg_indices(obj: Object) -> np.ndarray:
    """有非零权重的顶点组索引

    只清点顶点自己记录的组, 不建 V x G 权重矩阵(省内存, 实测快约 25%), 全找到就提前结束。
    """
    obj_vgs = obj.vertex_groups
    vg_count = len(obj_vgs)
    weighted_bools = np.zeros(vg_count, dtype=bool)
    weighted_count = 0
    for vertex in obj.data.vertices:
        for group in vertex.groups:
            if group.weight and not weighted_bools[group.group]:
                weighted_bools[group.group] = True
                weighted_count += 1
        if weighted_count == vg_count:
            break
    return np.nonzero(weighted_bools)[0]


def get_weighted_vg_names(obj: Object) -> set[str]:
    """该网格里有非零权重的顶点组名"""
    obj_vgs = obj.vertex_groups
    return {obj_vgs[index].name for index in get_weighted_vg_indices(obj)}


def get_meshes_weighted_vg_names(objs: Iterable[Object]) -> set[str]:
    """多个网格里有非零权重的顶点组名合集"""
    names: set[str] = set()
    for obj in objs:
        names |= get_weighted_vg_names(obj)
    return names


def delete_empty_vgs(obj: Object, keep_names: Sequence[str] = ()) -> list[str]:
    """删除没有非零权重的顶点组, keep_names 里的组即使是空的也保留; 返回被删的组名"""
    weighted_indices = set(get_weighted_vg_indices(obj).tolist())

    obj_vgs = obj.vertex_groups
    keep_indices = {obj_vgs[name].index for name in keep_names if obj_vgs.get(name)}
    empty_vg_indices_desc = sorted(
        set(range(len(obj_vgs))) - weighted_indices - keep_indices
    )[::-1]
    deleted_names = [obj_vgs[index].name for index in reversed(empty_vg_indices_desc)]
    for empty_vg_index in empty_vg_indices_desc:
        obj_vgs.remove(obj_vgs[empty_vg_index])
    return deleted_names


def merge_vgs(
    obj: Object,
    merge_vg_names: list[str] | tuple[str, ...] | set[str],
    new_vg_name: str,
    inverse: bool = False,
    create_if_empty: bool = False,
    overwrite: bool = True,
) -> None:
    obj_vgs = obj.vertex_groups
    obj_vg_names = get_vg_names(obj)

    weight_matrix = get_weight_matrix(obj)
    valid_vg_indices = [
        obj_vgs[vg_name].index for vg_name in merge_vg_names if vg_name in obj_vg_names
    ]
    valid_vg_weight_matrix = weight_matrix[:, valid_vg_indices]
    new_vg_weights = np.sum(valid_vg_weight_matrix, axis=1)

    if inverse:
        new_vg_weights = 1 - new_vg_weights

    # 使用tolist将np的int32或64转化为python的int后才能当做顶点索引，否则会报错，
    valid_vertex_indices = np.nonzero(new_vg_weights)[0].tolist()
    if not valid_vertex_indices and not create_if_empty:
        return

    existing_vg = obj_vgs.get(new_vg_name)
    if existing_vg is not None:
        if overwrite:
            obj_vgs.remove(existing_vg)
        else:
            return

    # 添加有效顶点权重
    new_vg = obj_vgs.new(name=new_vg_name)
    for valid_vertex_index in valid_vertex_indices:
        new_vg.add([valid_vertex_index], new_vg_weights[valid_vertex_index], "REPLACE")


def add_mirror_bones_map(
    kk_bone_to_vrc_bones_map_left: Mapping[str, Sequence[str]],
) -> dict[str, Sequence[str]]:
    kk_bone_to_vrc_bones_map = kk_bone_to_vrc_bones_map_left.copy()

    # 边遍历边插入镜像键, 先取快照
    for kk_bone, vrc_bones in list(kk_bone_to_vrc_bones_map.items()):
        if not kk_bone.endswith("_L"):
            continue

        kk_bone_L = kk_bone
        vrc_bones_L = vrc_bones
        kk_bone_R = kk_bone_L[:-2] + "_R"
        vrc_bones_R = []

        for vrc_bone_L in vrc_bones_L:
            for suffix in ["_L", ".L", "-L"]:
                if suffix in vrc_bone_L:
                    vrc_bone_R = vrc_bone_L.replace(suffix, suffix[0] + "R")
                    break
            else:
                vrc_bone_R = vrc_bone_L
            vrc_bones_R.append(vrc_bone_R)
        kk_bone_to_vrc_bones_map[kk_bone_R] = vrc_bones_R

    return kk_bone_to_vrc_bones_map


def set_skip_transfer_group(obj: Object, vertex_indices: Iterable[int]) -> int:
    """用这些顶点重建 skip_transfer_group, 返回顶点数

    没有顶点也照样建一个空组 (空组等价于缺失, 都是整片传), 方便在权重模式下对比有没有标过。
    """
    obj_vgs = obj.vertex_groups
    existing_vg = obj_vgs.get(SKIP_TRANSFER_GROUP_NAME)
    if existing_vg is not None:
        obj_vgs.remove(existing_vg)

    indices = list(vertex_indices)
    new_vg = obj_vgs.new(name=SKIP_TRANSFER_GROUP_NAME)
    if indices:
        new_vg.add(indices, 1.0, "REPLACE")
    return len(indices)


def build_skip_transfer_group(obj: Object) -> int:
    """按骨骼名标记要跳过传权重的顶点, 返回顶点数

    人形骨名单只算 VRC/MMD (与 bodytight 传权重的目标一致), 名字先按原文再按归一化比对
    (`Upper_leg.L` 与 `Upper_Leg.L` 算同一个, `左腕` 与 `腕.L` 也算同一个), 否则大小写 / 分隔符 /
    左右写法不同的骨名会漏成"非人形骨"。
    KK 命名的网格算不出人形骨, 于是全部顶点都跳过 (整片不传), 与合并权重到 KK 顶点组后的旧行为一致。
    """
    vg_names = get_vg_names(obj)
    humanoid_indices = [
        index for index, name in enumerate(vg_names) if is_humanoid_bone_name(name)
    ]
    vertex_count = len(obj.data.vertices)
    if humanoid_indices:
        has_humanoid_weight = get_weight_matrix(obj)[:, humanoid_indices].any(axis=1)
        skip_indices = np.nonzero(~has_humanoid_weight)[0].tolist()
    else:
        skip_indices = list(range(vertex_count))
    return set_skip_transfer_group(obj, skip_indices)


# 只归一化与骨架骨骼同名的组: 选择标记组 (bot_part / top_part / top_bot_edge / skip_transfer_group)、
# mmd_tools 的 mmd_edge_scale (边缩放系数) / mmd_vertex_order (顶点顺序)、
# 各插件自建的标记组 (body_vg / _clipping / shoe ...) 的权重都不是骨骼权重, 一律原样保留
# 权重和与 1 的偏差超过这个值才算没归一化
WEIGHT_SUM_TOLERANCE: float = 0.001


def get_weight_sum_stats(obj: Object) -> tuple[int, float, int]:
    """可修复的权重和偏离 1 的顶点数, 最大偏差, 没有任何骨骼权重的顶点数

    非骨骼组不算 (它们的权重不是骨骼权重, 混进来会让统计失去意义);
    权重和为 0 的顶点无从缩放, 单独计数。
    """
    ignored_indices = _get_ignored_vg_indices(obj)
    deviating = 0
    max_deviation = 0.0
    unweighted = 0
    for vertex in obj.data.vertices:
        weight_sum = sum(e.weight for e in vertex.groups if e.group not in ignored_indices)
        if weight_sum <= 0:
            unweighted += 1
            continue
        deviation = abs(weight_sum - 1)
        if deviation > WEIGHT_SUM_TOLERANCE:
            deviating += 1
            max_deviation = max(max_deviation, deviation)
    return deviating, max_deviation, unweighted


def normalize_weights(obj: Object) -> tuple[int, float]:
    """把每个顶点的骨骼权重缩放回和为 1, 返回归一化的顶点数, 最大修正偏差

    非骨骼组 / 锁定的组原样保留; 权重和为 0 的顶点无从缩放, 直接跳过。
    """
    obj_vgs = obj.vertex_groups
    ignored_indices = _get_ignored_vg_indices(obj)
    fixed = 0
    max_deviation = 0.0
    for vertex in obj.data.vertices:
        entries = [
            (e.group, e.weight)
            for e in vertex.groups
            if e.group not in ignored_indices and e.weight
        ]
        weight_sum = sum(weight for _, weight in entries)
        if weight_sum <= 0:
            continue
        deviation = abs(weight_sum - 1)
        if deviation <= WEIGHT_SUM_TOLERANCE:
            continue
        scale = 1 / weight_sum
        for group_index, weight in entries:
            obj_vgs[group_index].add([vertex.index], weight * scale, "REPLACE")
        fixed += 1
        max_deviation = max(max_deviation, deviation)
    return fixed, max_deviation


def get_armature_bone_names() -> set[str]:
    """场景里所有骨架的骨骼名"""
    return {
        bone.name
        for obj in bpy.data.objects
        if obj.type == "ARMATURE"
        for bone in obj.data.bones
    }


def get_non_bone_vg_names(obj: Object, bone_names: set[str] | None = None) -> list[str]:
    """网格上不是骨骼的组名 (标记组 / mmd_tools / 插件自建), 归一化时会原样保留"""
    if bone_names is None:
        bone_names = get_armature_bone_names()
    return [vg.name for vg in obj.vertex_groups if vg.name not in bone_names]


def _get_ignored_vg_indices(obj: Object) -> set[int]:
    """不参与归一化 / 体检的组: 不是骨骼的组 + 锁定的骨骼组"""
    bone_names = get_armature_bone_names()
    return {
        vg.index
        for vg in obj.vertex_groups
        if vg.lock_weight or vg.name not in bone_names
    }
