from collections.abc import Mapping
from types import MappingProxyType

import bpy

from hitori_addon.mesh import add_key, get_key_names, get_keys

expression_endswiths_map: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "m25A小": ("_あ", "_a", "_A"),
        "m26A大": ("_あ", "_a", "_A"),
        "m27I小": ("_い", "_i", "_I"),
        "m28I大": ("_い", "_i", "_I"),
        "m29U小": ("_う", "_u", "_U"),
        "m30U大": ("_う", "_u", "_U"),
        "m31E小": ("_え", "_e", "_E"),
        "m32E大": ("_え", "_e", "_E"),
        "m33O小": ("_お", "_o", "_O"),
        "m34O大": ("_お", "_o", "_O"),
        "m35N小": ("_Empty",),
        "m36N大": ("_Empty",),
    }
)

obj = bpy.context.object
obj.show_only_shape_key = False
keys = get_keys(obj)

all_expressions = get_key_names(obj)

expression_map = {}
for dst_expression, endswiths in expression_endswiths_map.items():
    for expression in all_expressions:
        if expression.endswith(endswiths):
            expression_map[dst_expression] = expression
            break
    else:
        raise ValueError(f'未找到表情"{dst_expression}"对应的五十音表情后缀{endswiths}')

for dst_expression, src_expression in expression_map.items():
    keys[src_expression].value = 1 if dst_expression.endswith("大") else 0.5
    add_key(obj, key_name=dst_expression, from_mix=True)
    keys[src_expression].value = 0
