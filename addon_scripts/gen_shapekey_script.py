"""形态键生成模板: 用户在文本块 `shapekey_script` 里改表情类型后手动运行 (无菜单按钮)"""

from typing import Literal

import bpy

from hitori_addon.game_data import get_kk_expression_code_name_map
from hitori_addon.headmod import KK_EXPRESSION_TYPES
from hitori_addon.mesh import add_key, get_keys
from hitori_addon.text import write_text_data

LOG_TEXT_DATA_NAME = "shapekey_history"


def main(expression_type: Literal["b", "bc", "e", "m"]):
    if expression_type not in KK_EXPRESSION_TYPES:
        raise TypeError(f"表情类型{expression_type}在{KK_EXPRESSION_TYPES}中不存在")

    obj = bpy.context.object
    keys = get_keys(obj)

    # 获取要创建的新表情形态键的名称
    last_key_name = keys[-1].name
    # 赋予新表情起始序号
    new_key_code = expression_type + "00"

    # 如果新表情所在位置不是开始序号,则使用最新序号
    if last_key_name.startswith(expression_type):
        number_str = last_key_name[len(expression_type) : len(expression_type) + 2]
        if number_str.isnumeric():
            new_key_code = expression_type + f"{int(number_str) + 1:02}"

    expression_code_name_map = get_kk_expression_code_name_map()
    new_key_name = expression_code_name_map.get(new_key_code)
    if not new_key_name:
        raise LookupError(f'分组"{expression_type}"已完成所有形态键')

    current_valid_shapekey_value_map = {
        key.name: key.value for key in keys if key.value != 0
    }
    current_active_shapekey_index = obj.active_shape_key_index

    if obj.show_only_shape_key:
        write_text_data(
            LOG_TEXT_DATA_NAME,
            f'{new_key_name}: "{keys[current_active_shapekey_index].name}"',
            mode="a",
        )
    else:
        write_text_data(
            LOG_TEXT_DATA_NAME,
            f"{new_key_name}: {current_valid_shapekey_value_map}",
            mode="a",
        )

    # 以下开始生成新表情形态键
    if new_key_code.endswith("00"):
        # 如果新表情是起始序号,则提前添加当前表情分组分割线
        add_key(obj, key_name=expression_type + "-" * 20, from_mix=False)

    add_key(obj, key_name=new_key_name, from_mix=True)

    for key in keys:
        key.value = 0
        key.vertex_group = ""

    # 将选中形态键重设为运行脚本前的状态
    obj.active_shape_key_index = current_active_shapekey_index


if __name__ == "__main__":
    main(expression_type="b")
