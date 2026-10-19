"""自动缩裹 + 生成烘焙产物 + 烘焙

选中要烘焙的源网格: 缩裹到官方 bodytight (bake-inner 0mm / bake-middle 1mm / bake-outer 2mm
三个顶点组限定的修改器, 已存在的一律不动), 再生成/复用烘焙产物(bodytight 子集), 最后逐个烘焙。
烘焙产物带 `hitori_bake_source` 属性(指向源物体, 随 blend 保存), 源网格没改过就复用;
弹窗只在需要时出现: 贴图分辨率 / 距离阈值 / 罩体 / 补洞都记在产物上, 想改就删掉产物再运行。
"""

from collections.abc import Sequence
from pathlib import Path

import bpy
from bpy.types import Object

from hitori_addon.baketarget import (
    BAKE_SIZE_PROPERTY,
    DEFAULT_CAGE_DISTANCE,
    DEFAULT_DISTANCE_MM,
    DEFAULT_FILL_HOLES,
    DEFAULT_GROW,
    MAX_PROJECTION_GAP,
    ensure_bodytight,
    find_existing_target,
    format_distance,
    get_bake_sources,
    get_cage_property,
    get_distance_property,
    get_fill_holes_property,
    get_or_generate_target,
    get_target_params,
    need_bake_params,
    parse_distance,
)
from hitori_addon.check import is_mmd_material
from hitori_addon.error import ObjectError
from hitori_addon.image import backup_image_file
from hitori_addon.material import ensure_alpha_clip, set_simple_material
from hitori_addon.menu import message_box, register_menu_and_run
from hitori_addon.obj import (
    activate_obj,
    deselect_obj,
    hide_obj,
    select_objs,
)
from hitori_addon.path import get_blend_file_dir

IMG_SIZE = 1024
MIN_IMG_SIZE = 64
MAX_IMG_SIZE = 8192
SIZE_PROPERTY = bpy.props.StringProperty(
    name="贴图分辨率",
    description="必须是 2 的 n 次方; 只在新建产物时生效, 已存在的产物用它自己记下的分辨率",
    default=str(IMG_SIZE),
)
DISTANCE_PROPERTY = get_distance_property()
CAGE_PROPERTY = get_cage_property()
FILL_HOLES_PROPERTY = get_fill_holes_property()
# 缩裹方案: (修改器与顶点组同名, 偏移(米)); 三个顶点组构成全集且互斥
# 贴身的放 bake-inner(0mm), 宽松的放 bake-outer(2mm), 剩下的都在 bake-middle(1mm)
SHRINKWRAP_SETUP = (
    ("bake-inner", 0.0),
    ("bake-middle", 0.001),
    ("bake-outer", 0.002),
)
MIDDLE_GROUP = "bake-middle"
EDGE_GROUPS = ("bake-inner", "bake-outer")

NOTES = """注意事项:
· 缩裹是 bake-inner/bake-middle/bake-outer 三个顶点组限定的修改器, 已存在的顶点组与修改器不会改动
· bake-middle 就是 inner/outer 之外的顶点(1mm): 想贴身/宽松就把顶点放进 bake-inner(0mm)/bake-outer(2mm)
· 自己改过顶点组或缩裹参数, 产物会自动重建; 都没改就直接复用
· 烘焙产物是 bodytight 的子集, 保留官方权重/缝合边/法线, UV 是重展的, 旧贴图对不上
· 产物比源网格多出来的边缘没东西可烘, 贴图上是透明像素, 材质预览里能看到, 自己用画笔补一下
· 分辨率/距离/罩体/补洞记在产物上: 第一次运行时输入(默认 1024/10mm/不建罩体/补洞), 之后直接沿用不再问, 想换就删掉产物再运行
· 改过源网格就要重新烘焙, 贴图输出到 blend 同目录 <产物名>.png
· 产物名: 源网格名带 _bake / -bake / bake_ / bake- 且去掉后是合法服装名(如 cloth_top_bake)时直接用合法名
  (贴图也就叫 cloth_top.png), 否则叫 <源名>_target; 改过名要删掉产物重跑"""


