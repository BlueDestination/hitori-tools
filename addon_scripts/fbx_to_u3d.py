"""把桌面的 fbx 导入 abdata 的 unity3d 并热重载 (服装/饰品/头模智能更新调用, 不要单独运行)"""

import shutil
from pathlib import Path

import UnityPy

from hitori_addon.const import ABDATA_DIR, DESKTOP_DIR, SB3U_DIR
from hitori_addon.fbx import (
    get_fbx_scene,
    get_scene_frames,
    get_scene_meshes_materials_textures,
    process_meshes_materials_textures,
)
from hitori_addon.hotreload import update_and_refresh_mod
from hitori_addon.image import img_to_kk_color
from hitori_addon.path import get_blend_file_stem, get_file_stem
from hitori_addon.progress import Progress
from hitori_addon.sb3u import MESH_ANIMATOR_MAP, Sb3uFbxMesh, sb3u_run_script
from hitori_addon.text import write_temp_text
from hitori_addon.u3d import get_component_index_map, get_u3d_img_names


def get_import_mesh_script(chara_name: str, is_headmod: bool) -> str:
    if not is_headmod:
        return f"""
// ------打开所有网格对应的animator-------
// 必须要先打开所有需要的animator，再导入后续网格模型（贴图和材质则无影响），否则animator_component_index会错位
{open_animators_lines}

// ----------导入所有网格-----------------
{import_meshes_lines}
"""
    else:
        headmod_mesh_name = f"{chara_name}_headmod"
        headmod_component_index = 345
        collider_component_index = 349
        headmod_mesh_frame_id = 92
        return f"""
// ------打开所有网格对应的animator-------
// 必须要先打开所有需要的animator，再导入后续网格模型（贴图和材质则无影响），否则animator_component_index会错位
// 重要，碰撞头模在sb3u里显示是用OpenAnimator，而非用OpenVirtualAnimator来打开，而且之前写的定位index函数会错误，只能使用349来定位碰撞头模的index
virtualAnimator{collider_component_index} = unityEditor0.OpenAnimator(componentIndex={collider_component_index})
animatorEditor{collider_component_index} = AnimatorEditor(parser=virtualAnimator{collider_component_index})
unityEditor0.GetAssetNames(filter=True)

// ----------导入主头模网格-----------------
// 已经在dummy中打开了animator,因此无需重复打开
meshId = animatorEditor{headmod_component_index}.ReplaceMeshRenderer(mesh=importedEditor0.Meshes[0], frameId={headmod_mesh_frame_id}, merge=False, normals="Replace", bones="Replace", targetFullMesh=False)

// ----------导入主头模形态键-----------------
animatorEditor{headmod_component_index}.ReplaceMorph(morph=importedEditor0.Morphs[0], destMorphName="mayuge [{headmod_mesh_name}]", replaceNormals=False, minSquaredDistance=0.0000000001)
animatorEditor{headmod_component_index}.ReplaceMorph(morph=importedEditor0.Morphs[1], destMorphName="eye_face [{headmod_mesh_name}]", replaceNormals=False, minSquaredDistance=0.0000000001)
animatorEditor{headmod_component_index}.ReplaceMorph(morph=importedEditor0.Morphs[2], destMorphName="kuti_face [{headmod_mesh_name}]", replaceNormals=False, minSquaredDistance=0.0000000001)

// ----------碰撞头模形态归位-----------------
animatorEditor{collider_component_index}.AlignSkinnedMeshRendererWithMesh(meshId=0)
"""


def get_sb3u_script(chara_name: str, is_headmod: bool) -> str:
    return rf"""
// 导入插件,并将u3d文件赋值给unityEditor0(如果使用GUI请删除这部分,GUI打开文件会自动设置这部分)
LoadPlugin("{SB3U_DIR}\plugins\UnityPlugin.dll")
LoadPlugin("{SB3U_DIR}\plugins\UnityBase.dll")
unityParser0 = OpenUnity3d(path="{u3d_path}")
unityEditor0 = Unity3dEditor(parser=unityParser0)

// 导入fbx为importedEditor0
importFbx0 = ImportFbx(path="{fbx_path}", averageNormals=True, negateQuaternionFlips=True, forceTypeSampled=True)
importedEditor0 = ImportedEditor(importFbx0)

// 开始导入内容到u3d
unityeditor0.BeginTransfer()

// ----------导入贴图和材质------------
// 打开任意animator仅用于导入贴图和材质
virtualAnimator{dummy_animator_index} = unityEditor0.OpenVirtualAnimator(componentIndex={dummy_animator_index})
animatorEditor{dummy_animator_index} = AnimatorEditor(parser=virtualAnimator{dummy_animator_index})
unityEditor0.GetAssetNames(filter=True)

// 导入纹理
{import_texture_lines}

// 导入材质
{import_material_lines}

// ----------导入网格-----------------
{get_import_mesh_script(chara_name, is_headmod)}

// ----------结束-------------------
// 结束导入内容到u3d
unityeditor0.EndTransfer()

// 保存文件(background=False才能在非GUI保存)
unityEditor0.SaveUnity3d(keepBackup=False, backupExtension=".unity3d", background=False, clearMainAsset=True, pathIDsMode=-1)
"""


