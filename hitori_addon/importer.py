from pathlib import Path

import bpy

from hitori_addon.error import UserError
from hitori_addon.image import fix_missing_image_paths
from hitori_addon.menu import message_box

MMD_TOOLS_ADDON_NAME = "mmd_tools"
MMD_TOOLS_RECOMMENDED_VERSION = "2.8.0"
VRM_ADDON_NAME = "VRM_Addon_for_Blender-release"
VRM_EXTENSION_KEY = "vrm_addon_extension"


def is_addon_enabled(name: str) -> bool:
    import addon_utils

    return addon_utils.check(name)[1]


def enable_addon(name: str) -> bool:
    """已安装但未启用时临时启用, 不写进偏好设置; 返回最终是否可用"""
    import addon_utils

    if not is_addon_enabled(name):
        addon_utils.enable(name)
    return is_addon_enabled(name)


def strip_vrm_extension() -> None:
    """VRM 插件把整份 glTF 数据挂到场景/骨架/骨骼/材质上, 导入后已用不到"""
    id_blocks = [
        *bpy.data.scenes,
        *bpy.data.armatures,
        *bpy.data.materials,
        *bpy.data.objects,
        *bpy.data.meshes,
    ]
    for id_block in id_blocks:
        if VRM_EXTENSION_KEY in id_block:
            del id_block[VRM_EXTENSION_KEY]
    for armature in bpy.data.armatures:
        for bone in armature.bones:
            if VRM_EXTENSION_KEY in bone:
                del bone[VRM_EXTENSION_KEY]


def require_mmd_tools() -> None:
    """mmd_tools 是可选依赖, 用到时才检查; 缺失时弹窗提示安装并中断"""
    if enable_addon(MMD_TOOLS_ADDON_NAME):
        return

    from hitori_addon.menu import message_box

    message = "\n".join(
        (
            "缺少 mmd_tools 插件, 无法导入 pmx 模型.",
            f"请在 Blender 的 编辑 > 偏好设置 > 插件 里安装并启用后重试, 推荐版本 {MMD_TOOLS_RECOMMENDED_VERSION}.",
        )
    )
    message_box(message, title="缺少 mmd_tools 插件", icon="ERROR")
    raise UserError(message)


def import_vrm(filepath: str | Path):
    """VRM 插件默认禁用(会往保存的 blend 里写入大量元数据), 这里临时启用并在导入后清理"""
    was_enabled = is_addon_enabled(VRM_ADDON_NAME)
    if not enable_addon(VRM_ADDON_NAME):
        message = f"缺少 {VRM_ADDON_NAME} 插件, 无法导入 vrm 模型."
        from hitori_addon.menu import message_box

        message_box(message, title="缺少插件", icon="ERROR")
        raise UserError(message)

    bpy.ops.import_scene.vrm(
        filepath=str(filepath),
        use_addon_preferences=True,
        extract_textures_into_folder=False,
        make_new_texture_folder=True,
        set_shading_type_to_material_on_import=True,
        set_view_transform_to_standard_on_import=True,
        set_armature_display_to_wire=True,
        set_armature_display_to_show_in_front=True,
        set_armature_bone_shape_to_default=True,
    )
    if not was_enabled:
        strip_vrm_extension()


def report_fixed_image_paths() -> None:
    """贴图路径带手误时自动指向同目录下的真实文件, 并弹窗说一声 (只在有修正时)"""
    fixed = fix_missing_image_paths()
    if not fixed:
        return
    lines = ["贴图路径读不到, 已自动指向同目录下的同名文件:", ""]
    lines += [f"{Path(old).name} -> {Path(new).name}" for old, new in fixed]
    message_box("\n".join(lines), title="贴图路径修正")


def import_pmx(filepath: str | Path):
    require_mmd_tools()
    bpy.ops.mmd_tools.import_model(
        filepath=str(filepath),
        types={"MESH", "ARMATURE", "MORPHS"},
        scale=0.08,
        clean_model=True,
        remove_doubles=False,
        fix_IK_links=True,
        ik_loop_factor=5,
        apply_bone_fixed_axis=True,
        rename_bones=True,
        use_underscore=False,
        dictionary="DISABLED",
        use_mipmap=True,
        sph_blend_factor=1,
        spa_blend_factor=1,
        log_level="ERROR",
        save_log=False,
    )
    report_fixed_image_paths()


def import_fbx(filepath: str | Path):
    bpy.ops.import_scene.fbx(
        filepath=str(filepath),
        ui_tab="MAIN",
        use_manual_orientation=False,
        global_scale=1,
        bake_space_transform=False,
        use_custom_normals=True,
        colors_type="SRGB",
        use_image_search=True,
        use_alpha_decals=False,
        decal_offset=0.0,
        use_anim=True,
        anim_offset=1.0,
        use_subsurf=False,
        use_custom_props=True,
        use_custom_props_enum_as_string=True,
        ignore_leaf_bones=True,
        force_connect_children=True,
        automatic_bone_orientation=True,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        use_prepost_rot=True,
        axis_forward="-Z",
        axis_up="Y",
    )


# 后缀 -> 导入函数: scripts/view_model.py 与"导入外部模型"按钮共用, 加格式只改这里
MODEL_IMPORTERS = {
    ".fbx": import_fbx,
    ".vrm": import_vrm,
    ".pmx": import_pmx,
}


def get_model_filter_glob() -> str:
    """文件选择框的过滤器, 如 *.fbx;*.vrm;*.pmx"""
    return ";".join(f"*{suffix}" for suffix in MODEL_IMPORTERS)


def get_supported_model_hint() -> str:
    """弹窗提示里的格式清单, 如 .fbx / .vrm / .pmx"""
    return " / ".join(MODEL_IMPORTERS)


def split_pmx_by_material() -> None:
    """pmx 按材质拆成多个网格, 再去掉 mmd_tools 给网格加的名字前缀"""
    from hitori_addon.obj import get_objs, select_obj

    select_obj(get_objs("MESH")[-1])
    bpy.ops.mmd_tools.convert_materials()
    bpy.ops.mmd_tools.separate_by_materials()

    for mesh in get_objs("MESH"):
        mesh.name = mesh.name.split("_", 1)[-1]


# 导入后还要再处理的格式: 由 scripts/view_model.py 在骨架清理之后调用
MODEL_POST_PROCESSORS = {
    ".pmx": split_pmx_by_material,
}
