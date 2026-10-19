import bpy

from hitori_addon.mesh import add_key, get_keys

obj = bpy.context.object

keys = get_keys(obj)

keys_len_digit_count = len(str(len(keys)))

add_key(obj, key_name="Empty", from_mix=True, select=True)
bpy.ops.object.shape_key_move(type="TOP")

for i, key in enumerate(keys):
    key.name = f"{i:0{keys_len_digit_count}}_{key.name}"
