"""把选中瞳孔的贴图写入 kk_hitomi 模板贴图, 新贴图保存到工程目录

运行会弹窗询问模式与选项, 取消弹窗则不做任何操作
二维复制: 取瞳孔网格 uv 外轮廓环围出的选区, 按物理尺寸缩放到模板贴图 uv 环的中心
缩放比例由两边网格的 uv 到世界坐标拟合算出, 让瞳孔在游戏里的尺寸和原模型一致
正交投影: 把瞳孔网格沿 Y 轴正交投影到模板贴图的 uv 布局上(原理同写入眼线贴图),
结果与外部模型正视图里看到的瞳孔一致, 源网格有没有厚度 / 几层结构都不影响, 不需要缩裹也不需要烘焙
复用时右眼镜像沿用上次的选择(记在模板物体上, 随工程保存)
脚本只做贴图处理: 不新建 / 不改动场景里的物体、相机和渲染设置; 模板材质只换贴图节点上的贴图
(材质里没有贴图节点时按原来的兜底逻辑新建一个)
写入后还会把贴图转成游戏颜色写进默认人物卡, 并让游戏重载该卡
"""

import tempfile
from pathlib import Path

import bpy
import numpy as np

from hitori_addon.card import (
    get_card_path,
    reload_kk_card,
    set_official_pupil_no_iris,
    set_pupil_overlay,
)
from hitori_addon.error import ObjectError
from hitori_addon.image import (
    backup_image_file,
    img_to_kk_color,
    mirror_image_horizontal,
    set_named_image,
)
from hitori_addon.material import (
    ensure_alpha_clip,
    get_source_image,
    get_texture_material_and_node,
    get_texture_node,
)
from hitori_addon.menu import message_box, register_and_invoke_menu, report_errors
from hitori_addon.mesh import selected_meshes
from hitori_addon.obj import get_obj
from hitori_addon.path import get_blend_file_dir, get_blend_file_stem
from hitori_addon.projection import get_image_pixels, project
from hitori_addon.template_link import HITOMI_NAME

TEMPLATE_NAME = HITOMI_NAME
TITLE = "写入瞳孔贴图"
IMAGE_NAME = "kk_hitomi"
IMG_SIZE = 512
# 上次用的右眼镜像选项记在模板物体上, 复用时不再弹窗就沿用它
MIRROR_STATE_KEY = "hitori_pupil_mirror"

MODE_PROPERTY = bpy.props.EnumProperty(
    name="模式",
    items=[
        ("复制", "二维复制", "取瞳孔贴图的 uv 选区按物理尺寸缩放到模板贴图(不烘焙)"),
        (
            "投影",
            "正交投影",
            "把瞳孔网格沿 Y 轴正交投影到模板贴图上, 与外部模型的正视图一致",
        ),
    ],
    default="投影",
)

MIRROR_PROPERTY = bpy.props.EnumProperty(
    name="右眼镜像",
    items=[
        ("否", "否", "左右眼用同一张贴图"),
        ("是", "是", "右眼用水平镜像的贴图"),
    ],
    default="否",
)

ROTATE_PROPERTY = bpy.props.FloatProperty(
    name="旋转角度(度)",
    description="瞳孔贴图绕瞳孔中心旋转的角度, 正值顺时针",
    default=0.0,
    soft_min=-180.0,
    soft_max=180.0,
)


def get_world_coords(obj):
    mesh = obj.data
    coords = np.empty(len(mesh.vertices) * 3, "f")
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    matrix = np.array(obj.matrix_world)
    return coords @ matrix[:3, :3].T + matrix[:3, 3]


def get_pupil_texture_node(pupil):
    for slot in pupil.material_slots:
        node = get_texture_node(slot.material)
        if node:
            return node

    raise ObjectError([pupil], "瞳孔网格的材质上没有连到基础色的贴图节点")


