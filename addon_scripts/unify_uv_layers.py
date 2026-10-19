"""统一 UV 层 (合并网格前先跑)

不同网格的有效 UV 可能分散在不同名字的层里 (`UVMap` / `UV 맵`), 另一层在这些面上全是 (0,0)。
合并成一个物体后只有一个 active 层生效, 那些面会退化成采样贴图同一个像素, 表现为一整块纯白
或颜色异常。这里把有效的面合并进一层 `UVMap` 并设为 active, 之后再合并物体就不会错。

对已经合并好的物体同样可用(按面挑有效的那一层), 所以合并完才发现问题也能救。
"""

from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.uv import unify_uv_layers

TITLE = "统一UV层"

objs = selected_meshes()
if not objs:
    message_box("请先选中网格", title=TITLE, icon="ERROR")
else:
    reports = [report for report in map(unify_uv_layers, objs) if report]
    if not reports:
        message_box(f"共 {len(objs)} 个网格, 没有需要修补的面", title=TITLE)
    else:
        lines = [f"共处理 {len(reports)} 个网格"]
        lines += reports
        message_box("\n".join(lines), title=TITLE)
