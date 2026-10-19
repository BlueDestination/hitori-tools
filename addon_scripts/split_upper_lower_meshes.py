"""拆分上下双状态网格: 给支持上下状态的连体服装一次生成 4 个网格

背景: 游戏里的连体服装其实是 1 件, 由上下两个网格控制。上下连接处必须完全重合,
否则游戏里会断开; 半脱状态由 `.001` 后缀的网格实现, 连接处在切换状态前后也要保持不动。

用法: 选中 cloth_top 或 cloth_bra (可多选) -> 服装工具 -> 拆分上下双状态网格
要求(每个网格):
    1. 名字是全穿状态的 cloth_top / cloth_bra (不要带 .001);
    2. 有 top_bot_edge 顶点组, 组内顶点通过组内的边连成一体(允许半圆 / 开放等非环状切面);
    3. 有 top_part / bot_part 顶点组之一(标记切面以外的上半或下半部分, 有一个就够),
       且存在的顶点组必须包含 top_bot_edge 的全部顶点。
结果(每个网格 4 个):
    cloth_top     -> cloth_top_top    (上半) + cloth_top_bot    (下半)
    cloth_top.001 -> cloth_top_top.001(上半) + cloth_top_bot.001(下半)
    cloth_bra 同理。带 .001 的两个是复制出来的, 半脱状态的形态要自己改。
并给两个上半网格添加数据传递修改器(目标为对应下半网格, 顶点组 top_bot_edge, 只传递法向),
四个新网格都会开启 Auto Smooth 以让法向传递生效。
四个新网格的 top_bot_edge 顶点会在编辑模式里隐藏(避免误编辑), Alt+H 可取消隐藏。
原网格会先按"备份物体"的方式备份到 bak 集合, 再删除。
"""

import bmesh
import bpy
import numpy as np

from hitori_addon.error import ObjectError
from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.obj import copy_obj, select_obj, select_objs, set_mode
from hitori_addon.run import run_addon_script

TOP_BOT_EDGE_VG_NAME = "top_bot_edge"
TOP_PART_VG_NAME = "top_part"
BOT_PART_VG_NAME = "bot_part"
HALF_OFF_SUFFIX = ".001"
CONNECTED_CLOTH_BASES = ("cloth_top", "cloth_bra")
TITLE = "拆分上下双状态网格"


def get_vg_vertex_indices(obj, vg_name):
    """取顶点组内权重非零的顶点索引(升序)"""
    vg = obj.vertex_groups.get(vg_name)
    if vg is None:
        raise ObjectError(obj, f"没有顶点组 {vg_name}")

    group_index = vg.index
    indices = [
        vertex.index
        for vertex in obj.data.vertices
        if any(g.group == group_index and g.weight > 0 for g in vertex.groups)
    ]
    if not indices:
        raise ObjectError(obj, f"顶点组 {vg_name} 为空")

    return indices


def get_edges(obj):
    edges = obj.data.edges
    edges_arr = np.empty((len(edges), 2), dtype=np.int64)
    edges.foreach_get("vertices", edges_arr.ravel())
    return edges_arr.tolist()


def check_connected(obj, ring_indices, edges):
    """检查组内顶点是否通过组内的边连成一体(允许半圆 / 开放等非环状切面)"""
    ring_set = set(ring_indices)
    neighbors = {index: [] for index in ring_indices}

    for a, b in edges:
        if a in ring_set and b in ring_set:
            neighbors[a].append(b)
            neighbors[b].append(a)

    start = ring_indices[0]
    visited = {start}
    stack = [start]
    while stack:
        for neighbor in neighbors[stack.pop()]:
            if neighbor not in visited:
                visited.add(neighbor)
                stack.append(neighbor)

    if len(visited) != len(ring_indices):
        raise ObjectError(obj, f"顶点组 {TOP_BOT_EDGE_VG_NAME} 的顶点未相连")