def get_uv_layer(obj, texture_node):
    """取贴图节点用的 uv 层, 节点没指定就用渲染 uv 层"""
    mesh = obj.data
    vector_input = texture_node.inputs.get("Vector", None)
    if vector_input and vector_input.is_linked:
        node = vector_input.links[0].from_node
        if node.type == "UVMAP":
            layer = mesh.uv_layers.get(node.uv_map)
            if layer:
                return layer

    layer = (
        next((layer for layer in mesh.uv_layers if layer.active_render), None)
        or mesh.uv_layers.active
    )
    if not layer:
        raise ObjectError([obj], "网格没有 uv 层")
    return layer


def get_boundary_rings(obj, uv_layer):
    """取网格外轮廓环, 每项为 (顶点序号列表, uv 数组)"""
    mesh = obj.data

    edge_counts = {}
    for polygon in mesh.polygons:
        vertices = list(polygon.vertices)
        for index, vertex in enumerate(vertices):
            other = vertices[(index + 1) % len(vertices)]
            edge = (min(vertex, other), max(vertex, other))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1

    border_edges = {edge for edge, count in edge_counts.items() if count == 1}

    uv_by_vertex = {}
    for loop in mesh.loops:
        uv_by_vertex.setdefault(loop.vertex_index, tuple(uv_layer.data[loop.index].uv))

    neighbors = {}
    for a, b in border_edges:
        neighbors.setdefault(a, []).append(b)
        neighbors.setdefault(b, []).append(a)

    rings = []
    remaining = set(border_edges)
    while remaining:
        start = min(remaining)[0]
        ring = [start]
        previous, current = None, start
        while True:
            step = next(
                (
                    vertex
                    for vertex in neighbors[current]
                    if vertex != previous
                    and (min(current, vertex), max(current, vertex)) in remaining
                ),
                None,
            )
            if step is None:
                break
            remaining.discard((min(current, step), max(current, step)))
            if step == start:
                break
            ring.append(step)
            previous, current = current, step
        if len(ring) >= 3:
            rings.append(
                (ring, np.array([uv_by_vertex[vertex] for vertex in ring], "f"))
            )
    return rings


def get_ring_world_x(obj, indices):
    mesh = obj.data
    coords = np.array([mesh.vertices[index].co for index in indices], "f")
    matrix = np.array(obj.matrix_world)
    return float(np.mean(coords @ matrix[:3, 0] + matrix[0, 3]))


def make_ring_mask(rings, size):
    """把 uv 环填成选区遮罩(像素行序为自上而下, 与 PIL 一致)"""
    from PIL import Image, ImageDraw

    width, height = size
    mask = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for _, ring in rings:
        points = ring * np.array([width, height], "f")
        points[:, 1] = height - points[:, 1]
        draw.polygon([tuple(point) for point in points], fill=1)
    return np.array(mask, bool)


def mask_bounds(mask):
    rows, cols = np.where(mask)
    return int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1


def get_uv_world_scale(obj, indices, uvs):
    """用一组顶点(及其 uv)拟合 uv 到世界坐标的映射, 返回 uv 每单位对应的世界尺寸(两个方向)"""
    mesh = obj.data
    matrix = np.array(obj.matrix_world)
    coords = np.array([mesh.vertices[index].co for index in indices], "f")
    world = coords @ matrix[:3, :3].T + matrix[:3, 3]

    fitted, *_ = np.linalg.lstsq(
        np.column_stack([uvs, np.ones(len(uvs))]), world, rcond=None
    )
    return float(np.linalg.norm(fitted[0])), float(np.linalg.norm(fitted[1]))


