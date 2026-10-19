"""动骨骨架自动清理

复制当前骨架为 <名>-db 后清理, 原骨架保持不动; 被删掉的骨骼另存到 <名>-deleted 骨架里备查。
复制后先把姿态固化成静置骨架 (`arm.freeze_pose`: 外部骨架的可视状态 -> rest, 并清空姿态通道),
否则后面接骨/合并/导出时骨骼会跳回外部骨架的原始静置位置。
结束后隐藏原骨架与 <名>-deleted, 只显示 <名>-db 并进入编辑模式。
两个骨架的骨骼分别归入骨骼组 db(绿) / deleted(红), 方便翻出来对比。
删除四类无用骨:
(1) 整棵子树都没有权重; (2) 子树里不含任何动骨的标准人形骨;
(3) 首词带 hip(s)/tail(s) 的骨骼(臀部几乎不挂服装动骨, 尾巴通常是饰品), 连同子树一起删;
(4) 脖子以上(头 / 头发 / 发饰)的骨骼, 不再是服装, 整枝删(只删动骨, 人形骨一律保留)。
头 / 发删完后只剩人形骨的空枝(如 Neck -> Head)一并删掉。
最后把所有剩下的标准人形骨(身体骨, 如 Spine / Chest / Upper_leg.L)一起删:
动骨骨架只留动骨链与接骨(链根骨), 链根骨删完各自成为根骨。
"""

import bpy

from hitori_addon.arm import delete_bones, freeze_pose, get_bone_names
from hitori_addon.bonegroup import GREEN, RED, color_by_bone_group
from hitori_addon.dynbone import (
    find_body_bone_names,
    find_neck_z,
    find_useless_bone_names,
)
from hitori_addon.error import ObjectError
from hitori_addon.menu import format_name_list, message_box
from hitori_addon.obj import copy_obj, hide_obj, select_obj, set_mode

KEEP_SUFFIX = "-db"
DELETED_SUFFIX = "-deleted"
GROUP_KEEP = "db"
GROUP_DELETED = "deleted"


def main():
    source = bpy.context.object
    if source is None or source.type != "ARMATURE":
        raise ObjectError(source, "请选中要清理的动骨骨架(会复制成 <名>-db 再清理)")

    arm = copy_obj(source, name=source.name + KEEP_SUFFIX)
    # 后续清理 / 接骨 / 合并 / 导出都用静置坐标, 所以先固化可视姿态
    freeze_pose(arm)
    removed = find_useless_bone_names(arm)
    delete_bones(arm, removed)
    # 动骨骨架只要接骨与动骨链: 前面为链根骨保住的身体骨最后一起删
    body_names = find_body_bone_names(arm)
    delete_bones(arm, body_names)
    removed = sorted(set(removed) | set(body_names))

    deleted = None
    if removed:
        # 被删的骨骼原样留一份, 方便事后检查是否删错
        deleted = copy_obj(source, name=source.name + DELETED_SUFFIX)
        # 跟 -db 一起固化, 两副骨架的骨骼位置才能对上
        freeze_pose(deleted)
        removed_set = set(removed)
        delete_bones(
            deleted,
            [name for name in get_bone_names(deleted) if name not in removed_set],
        )

    # 两个骨架各染一种颜色, 同时翻出来对比时不会看混
    color_by_bone_group(arm, GROUP_KEEP, GREEN)
    if deleted is not None:
        color_by_bone_group(deleted, GROUP_DELETED, RED)

    lines = [f"{arm.name}: 保留 {len(arm.data.bones)} 骨"]
    lines.append(
        f"{deleted.name}: 删除 {len(removed)} 骨" if deleted else "没有需要删除的骨骼"
    )
    if body_names:
        lines.append(f"身体骨 {len(body_names)} 根已删:")
        lines.append(format_name_list(body_names, indent="    "))
    if find_neck_z(arm) is None:
        lines.append(
            "没找到参考颈部(同源原始骨架或对齐后的 Armature), 已跳过脖子以上剪枝"
        )

    # 只留 -db: 原骨架与 -deleted 藏起来, 并进入编辑模式方便继续微调
    select_obj(arm)
    hide_obj(source)
    if deleted is not None:
        hide_obj(deleted)
    set_mode("EDIT")

    message_box("\n".join(lines), title="动骨骨架自动清理")


if __name__ == "__main__":
    main()
