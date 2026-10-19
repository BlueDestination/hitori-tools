import bpy

from hitori_addon.const import require_external_resources
from hitori_addon.obj import get_obj, hide_obj
from hitori_addon.template_link import (
    APPEND_COLLECTION_NAMES,
    ARMATURE_NAME,
    EYELINE_NAME,
    HEAD_NAME,
    HITOMI_NAME,
    TEMPLATE_BLEND,
)

require_external_resources()

with bpy.data.libraries.load(str(TEMPLATE_BLEND)) as (data_from, data_to):
    missing = [name for name in APPEND_COLLECTION_NAMES if name not in data_from.collections]
    if missing:
        raise RuntimeError(f"{TEMPLATE_BLEND} 里缺少集合: {missing}")
    data_to.collections = list(APPEND_COLLECTION_NAMES)

for collection in data_to.collections:
    bpy.context.scene.collection.children.link(collection)

hide_obj_names: tuple[str, ...] = (
    ARMATURE_NAME,
    HEAD_NAME,
    EYELINE_NAME,
    HITOMI_NAME,
)

for hide_obj_name in hide_obj_names:
    obj = get_obj(hide_obj_name)
    if obj:
        hide_obj(obj)
