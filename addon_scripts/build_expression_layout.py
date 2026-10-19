import bpy

from hitori_addon.const import ADDON_SCRIPTS_DIR, require_external_resources
from hitori_addon.template_link import EXPRESSION_WORKSPACE_NAME, TEMPLATE_BLEND
from hitori_addon.text import write_text_data

require_external_resources()

script_path = ADDON_SCRIPTS_DIR / "gen_shapekey_script.py"
with open(script_path, "r", encoding="utf-8") as f:
    text_content = f.read()

lines = text_content.rstrip().split("\n")
if not lines:
    raise ValueError("生成形态键脚本文件为空")

last_not_empty_line_index = len(lines) - 1
last_not_empty_line = lines[last_not_empty_line_index]
last_not_empty_line_len = len(last_not_empty_line)

text_data = write_text_data("shapekey_script", text_content)
text_data.current_line_index = last_not_empty_line_index
text_data.select_end_line_index = last_not_empty_line_index
text_data.current_character = last_not_empty_line_len - 3
text_data.select_end_character = last_not_empty_line_len - 2

blend_layout_name = EXPRESSION_WORKSPACE_NAME

if not bpy.data.workspaces.get(blend_layout_name):
    with bpy.data.libraries.load(str(TEMPLATE_BLEND)) as (data_from, data_to):
        data_to.workspaces = [blend_layout_name]

bpy.context.window.workspace = bpy.data.workspaces.get(blend_layout_name)
