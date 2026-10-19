import tempfile
from typing import Literal


def write_text_data(
    text_data_name: str,
    content: str,
    mode: Literal["w", "a"] = "w",
    add_newline: bool = True,
):
    import bpy

    if mode not in ("w", "a"):
        raise ValueError('mode参数错误,只能为"w"或"a"')

    if mode == "a" and add_newline:
        content += "\n"

    text_data = bpy.data.texts.get(text_data_name)
    if not text_data:
        text_data = bpy.data.texts.new(name=text_data_name)

    if mode == "w":
        text_data.clear()
        text_data.write(content)
    elif mode == "a":
        last_line_index = len(text_data.lines) - 1
        last_character_index = len(text_data.lines[last_line_index].body)
        text_data.cursor_set(line=last_line_index, character=last_character_index)
        text_data.write(content)

    return text_data


def write_temp_text(content: str, encoding: str = "utf-8") -> str:
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".txt", mode="w", encoding=encoding
    ) as f:
        f.write(content)
        return f.name
