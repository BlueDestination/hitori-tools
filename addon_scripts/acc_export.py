"""导出选中的饰品和对应饰品骨架 (饰品智能更新 / 注册饰品动骨调用, 不要单独运行)"""

import bpy
import numpy as np

from hitori_addon.arm import (
    apply_arm,
    create_parent_bone,
    delete_bones,
    get_bone_names,
    get_root_bones,
)
from hitori_addon.check import require_acc_meshes
from hitori_addon.const import KK_ACC_POSITIONS_ARR, KK_ACCS
from hitori_addon.error import ObjectError
from hitori_addon.exporter import export_kk_fbx, sort_objs_internal_order
from hitori_addon.mesh import (
    apply_meshes,
    remove_unused_material_slot,
    selected_meshes,
    set_armature_modifier,
)
from hitori_addon.obj import (
    apply_transform,
    clear_parent,
    copy_obj,
    only_show_objs,
    select_objs,
    set_acc_matrix,
    set_mode,
    set_unity_matrix,
)
from hitori_addon.path import get_blend_file_stem
from hitori_addon.progress import Progress
from hitori_addon.template import update_acc_csv_parents
from hitori_addon.vg import delete_empty_vgs, get_vg_names

accs = selected_meshes()
if not accs:
    raise ObjectError(accs, "没有选中的饰品")
first_acc = accs[0]
if not first_acc.parent:
    raise ObjectError(accs, "所选饰品没有父级骨架")

# 如果有非饰品网格则报错
require_acc_meshes(accs)

# 复制骨架和移动骨架前先应用所有饰品和用于复制的共用饰品骨架
set_mode("OBJECT")
apply_meshes(accs)
apply_arm(first_acc.parent)
# 清除网格无用材质槽
remove_unused_material_slot(accs)

acc_arms = []
# {饰品网格名: 游戏里的挂点名}, 导出后写进 zipmod 的饰品 csv
acc_parent_map = {}

for acc in Progress(accs):
    # 复制饰品骨架
    old_acc_arm = acc.parent
    if not old_acc_arm:
        raise ObjectError(acc, "所选饰品没有父级骨架")

    acc_arm = copy_obj(old_acc_arm, name=f"arm_{acc.name}")
    acc_arms.append(acc_arm)

    # 饰品和饰品骨架清除父级和应用变换
    for obj in (acc, acc_arm):
        clear_parent(obj)
        apply_transform(obj)

    # 设置饰品骨架修改器
    set_armature_modifier(acc, acc_arm)

    # 删除饰品骨架中的无用骨骼
    delete_empty_vgs(acc)
    valid_bones = get_vg_names(acc)
    all_bones = get_bone_names(acc_arm)
    invalid_bones = set(all_bones) - set(valid_bones)
    delete_bones(acc_arm, invalid_bones)

    ## 如果有多个根骨骼则创建唯一的根骨骼当做父级
    old_root_bones = get_root_bones(acc_arm)
    old_root_bones_count = len(old_root_bones)
    old_root_bone_names = [bone.name for bone in old_root_bones]

    if old_root_bones_count < 1:
        raise ObjectError(acc_arm, f"饰品骨架{acc_arm.name}没有骨骼")
    elif old_root_bones_count == 1:
        root_bone = old_root_bones[0]
    else:
        new_root_bone_name = f"arm_{acc.name}_root"
        root_bone = create_parent_bone(
            acc_arm, new_root_bone_name, old_root_bone_names, set_x_zero=True
        )

    # 存储根骨骼位置(左乘矩阵应用变换,不是右乘!)
    root_bone_position = acc_arm.matrix_world @ root_bone.head
    root_bone_position_arr = np.array(root_bone_position)

    # 计算距离最近的kk饰品挂点, 并把饰品变换到挂点原点(见 obj.get_inverse_acc_matrix)
    distances = np.linalg.norm(KK_ACC_POSITIONS_ARR - root_bone_position_arr, axis=1)
    nearest_kk_acc = KK_ACCS[np.argmin(distances)]
    acc_parent_map[acc.name] = nearest_kk_acc.parent

    ## 饰品和骨架施加挂点的逆变换, 再应用变换(即原点设置为挂点坐标系)
    for obj in acc, acc_arm:
        set_acc_matrix(obj, nearest_kk_acc)
        apply_transform(obj)

    # 将饰品原点设置为Unity坐标系
    set_unity_matrix(acc)

## 导出饰品和饰品骨架
accs_and_acc_arms = accs + acc_arms

only_show_objs(accs_and_acc_arms)
sort_objs_internal_order(accs_and_acc_arms)
export_kk_fbx(add_leaf_bones=True)

select_objs(accs_and_acc_arms)
# 无头导出没有3D视图, view_selected在无头模式下会报错
if not bpy.app.background:
    bpy.ops.view3d.view_selected()

# 父级以 csv 为准, 这里把 csv 里的 Parent 改成导出时选中的挂点(要重启游戏才生效)
update_acc_csv_parents(get_blend_file_stem(), acc_parent_map)