def main(chara_name: str):
    global \
        u3d_path, \
        fbx_path, \
        dummy_animator_index, \
        import_texture_lines, \
        import_material_lines, \
        open_animators_lines, \
        import_meshes_lines

    # 获取fbx信息
    fbx_path = DESKTOP_DIR / f"{chara_name}.fbx"
    fbx_scene = get_fbx_scene(fbx_path)
    fbx_frames = get_scene_frames(fbx_scene)
    meshes_materials_textures = get_scene_meshes_materials_textures(fbx_scene)
    fbx_mesh_names, fbx_materials, fbx_img_paths, fbx_normal_paths = (
        process_meshes_materials_textures(meshes_materials_textures)
    )

    # 分析是否是头模
    is_headmod = f"{chara_name}_headmod" in fbx_mesh_names
    u3d_basename = (
        f"{chara_name}.unity3d" if not is_headmod else f"{chara_name}-head.unity3d"
    )

    # 获取u3d的信息
    u3d_path = ABDATA_DIR / u3d_basename
    env = UnityPy.load(str(u3d_path))
    env_objs = env.objects
    component_index_map = get_component_index_map(env_objs)
    u3d_img_names = get_u3d_img_names(env_objs)

    # 生成校色后tga
    unimported_img_paths = [
        img_path
        for img_path in fbx_img_paths
        if get_file_stem(img_path) not in u3d_img_names
    ]
    unimported_tga_paths = [
        DESKTOP_DIR / f"{get_file_stem(img_path)}.tga"
        for img_path in unimported_img_paths
    ]
    for img_path, tga_path in Progress(zip(unimported_img_paths, unimported_tga_paths)):
        img_to_kk_color(img_path, tga_path, file_format="TARGA")

    # 复制法线贴图
    unimported_normal_paths = [
        Path(normal_path)
        for normal_path in fbx_normal_paths
        if get_file_stem(normal_path) not in u3d_img_names
    ]
    for normal_path in unimported_normal_paths:
        shutil.copy(normal_path, DESKTOP_DIR)

    # 导入校色后tga和法线贴图
    unimported_tga_and_normal_paths = unimported_tga_paths + unimported_normal_paths

    # 使用dummy animator导入贴图和材质
    dummy_animator_index = (
        component_index_map["0.hair"]
        if not is_headmod
        else component_index_map["p_cf_head_00"]
    )
    import_texture_lines = "\n".join(
        [
            f'image{i} = ImportTexture(path="{img_path}")\nanimatorEditor{dummy_animator_index}.AddTexture(image=image{i})'
            for i, img_path in enumerate(unimported_tga_and_normal_paths)
        ]
    )
    import_material_lines = "\n".join(
        [
            f'animatorEditor{dummy_animator_index}.MergeMaterial(mat=importedEditor0.Imported.MaterialList[{i}], opDiff=0, slotDiff="_MainTex", '
            'opAmb=0, slotAmb="unused", opEmi=1, slotEmi="Spec", opSpec=1, slotSpec="Norm", opBump=0, slotBump="_BumpMap")'
            for i, fbx_material in enumerate(fbx_materials)
        ]
    )

    fbx_meshes = [Sb3uFbxMesh(index, name) for index, name in enumerate(fbx_mesh_names)]

    open_animators_line_list = []
    import_meshes_line_list = []
    for fbx_mesh in fbx_meshes:
        component_index = (
            component_index_map[MESH_ANIMATOR_MAP[fbx_mesh.name]]
            if not fbx_mesh.is_headmod
            else component_index_map["p_cf_head_00"]
        )
        armature_dest_parent_id = fbx_mesh.arm_dst_parent_id
        fbx_mesh_index = fbx_mesh.index
        frame_id = fbx_mesh.frame_id
        fbx_arm_frame_index = (
            fbx_frames.index(fbx_mesh.arm_name) if fbx_mesh.is_acc else 0
        )
        open_one_animators_lines = (
            "// 打开单个网格的Animator导入骨架和网格\n"
            f"virtualAnimator{component_index} = unityEditor0.OpenVirtualAnimator(componentIndex={component_index})\n"
            f"animatorEditor{component_index} = AnimatorEditor(parser=virtualAnimator{component_index})\n"
        )
        import_mesh_lines = (
            "// 导入骨架和网格\n"
            f"animatorEditor{component_index}.MergeFrame(srcFrame=importedEditor0.Frames[{fbx_arm_frame_index}], "
            f"destParentId={armature_dest_parent_id})\n"
            f"meshId = animatorEditor{component_index}.ReplaceMeshRenderer(mesh=importedEditor0.Meshes[{fbx_mesh_index}], "
            f'frameId={frame_id}, merge=False, normals="Replace", bones="Replace", targetFullMesh=False)\n'
        )
        open_animators_line_list.append(open_one_animators_lines)
        import_meshes_line_list.append(import_mesh_lines)

    open_animators_lines = "\n".join(open_animators_line_list)
    import_meshes_lines = "\n".join(import_meshes_line_list)

    sb3u_script_str = get_sb3u_script(chara_name, is_headmod)
    sb3u_script_path = write_temp_text(sb3u_script_str)
    sb3u_run_script(sb3u_script_path)
    update_and_refresh_mod(u3d_path)


if __name__ == "__main__":
    main(get_blend_file_stem())
