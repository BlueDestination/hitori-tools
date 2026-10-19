"""生成调试脚本文本块 `debugger_script`

监听线程只能由用户自己在文本编辑器里启动: 插件代为执行会出问题, 所以这里只写入
文本块并弹窗提示手动 Alt+P 运行 (通信机制见 `hitori_addon/debugger.py`)。
"""

from pathlib import Path

from hitori_addon import debugger
from hitori_addon.menu import message_box
from hitori_addon.text import write_text_data

TITLE = "生成调试脚本"

text_data_name = "debugger_script"
debugger_script_path = Path(debugger.__file__).resolve()

with open(debugger_script_path, "r", encoding="utf-8") as f:
    content = f.read()

write_text_data(text_data_name, content)

lines = [
    f"文本块 {text_data_name} 已写入, 但需要你自己执行:",
    f"文本编辑器 -> 文本块 {text_data_name} -> Alt+P",
    "",
    "插件不能替你执行: 监听必须由你手动启动, 插件自己跑会出问题",
    "启动后外部才能连 127.0.0.1:61001 (只读探查, 不要调 bpy.ops)",
]
message_box("\n".join(lines), title=TITLE)
