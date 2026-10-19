"""补齐 kk 表情形态键并导出头模 (头模智能更新调用, 不要单独运行)"""

import bpy

from hitori_addon.error import ObjectError
from hitori_addon.exporter import export_kk_fbx
from hitori_addon.game_data import (
    get_kk_expression_code_name_map,
    get_kk_head_blend_shape_names,
)
from hitori_addon.mesh import (
    add_key,
    get_key_names,
    get_keys,
    remove_unused_material_slot,
)
from hitori_addon.obj import (
    clear_parent,
    only_show_objs,
    select_obj,
    set_mode,
    set_unity_matrix,
)

obj = bpy.context.object
arm = obj.parent

if obj.type != "MESH" or arm.type != "ARMATURE":
    raise ObjectError(obj, "选中的头模类型错误,选中物体不是网格,或其父级不是骨架")

keys = get_keys(obj)

# 重置形态键
obj.show_only_shape_key = False
for key in keys:
    key.value = 0

# kk表情名称
expression_code_name_map = get_kk_expression_code_name_map()
all_expressions = list(expression_code_name_map.values())
brow_expressions = [
    i for i in all_expressions if i.startswith("b") and not i.startswith("bc")
]
brow_close_00_expression = expression_code_name_map["bc00"]
eye_expressions = [i for i in all_expressions if i.startswith("e")]
mouth_expressions = [
    i for i in all_expressions if i.startswith("m") and not i.startswith("mc")
]
mouth_close_expressions = [i for i in all_expressions if i.startswith("mc")]

# 检查表情是否已全部制作完成
unfinished_expressions = set(all_expressions) - set(get_key_names(obj))
if unfinished_expressions:
    raise LookupError(f"请补全以下表情后重试: {unfinished_expressions}")

# 混合生成bc00之外的其他bc眉毛闭合表情
brow_close_expressions = ["bc" + expression[1:] for expression in brow_expressions]
brow_close_00_expression_key = keys[brow_close_00_expression]
for brow_expression, brow_close_expression in zip(
    brow_expressions[1:], brow_close_expressions[1:]
):
    brow_expression_key = keys[brow_expression]

    brow_expression_key.value = 1
    brow_close_00_expression_key.value = 1

    add_key(obj, key_name=brow_close_expression, from_mix=True)

    brow_expression_key.value = 0
    brow_close_00_expression_key.value = 0

# 复制生成ec的所有表情
eye_close_expressions = ["ec" + expression[1:] for expression in eye_expressions]
eye_close_to_open_expression_indices = [
    1,
    1,
    3,
    3,
    3,
    5,
    6,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
]
eye_close_to_open_expression_map = {
    close_expression: eye_expressions[eye_close_to_open_expression_indices[i]]
    for i, close_expression in enumerate(eye_close_expressions)
}

for close_expression in eye_close_expressions:
    target_eye_expression_key = keys[eye_close_to_open_expression_map[close_expression]]

    target_eye_expression_key.value = 1

    add_key(obj, key_name=close_expression, from_mix=True)

    target_eye_expression_key.value = 0

# 混合替换所有e眼睛表情
for eye_expression, eye_close_expression in zip(eye_expressions, eye_close_expressions):
    old_eye_expression_key = keys[eye_expression]
    eye_close_expression_key = keys[eye_close_expression]

    old_eye_expression_key.slider_max = 1.19
    old_eye_expression_key.value = 1.19
    eye_close_expression_key.slider_min = -0.19
    eye_close_expression_key.value = -0.19

    old_eye_expression_key.name += "_old"
    add_key(obj, key_name=eye_expression, from_mix=True)

    old_eye_expression_key.value = 0
    old_eye_expression_key.slider_max = 1
    eye_close_expression_key.value = 0
    eye_close_expression_key.slider_min = 0

# 获取b,bc,e,ec,m,mc到有效形态键集合中
valid_key_names = (
    brow_expressions
    + brow_close_expressions
    + eye_expressions
    + eye_close_expressions
    + mouth_expressions
    + mouth_close_expressions
)

# 按顺序混合替换所有有效形态键(将形态键生效范围限制在非脖子顶点组内)
# 生成的顺序会严格按照kk形态键排序
for valid_key_name in valid_key_names:
    old_key = keys[valid_key_name]

    old_key.vertex_group = "cf_J_FaceBase"
    old_key.value = 1

    old_key.name += "_old"
    add_key(obj, key_name=valid_key_name, from_mix=True)

    old_key.value = 0
    old_key.vertex_group = ""

# 删除有效形态键之外的无用形态键(不能删除形态键第一个的Basis形态键)
# 剩余形态键的顺序会严格按照kk形态键排序
invalid_key_names = set(get_key_names(obj)[1:]) - set(valid_key_names)
for invalid_key_name in invalid_key_names:
    obj.shape_key_remove(keys[invalid_key_name])

# 将剩余的Basis之外的有效形态键按kk形态键名称重命名
for key, kk_blendshape_name in zip(keys[1:], get_kk_head_blend_shape_names()):
    key.name = kk_blendshape_name

# 后处理和导出fbx
set_mode("OBJECT")

select_obj(obj)
clear_parent(obj)
set_unity_matrix(obj)
obj.active_shape_key_index = 0

# 清除网格无用材质槽
remove_unused_material_slot(obj)

only_show_objs([obj, arm])

export_kk_fbx()