def resize_image(image, out_width, out_height):
    """双线性缩放(alpha 预乘, 避免透明边缘发黑)"""
    height, width = image.shape[:2]
    out_width, out_height = max(1, int(out_width)), max(1, int(out_height))

    x = np.clip((np.arange(out_width) + 0.5) * width / out_width - 0.5, 0, width - 1)
    y = np.clip(
        (np.arange(out_height) + 0.5) * height / out_height - 0.5, 0, height - 1
    )
    x0, x1 = np.floor(x).astype(int), np.minimum(np.floor(x).astype(int) + 1, width - 1)
    y0, y1 = (
        np.floor(y).astype(int),
        np.minimum(np.floor(y).astype(int) + 1, height - 1),
    )
    fx = (x - x0)[None, :, None]
    fy = (y - y0)[:, None, None]

    alpha = image[..., 3:4]
    color = image[..., :3] * alpha

    def blend(values):
        return (
            values[y0][:, x0] * (1 - fx) * (1 - fy)
            + values[y0][:, x1] * fx * (1 - fy)
            + values[y1][:, x0] * (1 - fx) * fy
            + values[y1][:, x1] * fx * fy
        )

    out_alpha = blend(alpha)[..., 0]
    out_color = blend(color)

    out = np.empty((out_height, out_width, 4), "f")
    out[..., :3] = out_color / np.maximum(out_alpha, 1e-6)[..., None]
    out[..., 3] = out_alpha
    return out


def rotate_image(image, angle_degrees, center):
    """绕 center 旋转图片(正值为顺时针), alpha 预乘避免透明边缘发黑"""
    height, width = image.shape[:2]
    radians = np.radians(-angle_degrees)
    cos, sin = np.cos(radians), np.sin(radians)

    columns, rows = np.meshgrid(np.arange(width), np.arange(height))
    delta_x = columns - center[0]
    delta_y = rows - center[1]
    source_x = center[0] + cos * delta_x - sin * delta_y
    source_y = center[1] + sin * delta_x + cos * delta_y

    x0 = np.floor(source_x).astype(int)
    y0 = np.floor(source_y).astype(int)
    fx = (source_x - x0)[..., None]
    fy = (source_y - y0)[..., None]

    alpha = image[..., 3:4]
    color = image[..., :3] * alpha

    def sample(values):
        total = np.zeros((height, width) + values.shape[2:], "f")
        for x, y, weight in (
            (x0, y0, (1 - fx) * (1 - fy)),
            (x0 + 1, y0, fx * (1 - fy)),
            (x0, y0 + 1, (1 - fx) * fy),
            (x0 + 1, y0 + 1, fx * fy),
        ):
            inside = (x >= 0) & (x < width) & (y >= 0) & (y < height)
            xc = np.clip(x, 0, width - 1)
            yc = np.clip(y, 0, height - 1)
            total += np.where(inside[..., None], values[yc, xc] * weight, 0.0)
        return total

    out = np.empty((height, width, 4), "f")
    out_alpha = sample(alpha)[..., 0]
    out_color = sample(color)
    out[..., :3] = out_color / np.maximum(out_alpha, 1e-6)[..., None]
    out[..., 3] = out_alpha
    return out