def get_optional_vg_indices(obj, vg_name):
    """顶点组不存在时返回 None"""
    if obj.vertex_groups.get(vg_name) is None:
        return None
    return get_vg_vertex_indices(obj, vg_name)


def get_top_bottom_part_indices(obj, ring_indices):
    """按 top_part / bot_part 顶点组取上下两部分顶点索引, 环上顶点两块都要, 且要求这两个组包含整个环"""
    ring_set = set(ring_indices)
    all_set = set(range(len(obj.data.vertices)))
    non_ring_set = all_set - ring_set

    top_part = get_optional_vg_indices(obj, TOP_PART_VG_NAME)
    bot_part = get_optional_vg_indices(obj, BOT_PART_VG_NAME)
    if top_part is None and bot_part is None:
        raise ObjectError(
            obj,
            f"需要顶点组 {TOP_PART_VG_NAME} 或 {BOT_PART_VG_NAME} 之一来标记上下部分",
        )

    for vg_name, part in ((TOP_PART_VG_NAME, top_part), (BOT_PART_VG_NAME, bot_part)):
        if part is not None and not ring_set <= set(part):
            missing = len(ring_set - set(part))
            raise ObjectError(
                obj,
                f"顶点组 {vg_name} 应包含全部 {TOP_BOT_EDGE_VG_NAME} 顶点(缺少 {missing} 个)",
            )

    if top_part is not None and bot_part is not None:
        upper = set(top_part)
        lower = set(bot_part)
        overlap = upper & lower
        if overlap != ring_set:
            raise ObjectError(
                obj,
                f"{TOP_PART_VG_NAME} 与 {BOT_PART_VG_NAME} 只应在 {TOP_BOT_EDGE_VG_NAME} 上重叠"
                f"(实际重叠 {len(overlap)} 个, 环上 {len(ring_set)} 个)",
            )
        uncovered = all_set - upper - lower
        if uncovered:
            raise ObjectError(
                obj,
                f"{TOP_PART_VG_NAME} 与 {BOT_PART_VG_NAME} 未覆盖全部顶点(缺少 {len(uncovered)} 个)",
            )
    elif top_part is not None:
        upper = set(top_part)
        lower = ring_set | (non_ring_set - upper)
    else:
        lower = set(bot_part)
        upper = ring_set | (non_ring_set - lower)

    return sorted(upper), sorted(lower)


def keep_only_vertices(obj, keep_indices):
    """删除 keep_indices 之外的顶点(通过编辑模式删除以保留形态键 / 顶点组)"""
    set_mode("OBJECT")
    select_obj(obj)
    set_mode("EDIT")

    keep_set = set(keep_indices)
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.index_update()
    # delete 删除的是选中顶点, 因此选中要删掉的那些
    for vert in bm.verts:
        vert.select = vert.index not in keep_set
    bmesh.update_edit_mesh(obj.data)

    bpy.ops.mesh.delete(type="VERT")
    set_mode("OBJECT")


def add_normal_transfer(top_obj, bottom_obj):
    """给上半网格添加数据传递修改器, 从下半网格的环上顶点传递法向, 消除接缝处的明暗差"""
    modifier = top_obj.modifiers.new(name="DataTransfer", type="DATA_TRANSFER")
    modifier.object = bottom_obj
    modifier.vertex_group = TOP_BOT_EDGE_VG_NAME
    modifier.use_loop_data = True
    modifier.data_types_loops = {"CUSTOM_NORMAL"}
    modifier.loop_mapping = "NEAREST_POLYNOR"


def hide_ring_vertices(obj):
    """在编辑模式里隐藏 top_bot_edge 顶点(只隐藏顶点, 不动面), 避免接缝被误编辑"""
    ring_indices = get_vg_vertex_indices(obj, TOP_BOT_EDGE_VG_NAME)
    flags = np.zeros(len(obj.data.vertices), dtype=bool)
    flags[ring_indices] = True
    obj.data.vertices.foreach_set("hide", flags)
    obj.data.update()


