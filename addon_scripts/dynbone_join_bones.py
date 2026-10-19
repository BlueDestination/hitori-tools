import bpy

from hitori_addon.arm import get_bone_names, get_root_bone_names
from hitori_addon.bonegroup import (
    ORANGE,
    apply_bone_group_snapshot,
    color_by_bone_group,
    get_bone_group_snapshot,
)
from hitori_addon.dynbone import (
    KK_JOINT_BONE_NAMES,
    KK_JOINT_LONG_BONE_NAMES,
    ROOT_BONE_GROUP_NAME,
    find_kk_joint_bone_names,
)
from hitori_addon.menu import message_box
from hitori_addon.obj import get_obj, merge_objs, set_mode
from hitori_addon.template_link import ARMATURE_NAME

arm = get_obj(ARMATURE_NAME)
arm_to_merge = bpy.context.object

new_root_bone_names = get_root_bone_names(arm_to_merge)

# join 按组索引合并骨骼组, 不先记下来, db 骨骼组的颜色会丢(骨骼落进 Armature 原有的组)
merge_bone_names = set(get_bone_names(arm_to_merge))
bone_group_snapshot = get_bone_group_snapshot(arm_to_merge)

merge_objs([arm, arm_to_merge], target_obj=arm)
set_mode("OBJECT")

apply_bone_group_snapshot(arm, bone_group_snapshot, merge_bone_names)
if new_root_bone_names:
    # 接骨的那几根根骨单独用橙色标出来
    color_by_bone_group(arm, ROOT_BONE_GROUP_NAME, ORANGE, new_root_bone_names)

arm_bones = arm.data.bones
arm_edit_bones = arm.data.edit_bones

# 骨骼没有.location属性,用.matrix_local.to_translation()来获取骨骼位置
kk_joint_bone_position_map = {
    name: arm_bones[name].matrix_local.to_translation()
    for name in KK_JOINT_BONE_NAMES
}
# 长骨的远端关节只用来划区域(不是候选关节), 模板里没有就退回关节头距离
kk_joint_bone_position_map |= {
    name: arm_bones[name].matrix_local.to_translation()
    for name in KK_JOINT_LONG_BONE_NAMES.values()
    if name in arm_bones
}
new_root_bone_position_map = {
    name: arm_bones[name].matrix_local.to_translation() for name in new_root_bone_names
}

# 就近 + 长骨就上: 大腿 / 大臂中段的根骨挂到髋 / 肩侧关节
new_root_bone_to_kk_joint_bone_map = find_kk_joint_bone_names(
    new_root_bone_position_map, kk_joint_bone_position_map
)

set_mode("EDIT")
for edit_bone in arm_edit_bones:
    edit_bone.select = False

for (
    new_root_bone_name,
    kk_joint_bone_name,
) in new_root_bone_to_kk_joint_bone_map.items():
    new_root_edit_bone = arm_edit_bones[new_root_bone_name]
    new_root_edit_bone.parent = arm_edit_bones[kk_joint_bone_name]
    new_root_edit_bone.select = True

# 接骨完到姿态模式里试动骨, 接骨那几根骨保持选中
set_mode("POSE")

lines = ["已完成动骨接骨"]
lines += [
    f"{new_root_bone_name} -> {kk_joint_bone_name}"
    for new_root_bone_name, kk_joint_bone_name in new_root_bone_to_kk_joint_bone_map.items()
]
message_box("\n".join(lines), title="动骨骨架接骨")
