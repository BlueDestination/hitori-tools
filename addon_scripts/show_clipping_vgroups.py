"""给选中的网格标记穿模顶点组 _clipping: 顶点在官方紧身衣内部就算穿模

用法: 选中一个或多个网格 -> 常用 -> 显示穿模顶点组
没有选中网格时只处理当前激活的网格 (紧身衣本身会被跳过), 结束后选中全部被处理的网格
并进入权重模式。
"""

import bpy

from hitori_addon.error import ObjectError
from hitori_addon.mesh import apply_meshes, get_clipping_vertex_indices, selected_meshes
from hitori_addon.obj import (
    copy_objs,
    delete_obj,
    get_obj,
    select_objs,
    set_matrix,
    set_mode,
)
from hitori_addon.template_link import BODYTIGHT_NAME

VG_NAME = "_clipping"


def get_target_objs(bodytight) -> list:
    """要标记的网格: 优先选中的, 没选中就用激活的, 紧身衣本身不算"""
    objs = [obj for obj in selected_meshes() if obj is not bodytight]
    if objs:
        return objs

    active_obj = bpy.context.active_object
    if active_obj and active_obj.type == "MESH" and active_obj is not bodytight:
        return [active_obj]
    return []


def set_clipping_vgroup(obj, clipping_vertex_indices: list[int]):
    ## 如果顶点组重复则删除后新建
    obj_vgs = obj.vertex_groups
    existing_vg = obj_vgs.get(VG_NAME)
    if existing_vg:
        obj_vgs.remove(existing_vg)

    new_vg = obj_vgs.new(name=VG_NAME)
    new_vg.add(clipping_vertex_indices, 1, "REPLACE")
    obj_vgs.active = new_vg


def main():
    set_mode("OBJECT")
    bodytight = get_obj(BODYTIGHT_NAME)
    if bodytight is None:
        raise ObjectError([], f"场景里没有 {BODYTIGHT_NAME} 网格, 请先显示官方身体")

    objs = get_target_objs(bodytight)
    if not objs:
        raise ObjectError([], "请先选中要检查穿模的网格")

    # 复制一份应用形状后的网格, 统一到紧身衣坐标系再判断(用完即删), 原网格只用来上顶点组
    applied_objs = copy_objs(objs)
    apply_meshes(applied_objs)

    # 如果想要离皮肤贴的比较近的地方也标记上，可以在复制前对原网格应用变换 (原理暂不明)
    clipping_indices_list = []
    for applied_obj in applied_objs:
        set_matrix(applied_obj, bodytight.matrix_world)
        clipping_indices_list.append(
            get_clipping_vertex_indices(applied_obj, bodytight)
        )

    for applied_obj in applied_objs:
        delete_obj(applied_obj)

    for obj, clipping_vertex_indices in zip(objs, clipping_indices_list):
        set_clipping_vgroup(obj, clipping_vertex_indices)

    select_objs(objs)
    set_mode("WEIGHT_PAINT")


if __name__ == "__main__":
    main()
