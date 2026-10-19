"""骨架骨骼分组染色

Blender 3.6 没有骨骼集合(4.0 才有), 能用的就是骨骼组(`pose.bone_groups`) + 组颜色(`color_set`),
配合 `Armature.show_group_colors` 在视图里按组显示颜色。这里用一个组装下整个骨架的骨骼。
"""

from collections.abc import Iterable, Sequence

from bpy.types import BoneGroup, Object

GREEN = (0.16, 0.72, 0.16)
RED = (0.85, 0.16, 0.16)
ORANGE = (0.95, 0.45, 0.05)

RGB = Sequence[float]


def _lighten(rgb: RGB, factor: float) -> tuple[float, float, float]:
    return tuple(min(1.0, c * factor + 0.15) for c in rgb[:3])


def color_by_bone_group(
    obj: Object,
    group_name: str,
    rgb: RGB,
    bone_names: Iterable[str] | None = None,
) -> BoneGroup:
    """把 obj(骨架)的骨骼归入 group_name 骨骼组并染成 rgb, bone_names 为空时处理全部骨骼"""
    groups = obj.pose.bone_groups
    group = groups.get(group_name)
    if group is None:
        group = groups.new(name=group_name)
    group.color_set = "CUSTOM"
    group.colors.normal = rgb[:3]
    group.colors.select = _lighten(rgb, 1.35)
    group.colors.active = _lighten(rgb, 1.7)

    if bone_names is None:
        pose_bones = obj.pose.bones
    else:
        pose_bones = [
            obj.pose.bones[name] for name in bone_names if name in obj.pose.bones
        ]
    for pose_bone in pose_bones:
        pose_bone.bone_group = group

    obj.data.show_group_colors = True
    return group


def get_group_bone_names(obj: Object, group_name: str) -> list[str]:
    """obj 骨架里归在 group_name 骨骼组的骨骼名 (组不存在返回空)"""
    group = obj.pose.bone_groups.get(group_name)
    if group is None:
        return []
    return [
        pose_bone.name for pose_bone in obj.pose.bones if pose_bone.bone_group == group
    ]


def get_bone_group_snapshot(obj: Object) -> tuple[dict[str, str], dict[str, tuple]]:
    """记录 骨骼名 -> 组名 与 组名 -> 颜色, 合并骨架(join)前调用, 否则组会按索引错位"""
    bone_groups = {
        pose_bone.name: pose_bone.bone_group.name
        for pose_bone in obj.pose.bones
        if pose_bone.bone_group
    }
    group_colors = {}
    for group in obj.pose.bone_groups:
        group_colors[group.name] = (
            group.color_set,
            tuple(group.colors.normal),
            tuple(group.colors.select),
            tuple(group.colors.active),
        )
    return bone_groups, group_colors


def apply_bone_group_snapshot(
    obj: Object,
    snapshot: tuple[dict[str, str], dict[str, tuple]],
    bone_names: Iterable[str] | None = None,
) -> int:
    """把快照里的骨骼组和颜色还原到 obj(可只处理 bone_names), 返回还原的骨骼数。

    obj 里已有的同名组保持原样, 避免覆盖官方 Armature 自带的分组颜色。
    """
    bone_groups, group_colors = snapshot
    bone_names = None if bone_names is None else set(bone_names)

    group_map: dict[str, BoneGroup] = {}
    restored = 0
    for bone_name, group_name in bone_groups.items():
        if bone_names is not None and bone_name not in bone_names:
            continue
        pose_bone = obj.pose.bones.get(bone_name)
        if pose_bone is None:
            continue

        group = group_map.get(group_name)
        if group is None:
            group = obj.pose.bone_groups.get(group_name)
            if group is None:
                group = obj.pose.bone_groups.new(name=group_name)
                _set_group_colors(group, group_colors.get(group_name))
            group_map[group_name] = group

        pose_bone.bone_group = group
        restored += 1

    if restored:
        obj.data.show_group_colors = True
    return restored


def _set_group_colors(group: BoneGroup, colors: tuple | None):
    if not colors:
        return

    color_set, normal, select, active = colors
    group.color_set = color_set
    if color_set == "CUSTOM":
        group.colors.normal = normal
        group.colors.select = select
        group.colors.active = active
