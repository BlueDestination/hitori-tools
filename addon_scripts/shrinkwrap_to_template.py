"""给选中网格加缩裹修改器, 目标为 bodytight"""

from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.obj import get_obj
from hitori_addon.template_link import BODYTIGHT_NAME

TITLE = "衣物缩裹"

bodytight = get_obj(BODYTIGHT_NAME)
selected = selected_meshes()
# 缩裹目标不能是自己, bodytight 被一起选中时要跳过
objs = [obj for obj in selected if obj != bodytight]
if bodytight is None:
    message_box(f"场景里没有 {BODYTIGHT_NAME}, 先追加官方身体", title=TITLE, icon="ERROR")
elif not selected:
    message_box("请先选中网格", title=TITLE, icon="ERROR")
elif not objs:
    message_box(f"只选中了 {BODYTIGHT_NAME} 自身, 请再选中要缩裹的网格", title=TITLE, icon="ERROR")
else:
    for obj in objs:
        modifier = obj.modifiers.new(name="Shrinkwrap", type="SHRINKWRAP")
        modifier.wrap_method = "TARGET_PROJECT"
        modifier.wrap_mode = "ABOVE_SURFACE"
        modifier.target = bodytight
        modifier.show_on_cage = True

    lines = [f"目标: {BODYTIGHT_NAME}", f"已加缩裹: {len(objs)} 个网格"]
    lines.extend(f"  {obj.name}" for obj in objs)
    if len(objs) < len(selected):
        lines.append(f"已跳过 {BODYTIGHT_NAME} 自身")
    message_box("\n".join(lines), title=TITLE)
