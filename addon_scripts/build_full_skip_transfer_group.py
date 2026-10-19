"""把整个网格标记成 skip_transfer_group (全 1): 导出服装 mod 时一个顶点都不传权重

给已经自带官方权重的网格用 (手工做的基准件等); 烘焙产物会自动标记, 不用跑这个。
"""

from hitori_addon.menu import message_box
from hitori_addon.mesh import get_vertex_indices, selected_meshes
from hitori_addon.vg import set_skip_transfer_group

TITLE = "整网格不传权重"

objs = selected_meshes()
if not objs:
    message_box("请先选中网格", title=TITLE, icon="ERROR")
else:
    for obj in objs:
        set_skip_transfer_group(obj, get_vertex_indices(obj))
    names = ", ".join(obj.name for obj in objs)
    message_box(f"已标记 {len(objs)} 个网格整片不传权重: {names}", title=TITLE)
