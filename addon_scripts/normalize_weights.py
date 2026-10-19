"""归一化服装网格的骨骼权重

导入的 VRC/MMD 模型常有权重和不为 1 的顶点 (裙摆 / 丝带 / 头发等动骨部分), 游戏端不归一化,
权重和不到 1 的顶点会朝原点塌缩, 超过 1 会被拉伸, 所以导出前修一次。
只处理选中的网格; 只归一化与骨架骨骼同名的组, 标记组 / mmd_tools 的非骨骼组 / 锁定的组原样保留;
权重和已是 1 的顶点不动, 可以反复运行。
"""

from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.template_link import (
    BODYTIGHT_NAME,
    EYELINE_NAME,
    HEAD_NAME,
    HITOMI_NAME,
)
from hitori_addon.vg import (
    get_armature_bone_names,
    get_non_bone_vg_names,
    get_weight_sum_stats,
    normalize_weights,
)

TITLE = "归一化权重"
# 官方权重 (精确为 1) 与 KK 模板网格: 默认跳过
IGNORED_OBJ_NAMES: frozenset[str] = frozenset(
    {BODYTIGHT_NAME, HEAD_NAME, EYELINE_NAME, HITOMI_NAME}
)
NOTE = (
    "说明: 只缩放与骨架骨骼同名的组, 会改原始权重 (Ctrl+Z 可撤销)\n"
    "标记组 (bot_part / top_part / top_bot_edge / skip_transfer_group) / "
    "mmd_tools 的 mmd_edge_scale / mmd_vertex_order / 锁定的组原样保留\n"
    "游戏端按权重和蒙皮, 权重和不到 1 的顶点会朝原点塌缩, 超过 1 会被拉伸"
)

objs = selected_meshes()
if not objs:
    message_box("请先选中服装网格", title=TITLE, icon="ERROR")
else:
    lines: list[str] = []
    ok_names: list[str] = []
    skipped_names: list[str] = []
    preserved_names: set[str] = set()
    bone_names = get_armature_bone_names()

    for obj in objs:
        if obj.name in IGNORED_OBJ_NAMES:
            skipped_names.append(obj.name)
            continue

        preserved = get_non_bone_vg_names(obj, bone_names)
        if len(preserved) == len(obj.vertex_groups):
            skipped_names.append(f"{obj.name} (没有与骨架骨骼同名的顶点组)")
            continue

        preserved_names.update(preserved)
        fixed, max_deviation = normalize_weights(obj)
        unweighted = get_weight_sum_stats(obj)[2]
        if fixed:
            percent = fixed / max(len(obj.data.vertices), 1)
            lines.append(
                f"{obj.name}: 归一化 {fixed} 个顶点 ({percent:.0%}), "
                f"最大偏差 {max_deviation:.2f}"
            )
        else:
            ok_names.append(obj.name)
        if unweighted:
            lines.append(
                f"{obj.name}: {unweighted} 个顶点没有任何骨骼权重 "
                "(归一化无法修复, 需自己补权重)"
            )

    if not lines:
        lines.append("权重和都已是 1, 未改动")
    if ok_names:
        lines.append(f"已是 1 (未改动): {', '.join(ok_names)}")
    if skipped_names:
        lines.append(f"跳过 (官方权重 / 模板网格): {', '.join(skipped_names)}")
    if preserved_names:
        lines.append(f"保留的非骨骼组: {', '.join(sorted(preserved_names))}")
    lines.append("")
    lines.append(NOTE)
    message_box("\n".join(lines), title=TITLE)
