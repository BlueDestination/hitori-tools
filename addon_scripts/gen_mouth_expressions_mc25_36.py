import bpy

from hitori_addon.mesh import add_key

dst_expressions: tuple[str, ...] = (
    "mc25A小",
    "mc26A大",
    "mc27I小",
    "mc28I大",
    "mc29U小",
    "mc30U大",
    "mc31E小",
    "mc32E大",
    "mc33O小",
    "mc34O大",
    "mc35N小",
    "mc36N大",
)

obj = bpy.context.object
obj.show_only_shape_key = False

for dst_expression in dst_expressions:
    add_key(obj, key_name=dst_expression, from_mix=False)
