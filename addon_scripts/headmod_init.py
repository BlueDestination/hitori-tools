import bpy
import numpy as np

from hitori_addon.error import ObjectError
from hitori_addon.game_data import get_kk_neck_vertex_positions
from hitori_addon.math import vecs_apply_mat
from hitori_addon.mesh import (
    get_vertex_indices,
    selected_vertex_indices_arr,
    selected_vertices,
    set_armature_modifier,
)
from hitori_addon.obj import (
    apply_transform,
    clear_parent,
    copy_obj,
    create_obj,
    get_obj,
    hide_obj,
    move_obj,
    select_obj,
    set_mode,
)
from hitori_addon.path import get_blend_file_stem
from hitori_addon.template_link import HEAD_NAME


def main():
    chara_name = get_blend_file_stem()

    old_obj = bpy.context.object
    obj = copy_obj(old_obj, name=chara_name + "_headmod")
    hide_obj(old_obj)
    select_obj(obj)

    neck_vertices = selected_vertices(obj)
    neck_vertex_indices = selected_vertex_indices_arr(obj).tolist()
    not_neck_vertex_indices = list(
        set(get_vertex_indices(obj)) - set(neck_vertex_indices)
    )

    if len(neck_vertex_indices) != 26:
        raise ObjectError(old_obj, "请选中头部脖子接缝的26个顶点后重试")

    if obj.modifiers:
        raise ObjectError(old_obj, "头部网格存在修改器,请应用掉或删除掉后重试")

    # 存储脖子切面的顶点组
    obj_vgs = obj.vertex_groups
    set_mode("OBJECT")
    neck_vg = obj_vgs.new(name="neck_vg")
    neck_vg.add(neck_vertex_indices, 1, "REPLACE")

    # 从kk_head传递切面法线数据
    modifier = obj.modifiers.new(name="DataTransfer", type="DATA_TRANSFER")
    modifier.vertex_group = neck_vg.name
    modifier.object = get_obj(HEAD_NAME)
    modifier.data_types_loops = {"CUSTOM_NORMAL"}
    modifier.loop_mapping = "NEAREST_POLYNOR"
    set_mode("OBJECT")
    bpy.ops.object.modifier_apply(modifier=modifier.name)

    # 从脖子切面扩选两圈赋予neck材质并置顶
    set_mode("EDIT")
    material = bpy.data.materials.new(name="neck")
    material.use_nodes = True
    obj.data.materials.append(material)
    obj.active_material_index = len(obj.material_slots) - 1
    bpy.ops.mesh.select_more()
    bpy.ops.mesh.select_more()
    bpy.ops.object.material_slot_assign()
    for i in range(len(obj.material_slots)):
        bpy.ops.object.material_slot_move(direction="UP")

    # 以下开始对齐头模位置
    set_mode("OBJECT")
    select_obj(obj)

    neck_coordinates_local = [vertex.co for vertex in neck_vertices]
    neck_vertex_positions_arr = vecs_apply_mat(neck_coordinates_local, obj.matrix_world)

    kk_neck_vertex_positions = get_kk_neck_vertex_positions()
    neck_vertex_positions_mean = np.mean(neck_vertex_positions_arr, axis=0)
    kk_neck_vertex_positions_mean = np.mean(kk_neck_vertex_positions, axis=0)

    # 头部整体移动
    headmod_move_offset = kk_neck_vertex_positions_mean - neck_vertex_positions_mean
    move_obj(obj, headmod_move_offset)
    neck_vertex_positions_arr += headmod_move_offset

    # 所有脖子接缝顶点移动
    nearest_kk_neck_positions_world = []
    for neck_vertex_position in neck_vertex_positions_arr:
        distances = np.linalg.norm(
            kk_neck_vertex_positions - neck_vertex_position, axis=1
        )
        nearest_kk_neck_position = kk_neck_vertex_positions[np.argmin(distances)]
        nearest_kk_neck_positions_world.append(nearest_kk_neck_position)

    nearest_kk_neck_positions_arr_local = vecs_apply_mat(
        nearest_kk_neck_positions_world, obj.matrix_world
    )
    for vertex, target_local_co in zip(
        neck_vertices, nearest_kk_neck_positions_arr_local
    ):
        vertex.co = target_local_co

    # 设置两个KK头骨顶点组
    obj_vgs.new(name="cf_J_FaceRoot").add(neck_vertex_indices, 1, "REPLACE")
    obj_vgs.new(name="cf_J_FaceBase").add(not_neck_vertex_indices, 1, "REPLACE")

    # 创建两个KK头骨构成的骨架
    set_mode("OBJECT")
    arm_face_name = "Armature_face"
    arm_face = create_obj(arm_face_name, "ARMATURE")

    # 创建两个KK头骨
    select_obj(arm_face)
    set_mode("EDIT")
    arm_face_editbones = arm_face.data.edit_bones

    bone1 = arm_face_editbones.new("cf_J_FaceRoot")
    bone1.head, bone1.tail = (0, 0, 0), (0, 0, 0.0208806)

    bone2 = arm_face_editbones.new("cf_J_FaceBase")
    bone2.use_connect = False
    bone2.head, bone2.tail = (0, -0.006, 0.02), (0, -0.006, 0.0626318)
    bone2.parent = bone1

    # 设置头模父级和修改器
    set_mode("OBJECT")

    clear_parent(obj)
    apply_transform(obj)

    clear_parent(arm_face)
    apply_transform(arm_face)

    obj.parent = arm_face
    set_armature_modifier(obj, arm_face)

    # 优化显示
    hide_obj(arm_face)
    select_obj(obj)
    bpy.ops.view3d.view_selected()
    set_mode("EDIT")


if __name__ == "__main__":
    main()