def get_supported_objs():
    objs = selected_meshes()
    valid_names = " 或 ".join(CONNECTED_CLOTH_BASES)
    if not objs:
        raise ObjectError(objs, f"请选中支持上下状态的全穿网格: {valid_names}")

    invalid = [obj for obj in objs if obj.name not in CONNECTED_CLOTH_BASES]
    if invalid:
        raise ObjectError(
            invalid,
            f"只支持全穿状态的连体网格 {valid_names}, 不要选半脱的 {HALF_OFF_SUFFIX} 网格",
        )

    return objs


def get_split_names(base_name):
    """全穿 / 半脱两套上下网格名"""
    return [
        (f"{base_name}_top{suffix}", f"{base_name}_bot{suffix}")
        for suffix in ("", HALF_OFF_SUFFIX)
    ]


def get_split_plan(obj):
    """校验一个网格并算出上下顶点索引与新网格名"""
    ring_indices = get_vg_vertex_indices(obj, TOP_BOT_EDGE_VG_NAME)
    check_connected(obj, ring_indices, get_edges(obj))
    upper_indices, lower_indices = get_top_bottom_part_indices(obj, ring_indices)

    names = get_split_names(obj.name)
    exist_names = [
        name for pair in names for name in pair if bpy.data.objects.get(name)
    ]
    if exist_names:
        raise ObjectError(
            obj, f"网格 {', '.join(exist_names)} 已存在, 请先删除或改名"
        )

    return upper_indices, lower_indices, names


def split_one(obj, plan):
    """拆出一个网格的全穿 / 半脱各上下两块, 返回 (全穿上, 全穿下, 半脱上, 半脱下)"""
    upper_indices, lower_indices, names = plan
    (top_name, bottom_name), (half_top_name, half_bottom_name) = names

    top_obj = copy_obj(obj, name=top_name)
    bottom_obj = copy_obj(obj, name=bottom_name)
    keep_only_vertices(top_obj, upper_indices)
    keep_only_vertices(bottom_obj, lower_indices)

    # 半脱状态先复制全穿状态, 形态自己改
    half_top_obj = copy_obj(top_obj, name=half_top_name)
    half_bottom_obj = copy_obj(bottom_obj, name=half_bottom_name)

    pairs = ((top_obj, bottom_obj), (half_top_obj, half_bottom_obj))
    for pair_top_obj, pair_bottom_obj in pairs:
        # 数据传递自定义法向需要网格开启 Auto Smooth
        pair_top_obj.data.use_auto_smooth = True
        pair_bottom_obj.data.use_auto_smooth = True
        add_normal_transfer(pair_top_obj, pair_bottom_obj)

    new_objs = [top_obj, bottom_obj, half_top_obj, half_bottom_obj]
    for new_obj in new_objs:
        hide_ring_vertices(new_obj)

    return new_objs


def main():
    set_mode("OBJECT")

    objs = get_supported_objs()
    # 先全部校验, 避免建了一半才发现后面的网格有问题
    plans = {obj.name: get_split_plan(obj) for obj in objs}

    new_objs = []
    for obj in objs:
        new_objs += split_one(obj, plans[obj.name])

    # 备份原网格后删除, 并选中新网格
    set_mode("OBJECT")
    select_objs(objs)
    run_addon_script("backup_objects.py")
    for obj in objs:
        bpy.data.objects.remove(obj)

    select_objs(new_objs)

    lines = [f"共生成 {len(new_objs)} 个网格"]
    lines += [new_obj.name for new_obj in new_objs]
    lines += [
        "",
        f"带 {HALF_OFF_SUFFIX} 的网格的形态要自己改",
        f"{TOP_BOT_EDGE_VG_NAME} 顶点已在编辑模式中隐藏(避免误编辑), Alt+H 可取消隐藏",
    ]
    message_box("\n".join(lines), title=TITLE)


if __name__ == "__main__":
    main()