def build_pupil_overlay(
    pupil, template, template_node, template_size, rotate_angle: float = 0.0
):
    """取瞳孔贴图的 uv 选区, 按两边网格的物理尺寸缩放后贴到模板贴图 uv 环的中心"""
    pupil_node = get_pupil_texture_node(pupil)
    pupil_image = pupil_node.image
    if not pupil_image:
        raise ObjectError([pupil], "瞳孔网格的贴图节点上没有贴图")

    source_layer = get_uv_layer(pupil, pupil_node)
    source_rings = get_boundary_rings(pupil, source_layer)
    if not source_rings:
        raise ObjectError([pupil], "瞳孔网格没有闭合的 uv 外轮廓")

    # 双眼一体的网格只留与模板同侧的那只
    template_x = float(np.mean(get_world_coords(template), axis=0)[0])
    same_side = [
        item
        for item in source_rings
        if (get_ring_world_x(pupil, item[0]) >= 0) == (template_x >= 0)
    ]
    if not same_side:
        raise ObjectError([pupil], "瞳孔网格与模板不在同一侧")

    width, height = template_size
    source_size = tuple(pupil_image.size)
    source_mask = make_ring_mask(same_side, source_size)
    if not source_mask.any():
        raise ObjectError([pupil], "瞳孔网格的 uv 轮廓没有覆盖到贴图像素")
    pix_left, pix_top, pix_right, pix_bottom = mask_bounds(source_mask)

    # 贴图行序都按自上而下取, 最后整体翻回 blender 的自下而上
    source, _ = get_image_pixels(pupil_image)
    crop = source[pix_top:pix_bottom, pix_left:pix_right].copy()
    crop[~source_mask[pix_top:pix_bottom, pix_left:pix_right]] = 0

    # 瞳孔选区贴图 -> 模板贴图 的缩放: 让瞳孔在两边网格上的物理尺寸一致
    source_scale = get_uv_world_scale(
        pupil,
        [index for item in same_side for index in item[0]],
        np.concatenate([item[1] for item in same_side]),
    )
    template_layer = get_uv_layer(template, template_node)
    template_rings = get_boundary_rings(template, template_layer)
    template_scale = get_uv_world_scale(
        template,
        [index for item in template_rings for index in item[0]],
        np.concatenate([item[1] for item in template_rings]),
    )
    crop = resize_image(
        crop,
        round(
            crop.shape[1] * source_scale[0] / template_scale[0] * width / source_size[0]
        ),
        round(
            crop.shape[0]
            * source_scale[1]
            / template_scale[1]
            * height
            / source_size[1]
        ),
    )

    template_mask = make_ring_mask(template_rings, template_size)
    if not template_mask.any():
        raise ObjectError([template], "模板网格的 uv 轮廓没有覆盖到贴图像素")
    mask_left, mask_top, mask_right, mask_bottom = mask_bounds(template_mask)

    overlay = np.zeros((height, width, 4), "f")
    crop_height, crop_width = crop.shape[:2]
    left = (mask_left + mask_right) // 2 - crop_width // 2
    top = (mask_top + mask_bottom) // 2 - crop_height // 2
    source_left, source_top = max(0, -left), max(0, -top)
    left, top = max(0, left), max(0, top)
    right = min(width, left + crop_width - source_left)
    bottom = min(height, top + crop_height - source_top)
    if right > left and bottom > top:
        overlay[top:bottom, left:right] = crop[
            source_top : source_top + (bottom - top),
            source_left : source_left + (right - left),
        ]

    if rotate_angle:
        overlay = rotate_image(
            overlay,
            rotate_angle,
            ((mask_left + mask_right) / 2, (mask_top + mask_bottom) / 2),
        )
    return overlay[::-1]


def create_image(pixels, size, template_image, name):
    """新建贴图并写入像素(0-1, 行序自下而上, 由调用方翻转好), 色彩空间沿用模板原来的贴图"""
    image = bpy.data.images.new(name, size[0], size[1], alpha=True)
    image.colorspace_settings.name = (
        template_image.colorspace_settings.name if template_image else "sRGB"
    )
    image.pixels.foreach_set(np.ascontiguousarray(pixels, "f4").ravel())
    return image


def save_template_image(texture_node, image, img_path):
    """保存贴图到工程目录(不覆盖模板原贴图), 并让模板材质指向它"""
    backup_image_file(img_path)

    try:
        image.save(filepath=str(img_path))
    except Exception:
        bpy.data.images.remove(image)
        raise

    set_named_image(texture_node, image, img_path, IMAGE_NAME)


def get_last_mirror(template):
    """上次用的右眼镜像选项, 没记过就默认否"""
    value = template.get(MIRROR_STATE_KEY) if template else None
    return value if value in ("是", "否") else "否"


def save_last_mirror(template, mirror):
    """把这次的右眼镜像选项记在模板物体上(随工程保存)"""
    template[MIRROR_STATE_KEY] = mirror