def parse_img_size(text: str) -> int:
    """解析贴图分辨率: 必须是 2 的 n 次方"""
    value = text.strip()
    if not value.isdigit():
        raise ObjectError([], f"贴图分辨率必须是整数, 现在是 {text!r}")
    size = int(value)
    if not MIN_IMG_SIZE <= size <= MAX_IMG_SIZE or size & (size - 1):
        raise ObjectError(
            [],
            f"贴图分辨率要在 {MIN_IMG_SIZE}~{MAX_IMG_SIZE} 之间且是 2 的 n 次方, 现在是 {size}",
        )
    return size


def ensure_vg(obj: Object, name: str) -> bool:
    """没有该顶点组就新建, 返回是否新建"""
    if obj.vertex_groups.get(name) is not None:
        return False
    obj.vertex_groups.new(name=name)
    return True


def get_group_vertex_indices(obj: Object, names: Sequence[str]) -> set[int]:
    """这几个顶点组里有非零权重的顶点索引"""
    group_indices = {
        obj.vertex_groups[name].index for name in names if obj.vertex_groups.get(name)
    }
    result = set()
    for vertex in obj.data.vertices:
        for element in vertex.groups:
            if element.group in group_indices and element.weight:
                result.add(vertex.index)
                break
    return result


def ensure_shrinkwrap(obj: Object, bodytight: Object) -> list[str]:
    """缩裹到官方身体, 返回新建的修改器名

    三个顶点组构成全集且互斥: bake-middle = 除 bake-inner / bake-outer 之外的全部顶点。
    每次运行都重新对齐一遍(保留 middle 里已有权重, 只增删归属); 修改器只补缺失的, 已存在的不动。
    """
    for name, _ in SHRINKWRAP_SETUP:
        ensure_vg(obj, name)
    edge_indices = get_group_vertex_indices(obj, EDGE_GROUPS)
    middle_indices = get_group_vertex_indices(obj, (MIDDLE_GROUP,))
    middle = obj.vertex_groups[MIDDLE_GROUP]
    all_indices = range(len(obj.data.vertices))
    to_add = [index for index in all_indices if index not in edge_indices | middle_indices]
    to_remove = sorted(middle_indices & edge_indices)
    if to_add:
        middle.add(to_add, 1.0, "REPLACE")
    if to_remove:
        middle.remove(to_remove)

    created = []
    for name, offset in SHRINKWRAP_SETUP:
        if obj.modifiers.get(name) is not None:
            continue
        modifier = obj.modifiers.new(name=name, type="SHRINKWRAP")
        modifier.wrap_method = "TARGET_PROJECT"
        modifier.wrap_mode = "ABOVE_SURFACE"
        modifier.offset = offset
        modifier.target = bodytight
        modifier.vertex_group = name
        modifier.show_on_cage = True
        created.append(name)
    return created


def bake(src_obj: Object, dst_obj: Object, size: int, fill_holes: bool) -> Path:
    # mmd 材质节点树没法烘, 先统一成单贴图材质 (只要颜色, 不沿用 alpha / 法线)
    materials = [slot.material for slot in src_obj.material_slots if slot.material]
    if any(is_mmd_material(material) for material in materials):
        for material in materials:
            set_simple_material(material, keep_alpha=False, keep_normal=False)

    select_objs([src_obj, dst_obj])
    activate_obj(dst_obj)
    material_name = dst_obj.name

    width, height = size, size

    old_material = bpy.data.materials.get(material_name)
    old_image = bpy.data.images.get(material_name)
    if old_material:
        bpy.data.materials.remove(old_material)
    if old_image:
        bpy.data.images.remove(old_image)

    image = bpy.data.images.new(material_name, width, height, alpha=True)
    material = bpy.data.materials.new(material_name)
    texture_node = set_simple_material(
        material, image, keep_alpha=False, keep_normal=False
    )

    # 没烘到的透明像素要能在材质预览里看到(自己补画), 透明处也才不会发黑
    ensure_alpha_clip(material, texture_node)

    # 赋予当前材质
    dst_obj.data.materials.clear()
    dst_obj.data.materials.append(material)

    # 设置渲染属性和烘焙属性
    scene = bpy.context.scene

    cycles = scene.cycles
    cycles.device = "GPU"
    cycles.bake_type = "DIFFUSE"

    render = scene.render
    render.engine = "CYCLES"

    render.bake.use_pass_direct = False
    render.bake.use_pass_indirect = False
    render.bake.use_pass_color = True

    render.bake.use_selected_to_active = True
    render.bake.use_cage = False
    render.bake.cage_extrusion = 0.010
    # 光线距离决定能烘到多远的源网格: 补过空洞的产物最远处可能离源网格 100mm
    render.bake.max_ray_distance = MAX_PROJECTION_GAP if fill_holes else 0.020

    render.bake.target = "IMAGE_TEXTURES"
    render.bake.use_clear = True

    bpy.ops.object.bake(type="DIFFUSE")

    # 备份并保存贴图
    img_path = get_blend_file_dir() / f"{image.name}.png"

    backup_image_file(img_path)

    # 传入blender的路径只能是str
    filepath = str(img_path)
    image.save(filepath=filepath)
    image.filepath = filepath

    deselect_obj(dst_obj)
    activate_obj(src_obj)
    return img_path


