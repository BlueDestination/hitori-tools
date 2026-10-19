"""UV 层处理

同一次导入里, 不同网格可能把有效 UV 放在不同名字的层里 (例如有的在 `UVMap`, 有的在 `UV 맵`),
另一层在这些面上全是 (0,0)。Blender 3.6 的图片纹理节点没有 UV Map 输入, 只用 active 层,
所以一旦把网格合并成一个物体, 那些面就只剩一个 active 层可用, 整片退化成采样贴图同一个像素
(平展预览里表现为一整块纯白 / 颜色异常)。

`unify_uv_layers` 按面挑出有数据的那一层, 合并进一层 `UVMap` 并设为 active,
删掉全 (0,0) 的空层, 这样合并物体时所有网格都能按层名对齐; 对已经合并好的物体也能直接用。
重命名只改层名, 本仓库的材质都没有按名字引用 UV 层, 不受影响。
"""

import numpy as np
from bpy.types import Object

ZERO_TOL = 1e-6
TARGET_NAME = "UVMap"


def get_uv_arr(layer, loop_count: int) -> np.ndarray:
    arr = np.empty(loop_count * 2, dtype=np.float32)
    layer.data.foreach_get("uv", arr)
    return arr.reshape(-1, 2)


def get_zero_loops(uv_arr: np.ndarray) -> np.ndarray:
    return np.all(np.abs(uv_arr) < ZERO_TOL, axis=1)


def get_degenerate_faces(
    zero_loops: np.ndarray, loop_face: np.ndarray, loop_total: np.ndarray
) -> np.ndarray:
    """整个面的每个 loop 的 UV 都是 (0,0) 时, 这个面算退化(该层没有它的数据)"""
    weight = zero_loops.astype(np.float64)
    return np.bincount(loop_face, weights=weight, minlength=len(loop_total)) >= loop_total


def unify_uv_layers(obj: Object, target_name: str = TARGET_NAME) -> str | None:
    """把各 UV 层里有效的面合并成一层 `UVMap`, 返回一行报告; 不需要处理时返回 None"""
    mesh = obj.data
    loop_count = len(mesh.loops)
    poly_count = len(mesh.polygons)
    if not loop_count or not poly_count:
        return None
    layers = list(mesh.uv_layers)
    if not layers:
        return None
    active = mesh.uv_layers.active or layers[0]
    active_index = layers.index(active)

    loop_total = np.empty(poly_count, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", loop_total)
    loop_face = np.repeat(np.arange(poly_count), loop_total)
    uvs = [get_uv_arr(layer, loop_count) for layer in layers]
    zero_loops = [get_zero_loops(uv) for uv in uvs]
    degenerate = [
        get_degenerate_faces(zero, loop_face, loop_total)
        for zero in zero_loops
    ]

    # 按面选源: active 层有数据就用它, 否则取第一个有数据的层
    source = np.full(poly_count, active_index, dtype=np.int32)
    for index in range(len(layers)):
        if index == active_index:
            continue
        take = (source == active_index) & degenerate[active_index] & ~degenerate[index]
        source[take] = index
    source_loops = source[loop_face]
    fixed = int((source != active_index).sum())

    empty_layers = [
        layer for layer, zero in zip(layers, zero_loops) if bool(zero.all())
    ]
    empty_names = [layer.name for layer in empty_layers if layer is not active]
    if not fixed and active.name == target_name and not empty_layers:
        return None

    merged = uvs[active_index].copy()
    used_names = [active.name]
    for index in range(len(layers)):
        if index == active_index:
            continue
        mask = source_loops == index
        if not mask.any():
            continue
        merged[mask] = uvs[index][mask]
        used_names.append(layers[index].name)

    # 先把合并结果写回 active 层 (active 自己可能是空层, 所以先写再删)
    active.data.foreach_set("uv", merged.reshape(-1))

    notes = []
    # 目标层名要跳网格一致(合并时按层名对齐), 同名层先让开
    if active.name != target_name:
        occupied = mesh.uv_layers.get(target_name)
        if occupied is not None:
            if occupied in layers and bool(zero_loops[layers.index(occupied)].all()):
                mesh.uv_layers.remove(occupied)
                notes.append(f"删除空的 {target_name}")
            else:
                occupied.name = f"{target_name}_bak"
                notes.append(f"旧 {target_name} 改名 {target_name}_bak")
        active.name = target_name
        notes.append(f"层名 -> {target_name}")

    # 其余全 (0,0) 的空层没有数据, 删掉(否则合并时会把 (0,0) 带回来)
    for name in empty_names:
        layer = mesh.uv_layers.get(name)
        if layer is not None and layer.name != target_name:
            mesh.uv_layers.remove(layer)
            notes.append(f"删除空层 {name}")

    layer = mesh.uv_layers[target_name]
    layer.active = True
    layer.active_render = True

    parts = [f"{obj.name}:"]
    if fixed:
        parts.append(f"修补 {fixed} 面, UV 来源 {' + '.join(used_names)}")
    parts += notes
    return " ".join(parts)
