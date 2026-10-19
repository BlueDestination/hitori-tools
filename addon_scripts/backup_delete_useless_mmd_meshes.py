import bpy

from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.obj import copy_obj, delete_obj, deselect_obj, hide_obj

bak_collection_name = "bak"
bak_collection = bpy.data.collections.get(bak_collection_name)

if bak_collection is None:
    bak_collection = bpy.data.collections.new(bak_collection_name)
    bpy.context.scene.collection.children.link(bak_collection)


def is_useless_mmd_material_mesh(obj) -> bool:
    """判断网格是否为单材质且该材质以 + 结尾"""
    material_slots = obj.material_slots

    if len(material_slots) != 1:
        return False

    material = material_slots[0].material
    return material is not None and material.name.endswith("+")


useless_objs = [obj for obj in selected_meshes() if is_useless_mmd_material_mesh(obj)]

backup_names: list[str] = []
for obj in useless_objs:
    backup_obj = copy_obj(obj, name="bak_" + obj.name)
    backup_names.append(backup_obj.name)
    deselect_obj(backup_obj)
    hide_obj(backup_obj)

    for collection in backup_obj.users_collection:
        collection.objects.unlink(backup_obj)

    bak_collection.objects.link(backup_obj)
    delete_obj(obj)

bak_layer_collection = bpy.context.view_layer.layer_collection.children.get(
    bak_collection_name
)

if bak_layer_collection:
    bak_layer_collection.exclude = True

lines = [
    (
        f"共备份删除 {len(backup_names)} 个无用mmd材质网格 "
        f"(备份名加 bak_ 前缀, 已隐藏, 在 {bak_collection_name} 集合里):"
    )
]
lines.extend(backup_names)
message_box("\n".join(lines))