def get_existing_size(src_obj: Object) -> int | None:
    """现有产物记下的分辨率, 没有产物或没记过就是 None"""
    target = find_existing_target(src_obj)
    if target is None:
        return None
    size = target.get(BAKE_SIZE_PROPERTY)
    return size if isinstance(size, int) and size > 0 else None


def need_input() -> bool:
    """有产物还没记分辨率 / 生成参数时才需要弹窗问一次"""
    sources = get_bake_sources()
    return need_bake_params(sources) or any(
        get_existing_size(src_obj) is None for src_obj in sources
    )


def main(
    size: str = str(IMG_SIZE),
    distance: str = f"{DEFAULT_DISTANCE_MM:g}",
    cage: bool = False,
    fill_holes: bool = DEFAULT_FILL_HOLES,
    hide_src_obj: bool = False,
):
    img_size = parse_img_size(size)
    distance_value = parse_distance(distance)
    sources = get_bake_sources()
    if not sources:
        raise ObjectError(sources, "没有选中可烘焙的网格(不能是 bodytight 或烘焙产物)")

    bodytight = ensure_bodytight()

    lines = []
    for src_obj in sources:
        created = ensure_shrinkwrap(src_obj, bodytight)
        # 已有产物记过分辨率 / 参数就沿用(重建产物也不会丢), 没有才用弹窗输入 / 默认值
        target_size = get_existing_size(src_obj) or img_size
        target, cage_obj = get_or_generate_target(
            src_obj,
            distance=distance_value,
            grow=DEFAULT_GROW,
            unwrap=True,
            cage=cage,
            cage_distance=DEFAULT_CAGE_DISTANCE,
            fill_holes=fill_holes,
        )
        target[BAKE_SIZE_PROPERTY] = target_size
        distance_used, _, _, fill_used = get_target_params(target) or (
            distance_value,
            DEFAULT_GROW,
            cage,
            fill_holes,
        )
        bake(src_obj, target, target_size, fill_used)
        if hide_src_obj:
            hide_obj(src_obj)
        line = (
            f"{src_obj.name} ({len(src_obj.data.polygons)}面, "
            f"{'新加 ' + '/'.join(created) if created else '已有缩裹'}) "
            f"-> {target.name} ({len(target.data.polygons)}面, {format_distance(distance_used)}, "
            f"{'补洞, ' if fill_used else ''}{target_size}px)"
        )
        if cage_obj:
            line += f" + {cage_obj.name}"
        lines.append(line)

    select_objs(sources)
    message_box(
        "\n".join([*lines, "", NOTES, "", f"贴图: {get_blend_file_dir()}"]),
        title="自动缩裹烘焙",
    )


if __name__ == "__main__":
    if bpy.app.background or not need_input():
        main()
    else:
        register_menu_and_run(
            main,
            string_property=SIZE_PROPERTY,
            bool_property=CAGE_PROPERTY,
            string_property_2=DISTANCE_PROPERTY,
            bool_property_2=FILL_HOLES_PROPERTY,
        )
