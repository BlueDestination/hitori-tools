"""命名服装: 按关键词把选中的网格改成游戏里的合法名称

规则见 `hitori_addon/naming.py`:
    - 先试服装类 (cloth_top / cloth_bot / cloth_bra / pants / glove / panty / sock / shoe),
      同一目标有多个网格时第一个用本名, 后面的加 `_2` / `_3`, 需要自己合并;
    - 再试饰品: 头发 / 尾巴 / 翅膀 / 其它不连在服装上的配件 -> acc, 头发排在最前,
      超出 acc9 继续编号并加 `_` 前缀 (如 `_acc10`);
    - 再试身体类: body / body-head / body-hitomi / body-eye / body-eyebrow / body-eyeline /
      body-mouth / body-nail / body-hand / body-leg / body-ear, 只为归类方便批量处理, 不参与导出;
    - 无法自动归类的网格加 `_` 前缀, 提示需要手动改;
    - `.001`(半脱) 网格和已是合法名的网格不动。
拆分(上下状态 / 连体服)仍然自己手动做。
"""

from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.naming import is_merge_name, rename_meshes

TITLE = "命名服装"

objs = selected_meshes()
if not objs:
    message_box("请先选中网格", title=TITLE, icon="ERROR")
else:
    renames = rename_meshes(objs)
    if not renames:
        message_box(f"共 {len(objs)} 个网格, 都已经是对的, 没有改动", title=TITLE)
    else:
        lines = [f"共改名 {len(renames)} 个网格"]
        lines += [f"{old_name} -> {new_name}" for old_name, new_name in renames.items()]
        merge_names = [new_name for new_name in renames.values() if is_merge_name(new_name)]
        if merge_names:
            lines.append("")
            lines.append(
                f"带 _2 / _3 后缀的 {len(merge_names)} 个需要自己合并到同名网格"
            )
        manual_names = [new_name for new_name in renames.values() if new_name.startswith("_")]
        if manual_names:
            lines.append("")
            lines.append(f"加 _ 前缀的 {len(manual_names)} 个需要自己确认, 其余可导出")
        message_box("\n".join(lines), title=TITLE)
