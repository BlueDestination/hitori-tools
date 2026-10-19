"""沿 Y 轴正投影: 把源网格正视图里的颜色投影到目标网格的 uv 布局上

正视图里颜色只与世界坐标 (x, z) 有关, 与 y 无关, 所以目标网格表面点 (x, z) 在源网格正视图里的颜色
就是投影结果. 与源网格有没有厚度 / 有几层结构无关, 不需要缩裹, 也不需要烘焙.
源网格可以带多个材质槽, 按三角形所属材质分别取贴图; 源贴图带 alpha 时透明处会一起投影过来.
"""

from collections.abc import Sequence

import bpy
import numpy as np

from hitori_addon.error import ObjectError

# 源网格 (x, z) 查找图相对源贴图的分辨率倍数: 比源贴图细一点, 减少查表取整带来的偏差
MAP_SUPERSAMPLE: float = 1.5
# 查找图的像素数上限: 太细只是白吃内存
MAX_MAP_PIXELS: int = 6_000_000
# 取不到源贴图尺寸(源网格没有贴图)时的兜底分辨率
FALLBACK_SIZE: int = 512


def get_mesh_data(obj: bpy.types.Object) -> dict[str, np.ndarray]:
    """取物体求值后(带修改器 / 形态键)的网格数据, 与视图 / 渲染里看到的一致

    返回三角形(每个是 3 个 loop 序号), 及每个 loop 的 uv / 世界坐标 / 材质槽序号
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        uv_layer = mesh.uv_layers.active
        if uv_layer is None:
            raise ObjectError(obj, "网格上没有 uv")

        matrix = np.array(evaluated.matrix_world)
        coordinates = np.empty(len(mesh.vertices) * 3, "f")
        mesh.vertices.foreach_get("co", coordinates)
        world = coordinates.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]

        indices = np.empty(len(mesh.loops), "i")
        mesh.loops.foreach_get("vertex_index", indices)

        uv = np.empty(len(mesh.loops) * 2, "f")
        uv_layer.data.foreach_get("uv", uv)

        slots = np.empty(len(mesh.loops), "f")
        triangles = []
        for polygon in mesh.polygons:
            loops = list(polygon.loop_indices)
            slots[loops] = polygon.material_index
            if len(loops) == 3:
                triangles.append(loops)
            else:
                # 多边形按扇形拆成三角形
                for index in range(1, len(loops) - 1):
                    triangles.append([loops[0], loops[index], loops[index + 1]])
    finally:
        evaluated.to_mesh_clear()

    return {
        "triangles": triangles,
        "uv": uv.reshape(-1, 2),
        "world": world[indices],
        "slots": slots,
    }


def rasterize(
    triangles: Sequence[Sequence[int]],
    points: np.ndarray,
    values: np.ndarray,
    size: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """把三角形从 points 空间栅格化到 size 空间, 逐像素线性插值 values

    points / values 都按 loop 给, 每个三角形用自己的 3 个 loop.
    一个像素被多个三角形覆盖时取 y (values[..., 2]) 最小的那个, 与正视图里看到的一致.
    """
    width, height = size
    result = np.zeros((height, width, values.shape[-1]), "f")
    covered = np.zeros((height, width), bool)
    depth = np.full((height, width), np.inf, "f")

    for triangle in triangles:
        triangle_points = points[triangle]
        left = max(0, int(np.floor(triangle_points[:, 0].min())))
        right = min(width, int(np.ceil(triangle_points[:, 0].max())))
        top = max(0, int(np.floor(triangle_points[:, 1].min())))
        bottom = min(height, int(np.ceil(triangle_points[:, 1].max())))
        if right <= left or bottom <= top:
            continue

        matrix = np.array(
            [
                triangle_points[1] - triangle_points[0],
                triangle_points[2] - triangle_points[0],
            ]
        ).T
        if abs(np.linalg.det(matrix)) < 1e-12:
            continue

        grid_x, grid_y = np.meshgrid(
            np.arange(left, right) + 0.5, np.arange(top, bottom) + 0.5
        )
        inverse = np.linalg.inv(matrix)
        offset_x = grid_x - triangle_points[0, 0]
        offset_y = grid_y - triangle_points[0, 1]
        first = inverse[0, 0] * offset_x + inverse[0, 1] * offset_y
        second = inverse[1, 0] * offset_x + inverse[1, 1] * offset_y
        weight = np.stack([1 - first - second, first, second])
        inside = (weight > -1e-6).all(axis=0)

        interpolated = np.moveaxis(
            (values[triangle][:, :, None, None] * weight[:, None, :, :]).sum(axis=0),
            0,
            -1,
        )
        block = result[top:bottom, left:right]
        block_depth = depth[top:bottom, left:right]
        front = inside & (interpolated[..., 2] < block_depth)
        block[front] = interpolated[front]
        block_depth[front] = interpolated[..., 2][front]
        covered[top:bottom, left:right] |= inside

    return result, covered


def build_source_map(
    data: dict[str, np.ndarray],
    images: Sequence[bpy.types.Image | None],
    fallback_size: int = FALLBACK_SIZE,
) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float, float]]:
    """源网格: 世界 (x, z) -> 源网格 uv 的查找图, 供目标贴图的每个 texel 取色

    分辨率取源贴图分辨率的 MAP_SUPERSAMPLE 倍, 总量用 MAX_MAP_PIXELS 兜底
    """
    xz = data["world"][:, [0, 2]]
    x_min, x_max = float(xz[:, 0].min()), float(xz[:, 0].max())
    z_min, z_max = float(xz[:, 1].min()), float(xz[:, 1].max())
    extent = max(x_max - x_min, z_max - z_min)
    if extent <= 0:
        raise ObjectError([], "源网格在正视图里没有面积")

    area = max((x_max - x_min) * (z_max - z_min), 1e-12)
    texels = (
        max([max(image.size) for image in images if image] or [fallback_size])
        * MAP_SUPERSAMPLE
    )
    resolution = max(extent / texels, np.sqrt(area / MAX_MAP_PIXELS))

    width = int(np.ceil((x_max - x_min) / resolution)) + 1
    height = int(np.ceil((z_max - z_min) / resolution)) + 1
    points = np.stack(
        [(xz[:, 0] - x_min) / resolution, (z_max - xz[:, 1]) / resolution], axis=-1
    )
    # uv + 世界 y(用于深度比较) + 材质槽序号
    values = np.concatenate(
        [data["uv"], data["world"][:, [1]], data["slots"][:, None]], axis=-1
    )

    lookup, covered = rasterize(data["triangles"], points, values, (width, height))
    print(
        f"源网格查找图 {width}x{height} ({resolution * 1000:.3f}mm/像素), 覆盖 {covered.mean() * 100:.1f}%"
    )
    return lookup, covered, (x_min, x_max, z_min, z_max)


def build_target_map(
    data: dict[str, np.ndarray], size: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray]:
    """目标网格: 目标贴图的每个 texel -> 世界坐标"""
    width, height = size
    points = data["uv"] * np.array([width, height], "f")
    points[:, 1] = height - points[:, 1]

    mapping, covered = rasterize(data["triangles"], points, data["world"], size)
    print(f"模板贴图岛覆盖 {covered.mean() * 100:.1f}%")
    return mapping, covered


def get_image_pixels(image: bpy.types.Image) -> tuple[np.ndarray, float]:
    """取图片像素(RGBA, 0-1, 从上到下的行序)和最小 alpha"""
    width, height = image.size
    values = np.empty(width * height * 4, "f")
    image.pixels.foreach_get(values)
    return values.reshape(height, width, 4)[::-1], float(values[3::4].min())


def sample_pixels(pixels: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """按 uv 双线性采样 RGBA(alpha 预乘, 避免透明边缘发黑)"""
    height, width = pixels.shape[:2]
    position_x = np.clip(uv[:, 0], 0, 1) * (width - 1)
    position_y = (1 - np.clip(uv[:, 1], 0, 1)) * (height - 1)

    x_low, y_low = np.floor(position_x).astype(int), np.floor(position_y).astype(int)
    x_high, y_high = np.minimum(x_low + 1, width - 1), np.minimum(y_low + 1, height - 1)
    fraction_x, fraction_y = (
        (position_x - x_low)[:, None],
        (position_y - y_low)[:, None],
    )

    alpha = pixels[..., 3:4]
    color = pixels[..., :3] * alpha

    def blend(values):
        return (
            values[y_low, x_low] * (1 - fraction_x) + values[y_low, x_high] * fraction_x
        ) * (1 - fraction_y) + (
            values[y_high, x_low] * (1 - fraction_x)
            + values[y_high, x_high] * fraction_x
        ) * fraction_y

    result_alpha = blend(alpha)[:, 0]
    result_color = blend(color)
    return np.concatenate(
        [
            result_color / np.maximum(result_alpha, 1e-6)[:, None],
            result_alpha[:, None],
        ],
        axis=-1,
    )


def project(
    src_obj: bpy.types.Object,
    target_obj: bpy.types.Object,
    size: tuple[int, int],
    images: Sequence[bpy.types.Image | None],
    fallback_size: int = FALLBACK_SIZE,
) -> tuple[np.ndarray, float]:
    """把源网格在正视图里的颜色投影进目标网格的 uv 布局

    返回目标贴图像素(从上到下的行序)和目标贴图 uv 岛被投影覆盖的比例
    """
    lookup, lookup_covered, (x_min, x_max, z_min, z_max) = build_source_map(
        get_mesh_data(src_obj),
        images,
        fallback_size,
    )
    mapping, target_covered = build_target_map(get_mesh_data(target_obj), size)
    map_height, map_width = lookup_covered.shape

    column = np.rint(
        (mapping[..., 0] - x_min) / (x_max - x_min) * (map_width - 1)
    ).astype(int)
    row = np.rint(
        (z_max - mapping[..., 2]) / (z_max - z_min) * (map_height - 1)
    ).astype(int)
    inside = (
        target_covered
        & (column >= 0)
        & (column < map_width)
        & (row >= 0)
        & (row < map_height)
    )
    column, row = np.clip(column, 0, map_width - 1), np.clip(row, 0, map_height - 1)
    inside &= lookup_covered[row, column]

    uv = lookup[row, column, 0:2]
    slots = np.rint(lookup[row, column, 3]).astype(int)

    pixels = np.zeros((size[1], size[0], 4), "f")
    opaque_images: list[str] = []
    for index, image in enumerate(images):
        if image is None:
            continue

        take = inside & (slots == index)
        if not take.any():
            continue

        source_pixels, min_alpha = get_image_pixels(image)
        if min_alpha >= 0.99:
            opaque_images.append(image.name)
        pixels[take] = sample_pixels(source_pixels, uv[take])

    coverage = inside.sum() / max(target_covered.sum(), 1)
    print(
        f"投影覆盖模板贴图岛 {inside.sum()} / {target_covered.sum()} texel ({coverage * 100:.1f}%)"
    )
    if opaque_images:
        print(
            f"注意: 源贴图 {' / '.join(sorted(set(opaque_images)))} 没有透明通道, 背景会一起投影进来"
        )
    return pixels, coverage