def main(mirror: str = "否", rotate_degrees: float = 0.0, mode: str = "复制"):
    objs = selected_meshes()
    if len(objs) != 1:
        raise ObjectError(objs, "请只选中一个瞳孔网格")

    pupil = objs[0]
    template = get_obj(TEMPLATE_NAME)
    if not template:
        raise ObjectError(objs, f"场景中找不到模板物体 {TEMPLATE_NAME}")
    if pupil is template:
        raise ObjectError(objs, "请选中瞳孔网格, 而不是模板")
    if pupil.mode != "OBJECT" or template.mode != "OBJECT":
        raise ObjectError(objs, "请先退出编辑模式")

    material, texture_node = get_texture_material_and_node(template, TEMPLATE_NAME)
    save_last_mirror(template, mirror)
    old_image = texture_node.image
    # 模板贴图可能已被清掉(数据块还在但文件丢了, 尺寸为 0), 退回到默认尺寸 / sRGB
    template_size = (
        tuple(old_image.size)
        if old_image and all(old_image.size)
        else (IMG_SIZE, IMG_SIZE)
    )
    img_path = get_blend_file_dir() / f"{IMAGE_NAME}.png"

    if mode == "投影":
        images = [get_source_image(slot.material) for slot in pupil.material_slots]
        if not any(images):
            raise ObjectError(objs, "源网格的材质里找不到贴图")

        pixels, coverage = project(pupil, template, template_size, images, IMG_SIZE)
        if coverage < 0.01:
            raise ObjectError(
                objs, f"源网格与 {TEMPLATE_NAME} 在正视图中没有重合, 检查选中物体和朝向"
            )
        image = create_image(pixels[::-1], template_size, old_image, "投影瞳孔贴图")
    else:
        pixels = build_pupil_overlay(
            pupil, template, texture_node, template_size, rotate_degrees
        )
        image = create_image(pixels, template_size, old_image, "复制瞳孔临时贴图")

    save_template_image(texture_node, image, img_path)
    print(f"瞳孔贴图已保存到: {img_path}")
    ensure_alpha_clip(material, texture_node)
    write_pupil_overlay_to_card(img_path, mirror)
    return image


def write_pupil_overlay_to_card(img_path, mirror):
    """把复制好的瞳孔贴图转成游戏颜色后写进默认人物卡, 并让游戏重载该卡

    mirror 为 '是' 时右眼额外写一张水平镜像的贴图
    """
    card_path = get_card_path(get_blend_file_stem())
    if not card_path.exists():
        message_box(
            "找不到人物卡, 贴图只保存到工程目录, 没写进卡片.\n"
            f"贴图: {img_path}\n"
            f"人物卡: {card_path}\n"
            '请先点"↓初始化mod"按钮生成人物卡, 再重新运行',
            title=TITLE,
            icon="ERROR",
        )
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        card_image_path = temp_dir / f"{IMAGE_NAME}.png"
        img_to_kk_color(img_path, card_image_path, "PNG")

        right_image_path = None
        if mirror == "是":
            right_image_path = temp_dir / f"{IMAGE_NAME}_mirror.png"
            mirror_image_horizontal(card_image_path, right_image_path)

        set_pupil_overlay(card_path, card_image_path, right_image_path)
    set_official_pupil_no_iris(card_path)
    if not reload_kk_card(card_path):
        message_box(
            f"贴图已写入人物卡, 但游戏重载失败(游戏可能没在运行):\n{card_path}",
            title=TITLE,
            icon="ERROR",
        )
    print(f"瞳孔贴图已写入人物卡: {card_path}")


class PupilOverlayMenu(bpy.types.Operator):
    """写入瞳孔贴图前确认模式与选项, 取消则不做任何操作"""

    bl_idname = "wm.pupil_overlay_menu"
    bl_label = "写入瞳孔贴图"

    mode: MODE_PROPERTY
    mirror: MIRROR_PROPERTY
    rotate_degrees: ROTATE_PROPERTY

    def invoke(self, context, event):
        self.mirror = get_last_mirror(get_obj(TEMPLATE_NAME))
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "mode")
        if self.mode == "投影":
            self.layout.label(text="沿 Y 轴正交投影, 结果与外部模型的正视图一致")
            self.layout.label(text="源网格可以带厚度或分多层, 不需要缩裹和烘焙")
        else:
            self.layout.prop(self, "rotate_degrees")
        self.layout.prop(self, "mirror")

    @report_errors
    def execute(self, context):
        main(self.mirror, self.rotate_degrees, self.mode)
        return {"FINISHED"}


if __name__ == "__main__":
    register_and_invoke_menu(PupilOverlayMenu)
