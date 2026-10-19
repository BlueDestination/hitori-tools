"""添加叶骨: 给每个叶子骨骼加一根末端骨 (名为 xxx_end)

支持多骨架; 已带 _end 的骨骼跳过, 可重复执行。完成后弹窗列出数量与名称。
"""

from hitori_addon.arm import add_leaf_bones, selected_arms
from hitori_addon.error import ObjectError
from hitori_addon.menu import format_name_list, message_box

TITLE = "添加叶骨"


def main():
    arms = selected_arms()
    if not arms:
        raise ObjectError(None, "请先选中骨架")

    lines = []
    for arm in arms:
        names, skipped = add_leaf_bones(arm)
        if not names:
            lines.append(f"{arm.name}: 没有要加末端骨的叶子骨骼")
            continue
        text = f"{arm.name}: 新增 {len(names)} 根末端骨"
        if skipped:
            text += f", 跳过 {skipped} 根已带 _end 的骨骼"
        lines.append(text)
        lines.append(format_name_list(names, indent="    "))

    message_box("\n".join(lines), title=TITLE)


if __name__ == "__main__":
    main()
