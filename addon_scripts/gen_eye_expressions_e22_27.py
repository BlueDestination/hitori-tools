from collections.abc import Mapping
from types import MappingProxyType

import bpy

from hitori_addon.mesh import add_key, get_keys

expression_map: Mapping[str, str] = MappingProxyType(
    {
        "e22紧闭左眼": "e05眨眼L",
        "e23紧闭右眼": "e06眨眼R",
        "e24紧闭双眼-H": "e03笑脸闭眼",
        "e25紧闭左眼2": "e05眨眼L",
        "e26紧闭右眼2": "e06眨眼R",
        "e27紧闭双眼2": "e03笑脸闭眼",
    }
)

obj = bpy.context.object
obj.show_only_shape_key = False
keys = get_keys(obj)

for dst_expression, src_expression in expression_map.items():
    keys[src_expression].value = 1
    add_key(obj, key_name=dst_expression, from_mix=True)
    keys[src_expression].value = 0
