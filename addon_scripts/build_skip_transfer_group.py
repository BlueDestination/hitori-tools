"""按骨骼名标记哪些顶点不从 bodytight 传权重

导出服装 mod 前必做: 没有标记的网格会整片传权重, 覆盖已有权重 (尤其是已经合并到 KK 顶点组的网格)。
总会建 skip_transfer_group, 一个顶点都不用跳过时就留个空组 (空组与缺失都算整片传, 建出来方便对比)。
"""

from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.template_link import BODYTIGHT_NAME, SKIP_TRANSFER_GROUP_NAME
from hitori_addon.vg import build_skip_transfer_group, get_weight_sum_stats
from hitori_addon.view import enter_weight_paint

TITLE = "构建skip_transfer_group"
REMINDER = (
    "提醒: 导出服装mod前必须执行本步骤, "
    "否则没有标记的网格会整片传权重, 覆盖已有权重\n"
    "权重模式看 skip_transfer_group: 蓝色(无权重)的顶点就是后续会传递权重的 "
    "(已自动切到线框 + 权重模式, Shift+Z 切回实体)"
)

objs = selected_meshes()
if not objs:
    message_box("请先选中服装网格", title=TITLE, icon="ERROR")
else:
    lines: list[str] = []
    full_names: list[str] = []
    skipped_names: list[str] = []
    unbalanced_names: list[str] = []
    marked_objs = []

    for obj in objs:
        # bodytight 是权重传递源, 标了会覆盖每个服装网格的标记
        if obj.name == BODYTIGHT_NAME:
            skipped_names.append(obj.name)
            continue

        marked_objs.append(obj)
        skip_count = build_skip_transfer_group(obj)
        if skip_count:
            percent = skip_count / max(len(obj.data.vertices), 1)
            lines.append(f"{obj.name}: 跳过 {skip_count} 个顶点 ({percent:.0%})")
        else:
            full_names.append(obj.name)

        unbalanced_count = get_weight_sum_stats(obj)[0]
        if unbalanced_count:
            unbalanced_names.append(f"{obj.name} {unbalanced_count} 顶点")

    if full_names:
        lines.append(f"无需跳过 (整片传权重): {', '.join(full_names)}")
    if skipped_names:
        lines.append(f"跳过 {', '.join(skipped_names)} (是权重传递源, 不能标记)")
    if unbalanced_names:
        lines.append("")
        lines.append(f"权重和偏离 1: {', '.join(unbalanced_names)}")
        lines.append("建议先运行「移植步骤 > 归一化权重」: 游戏端按权重和蒙皮, 否则这些顶点会塌缩/拉伸")
    lines.append("")
    lines.append(REMINDER)
    # 直接摆好透视检查的姿势: 线框着色 + 权重模式, 激活组就是 skip_transfer_group
    enter_weight_paint(marked_objs, SKIP_TRANSFER_GROUP_NAME)
    message_box("\n".join(lines), title=TITLE)
