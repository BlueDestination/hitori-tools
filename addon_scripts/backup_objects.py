"""备份选中的物体: 复制为 bak_<名> 放进 bak 集合, 弹窗列出备份结果"""

from hitori_addon.menu import message_box
from hitori_addon.obj import backup_obj, selected_objs

TITLE = "备份物体"

objs = list(selected_objs())
if not objs:
    message_box("请先选中物体", title=TITLE, icon="ERROR")
else:
    backup_names = [backup_obj(obj).name for obj in objs]
    lines = [f"共备份 {len(backup_names)} 个物体 (已放进 bak 集合并隐藏):"]
    lines += backup_names
    message_box("\n".join(lines), title=TITLE)
