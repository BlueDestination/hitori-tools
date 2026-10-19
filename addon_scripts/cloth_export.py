"""导出选中的服装 (服装智能更新调用, 不要单独运行)"""

from hitori_addon.arm import rest_arm
from hitori_addon.check import require_cloth_meshes
from hitori_addon.exporter import export_kk_fbx, sort_objs_internal_order
from hitori_addon.mesh import (
    apply_meshes,
    remove_unused_material_slot,
    selected_meshes,
    set_armature_modifier,
    transfer_weight,
)
from hitori_addon.obj import (
    clear_parent,
    get_obj,
    only_show_objs,
    set_mode,
    set_unity_matrix,
)
from hitori_addon.progress import Progress
from hitori_addon.template_link import (
    ARMATURE_NAME,
    BODYTIGHT_NAME,
    SKIP_TRANSFER_GROUP_NAME,
)

arm = get_obj(ARMATURE_NAME)
bodytight = get_obj(BODYTIGHT_NAME)
objs = selected_meshes()

# 如果有非服装网格则报错
require_cloth_meshes(objs)

# 提前应用所有服装和静置KK骨架
set_mode("OBJECT")
apply_meshes(objs)
rest_arm(arm)
# 清除网格无用材质槽
remove_unused_material_slot(objs)

for obj in Progress(objs):
    # 缺失或空组 = 整片传权重, 非空组 = 只传组外顶点 (构建脚本按需写这个组)
    has_skip_group = obj.vertex_groups.get(SKIP_TRANSFER_GROUP_NAME) is not None
    transfer_weight(
        obj,
        bodytight,
        SKIP_TRANSFER_GROUP_NAME if has_skip_group else None,
        invert_vg=has_skip_group,
    )

    # 清除父级和设置Unity坐标系
    clear_parent(obj)
    set_unity_matrix(obj)

    # 设置骨架修改器
    set_armature_modifier(obj, arm)

# 导出fbx
only_show_objs([arm] + objs)
sort_objs_internal_order(objs)
export_kk_fbx()
