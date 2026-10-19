"""删除选中网格里没有非零权重的顶点组"""

from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.vg import delete_empty_vgs

TITLE = "删除空顶点组"

objs = selected_meshes()
if not objs:
    message_box("请先选中网格", title=TITLE, icon="ERROR")
else:
    lines: list[str] = []
    for obj in objs:
        deleted_names = delete_empty_vgs(obj)
        if not deleted_names:
            continue
        lines.append(f"{obj.name}: 删除 {len(deleted_names)} 个顶点组")
        lines.append(f"  {', '.join(deleted_names)}")

    if not lines:
        message_box("没有空顶点组", title=TITLE)
    else:
        message_box("\n".join(lines), title=TITLE)
