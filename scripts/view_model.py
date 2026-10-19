import sys
from pathlib import Path

from hitori_addon.arm import delete_unweighted_bone_trees, get_arm_meshes
from hitori_addon.importer import (
    MODEL_IMPORTERS,
    MODEL_POST_PROCESSORS,
    get_supported_model_hint,
)
from hitori_addon.obj import delete_obj, get_objs, hide_obj, select_obj, set_mode
from hitori_addon.path import aspath
from hitori_addon.uv import unify_uv_layers
from hitori_addon.vg import delete_empty_vgs, get_meshes_weighted_vg_names
from hitori_addon.view import fit_screen_view


def load_3d_model(filepath: str | Path):
    filepath = aspath(filepath)
    suffix = filepath.suffix.lower()
    import_model = MODEL_IMPORTERS.get(suffix)
    if import_model is None:
        supported = get_supported_model_hint()
        raise NotImplementedError(
            f"不支持预览的模型类型: {suffix or '没有后缀'}, 支持: {supported}"
        )
    import_model(filepath)

    fit_screen_view(get_objs(), min_z=0)

    # fbx 导入会选中骨架; vrm/pmx 取最后导入的那个骨架
    if suffix == ".fbx":
        arm = get_objs("ARMATURE", selected=True)[0]
    else:
        arm = get_objs("ARMATURE")[-1]

    # 骨骼预处理: 删除整棵子树都没有权重的骨骼树, 被删骨骼另存到 bak 集合备查
    # 权重在拆分网格前收集(pmx 导入时是单一网格, 拆分后要逐个网格扫一遍)
    arm_meshes = get_arm_meshes(arm)
    weighted_names = get_meshes_weighted_vg_names(arm_meshes)
    delete_unweighted_bone_trees(arm, weighted_names, backup=True)

    # 清掉各网格的空顶点组(同样在拆网格前做, 拆分后每块都会残留另一部分的空组)
    for mesh_obj in arm_meshes:
        delete_empty_vgs(mesh_obj)

    post_process = MODEL_POST_PROCESSORS.get(suffix)
    if post_process:
        post_process()

    # 删除空物体
    for obj in get_objs("EMPTY"):
        delete_obj(obj)

    # 各网格的有效 UV 可能在不同名字的层里, 合并物体后只剩 active 层会踩空, 先统一
    for mesh_obj in get_arm_meshes(arm):
        report = unify_uv_layers(mesh_obj)
        if report:
            print(report)

    # 解锁骨架
    arm.lock_location = [False, False, False]
    arm.lock_scale = [False, False, False]
    # 优化骨架显示
    arm.data.display_type = "STICK"
    arm.display_type = "BOUNDS"
    arm.show_in_front = True
    # 取消静置骨架和设置镜像
    arm.data.pose_position = "POSE"
    arm.data.relation_line_position = "HEAD"
    arm.data.use_mirror_x = True
    arm.pose.use_mirror_x = True

    # 取消所有编辑骨骼的相连(edit_bone只有在编辑模式才能获取到,否则只能获取到空列表)
    select_obj(arm)
    set_mode("EDIT")
    for edit_bone in arm.data.edit_bones:
        edit_bone.use_connect = False
    set_mode("OBJECT")

    # 解锁所有姿势骨骼锁定
    for bone in arm.pose.bones:
        bone.lock_location = [False, False, False]

    # 优化修改器显示
    for obj in get_objs():
        for modifier in obj.modifiers:
            modifier.show_on_cage = True
            modifier.show_in_editmode = True
            modifier.show_expanded = False

    # 选中骨架(左上角会显示骨架名),然后隐藏
    select_obj(arm)
    hide_obj(arm)


if __name__ == "__main__":
    model_path = sys.argv[sys.argv.index("--") + 1]
    load_3d_model(model_path)
