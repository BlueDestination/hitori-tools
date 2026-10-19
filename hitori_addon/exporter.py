import bpy
from bpy.types import Object

from hitori_addon.const import DESKTOP_DIR
from hitori_addon.path import get_blend_file_stem


def export_kk_fbx(add_leaf_bones: bool = False):
    chara_name = get_blend_file_stem()
    filepath = str(DESKTOP_DIR / f"{chara_name}.fbx")

    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=False,
        use_visible=True,
        use_active_collection=False,
        global_scale=0.01,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_NONE",
        use_space_transform=True,
        bake_space_transform=False,
        object_types={"ARMATURE", "MESH"},
        use_mesh_modifiers=True,
        use_mesh_modifiers_render=True,
        mesh_smooth_type="OFF",
        colors_type="SRGB",
        use_subsurf=False,
        use_mesh_edges=False,
        use_tspace=False,
        use_triangles=False,
        use_custom_props=False,
        add_leaf_bones=add_leaf_bones,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        use_armature_deform_only=False,
        armature_nodetype="NULL",
        bake_anim=True,
        bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=True,
        bake_anim_use_all_actions=True,
        bake_anim_force_startend_keying=True,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=1.0,
        path_mode="AUTO",
        embed_textures=False,
        batch_mode="OFF",
        use_batch_own_dir=True,
        axis_forward="-Z",
        axis_up="Y",
    )


def sort_objs_internal_order(
    objs: list[Object],
    collection_name: str = "objs_order_collection",
):
    new_collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(new_collection)

    sorted_objs = sorted(objs, key=lambda i: i.name)
    for obj in sorted_objs:
        for old_collection in obj.users_collection:
            old_collection.objects.unlink(obj)
        new_collection.objects.link(obj)
