import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import bpy
import numpy as np
from bpy.types import Image, Material

from hitori_addon.game_data import get_kk_color_curve_nodes
from hitori_addon.material import (
    arrange_nodes_layout,
    find_upstream_texture_node,
    get_bsdf_node,
)
from hitori_addon.path import aspath, find_best_name_match, get_file_paths, name_tokens

# 贴图扩展名优先级 (排前面的优先, 同一张图的 png 优先于 psd 这类源文件)
TEXTURE_EXTENSIONS = ["png", "tga", "webp", "jpg", "jpeg", "bmp", "dds", "psd"]
# 默认排除的文件夹 (UV 展开图之类, 不是贴图)
DEFAULT_TEXTURE_EXCLUDE_DIRS = ("uv",)
# 名字相似度阈值: 低于它就不配图 (宁缺勿错)
DEFAULT_TEXTURE_MATCH_THRESHOLD = 0.45
# 这些用途的材质要单独做遮罩图, 拿漫反射贴图填是错的
TEXTURE_MASK_TOKENS = frozenset(
    {
        "alpha",
        "mask",
        "shadow",
        "outline",
        "rim",
        "light",
        "highlight",
        "emission",
        "emissive",
        "matcap",
    }
)


def fold_image_name(name: str) -> str:
    """贴图名比对用的折叠: 小写, 空格 / 点 / 下划线 / 连字符归一成下划线, 去掉首尾分隔符"""
    stem, _, ext = name.rpartition(".")
    if not stem:
        stem, ext = name, ""
    stem = re.sub(r"[\s._-]+", "_", stem.lower()).strip("_")
    return f"{stem}.{ext.lower()}" if ext else stem


def fix_missing_image_paths() -> list[tuple[str, str]]:
    """把读不到的贴图路径指向同目录下唯一同名文件, 返回 (原路径, 新路径)

    PMX 里的贴图路径常带手误 (`xxx_d..png` 多一个点 / 扩展名大小写不一致 / 文件名里带空格),
    Blender 按原样拼路径读不到图, 材质就成空白。只改内存里的图片路径指向真实文件, 不拷贝也不改名磁盘文件;
    折叠后能对上多个文件的算歧义, 不动。
    """
    folder_cache: dict[Path, dict[str, list[Path]]] = {}
    fixed: list[tuple[str, str]] = []

    for image in bpy.data.images:
        if not image.filepath:
            continue

        path = Path(bpy.path.abspath(image.filepath))
        if path.exists():
            continue

        folder = path.parent
        if folder not in folder_cache:
            candidates: dict[str, list[Path]] = {}
            if folder.is_dir():
                for file_path in folder.iterdir():
                    if file_path.is_file():
                        key = fold_image_name(file_path.name)
                        candidates.setdefault(key, []).append(file_path)
            folder_cache[folder] = candidates

        matched = folder_cache[folder].get(fold_image_name(path.name), [])
        if len(matched) != 1:
            continue

        fixed.append((str(path), str(matched[0])))
        image.filepath = str(matched[0])
        image.reload()

    return fixed


def img_file_has_alpha(img_path: str | Path) -> bool:
    from PIL.Image import open as pil_image_open

    with pil_image_open(img_path) as image:
        return image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )


def get_img_file_min_alpha(img_path: str | Path) -> float:
    from PIL.Image import open as pil_image_open

    with pil_image_open(img_path) as image:
        image_array = np.array(image)

    channels = image_array.shape[-1] if image_array.ndim == 3 else 1
    if channels < 4:
        return 1
    else:
        return np.min(image_array[:, :, 3]) / 255.0


def backup_image_file(img_path: str | Path) -> Path | None:
    """备份旧贴图: tex.ext -> tex.{时间}.ex_

    扩展名末位改成 _, 文件名保持 tex.xxx 前缀, 文件管理器的同名分组不会把备份和原图分开
    """
    img_path = Path(img_path)
    if not img_path.exists():
        return None

    stamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    suffix = img_path.suffix
    backup_suffix = f"{suffix[:-1]}_" if len(suffix) > 1 else f"{suffix}_"

    backup_path = img_path.with_name(f"{img_path.stem}.{stamp}{backup_suffix}")
    index = 2
    while backup_path.exists():
        backup_path = img_path.with_name(
            f"{img_path.stem}.{stamp}_{index}{backup_suffix}"
        )
        index += 1

    shutil.copy(img_path, backup_path)
    return backup_path


def mirror_image_horizontal(img_path: str | Path, output_path: str | Path):
    """水平镜像图片并保存"""
    from PIL import Image as PilImage

    transpose = getattr(PilImage, "Transpose", PilImage).FLIP_LEFT_RIGHT
    with PilImage.open(img_path) as image:
        image.transpose(transpose).save(output_path)


def set_named_image(texture_node, image: Image, img_path: str | Path, name: str):
    """把新建的贴图接到模板材质的贴图节点上, 并改名成 name

    同名旧贴图没人用就删掉, 否则 Blender 会把它改名成 `name.001` 留下垃圾数据
    """
    texture_node.image = image
    old_named_image = bpy.data.images.get(name)
    if (
        old_named_image is not None
        and old_named_image is not image
        and old_named_image.users == 0
    ):
        bpy.data.images.remove(old_named_image)
    image.name = name
    image.filepath = str(img_path)


# KK 校色曲线: 每通道 17 个节点 (输入 0, 1/16, ..., 1 处的输出), 在 sRGB 空间线性插值
# 原实现把 KKLUT 注册进本机 Blender 的 config.ocio 再用 view_settings.look = 'KKLUT',
# 那个 look 不在仓库里也没法随插件安装, 换台机器会直接 TypeError。改成对像素施加曲线。
# 节点值取自原 64^3 LUT 的通道均值曲线, 已平滑掉原表在极饱和角点的试错痕迹;
# 与现成 LUT 整体平均差约 3/255, 后续可按游戏观感重定 (见 docs/external_resources.md)
KK_COLOR_CURVE_LEVELS = 256


@lru_cache(maxsize=1)
def _kk_color_curve_table() -> np.ndarray:
    """把 17 节点曲线铺成 256 级查表, 首次调用时从外部资源加载"""
    nodes = get_kk_color_curve_nodes()
    curve_input = np.linspace(0, 1, nodes.shape[1])
    return np.stack(
        [
            np.interp(
                np.linspace(0, 1, KK_COLOR_CURVE_LEVELS),
                curve_input,
                nodes[channel],
            )
            for channel in range(3)
        ]
    ).astype("f")


def kk_color_curve(rgb: np.ndarray) -> np.ndarray:
    """对位于 0-1 的 sRGB 值施加 KK 校色曲线, rgb 形如 (..., 3)"""
    table = _kk_color_curve_table()
    levels = KK_COLOR_CURVE_LEVELS - 1
    index = np.clip(np.rint(rgb * levels), 0, levels).astype(np.intp)
    return np.stack(
        [table[channel][index[..., channel]] for channel in range(3)],
        axis=-1,
    )


def apply_kk_color_to_img(img: Image):
    """把 KK 校色作用到 img 的 RGB 像素上

    实测已加载 sRGB 图片的 img.pixels 就是 sRGB 值, 且 Standard / 无 look 时 save_render
    逐像素恒等, 所以曲线直接作用在像素上, 不需要额外的线性空间转换。
    """
    width, height = img.size
    pixel_values = np.empty(width * height * 4, "f")
    img.pixels.foreach_get(pixel_values)
    pixel_values = pixel_values.reshape(-1, 4)
    pixel_values[:, :3] = kk_color_curve(pixel_values[:, :3]).astype("f")
    img.pixels.foreach_set(pixel_values.reshape(-1))
    img.update()


def get_img_min_alpha(img: Image) -> float:
    """取图片的最小 alpha

    用 img.pixels.foreach_get 比 img.pixels[:] 切片快得多, 也比经 PIL 取 numpy 数组快
    foreach_get 只支持单精度 'f', 用双精度会报错
    """
    if img.depth <= 24:
        return 1

    width, height = img.size
    pixel_values = np.empty(width * height * 4, "f")
    img.pixels.foreach_get(pixel_values)

    # 每个像素 4 个通道, 取所有像素的 alpha 通道
    return float(np.min(pixel_values[3::4]))


def img_to_kk_color(
    img_path: str | Path,
    output_path: str | Path,
    file_format: Literal["PNG", "TARGA"],
    ignore_useless_alpha: bool = True,
    useless_alpha_threshold: float = 0.99,
):
    # 备份设置
    scene = bpy.context.scene
    view_settings = scene.view_settings

    current_colorspace_name = scene.sequencer_colorspace_settings.name
    current_display_device = scene.display_settings.display_device
    current_view_transform = view_settings.view_transform
    current_look = view_settings.look
    current_exposure = view_settings.exposure
    current_gamma = view_settings.gamma
    current_use_curve_mapping = view_settings.use_curve_mapping

    # save_render 会走场景色彩管理, 这套设置下存盘是逐像素恒等, 校色已经在像素上做完
    scene.sequencer_colorspace_settings.name = "sRGB"
    scene.display_settings.display_device = "sRGB"
    view_settings.view_transform = "Standard"
    view_settings.look = "None"
    view_settings.exposure = 0
    view_settings.gamma = 1
    view_settings.use_curve_mapping = False

    # 开始操作
    img = bpy.data.images.load(filepath=str(img_path))
    apply_kk_color_to_img(img)
    img_save_render(
        img,
        output_path,
        file_format,
        ignore_useless_alpha=ignore_useless_alpha,
        useless_alpha_threshold=useless_alpha_threshold,
    )
    bpy.data.images.remove(img)

    # 还原设置
    scene.sequencer_colorspace_settings.name = current_colorspace_name
    scene.display_settings.display_device = current_display_device
    view_settings.view_transform = current_view_transform
    view_settings.look = current_look
    view_settings.exposure = current_exposure
    view_settings.gamma = current_gamma
    view_settings.use_curve_mapping = current_use_curve_mapping


def img_save_render(
    img: Image,
    filepath: str | Path,
    file_format: Literal["PNG", "TARGA"],
    ignore_useless_alpha: bool = True,
    useless_alpha_threshold: float = 0.99,
):
    # 备份设置
    image_settings = bpy.context.scene.render.image_settings

    current_file_format = image_settings.file_format
    current_color_mode = image_settings.color_mode
    current_color_depth = image_settings.color_depth

    image_settings.file_format = file_format
    image_settings.color_mode = get_img_color_mode(
        img,
        ignore_useless_alpha=ignore_useless_alpha,
        useless_alpha_threshold=useless_alpha_threshold,
    )
    image_settings.color_depth = "8"

    # 开始操作
    img.save_render(str(filepath))

    # 还原设置
    image_settings.file_format = current_file_format
    image_settings.color_mode = current_color_mode
    image_settings.color_depth = current_color_depth


def get_img_color_mode(
    img: Image,
    ignore_useless_alpha: bool = True,
    useless_alpha_threshold: float = 0.99,
) -> str:
    if img.depth <= 8:
        return "BW"
    elif img.depth <= 24:
        return "RGB"
    else:
        if ignore_useless_alpha and get_img_min_alpha(img) > useless_alpha_threshold:
            return "RGB"
        else:
            return "RGBA"


def normalize_extensions(extensions: list[str] | None) -> list[str]:
    """扩展名归一: 小写去点, 去重但保留顺序 (顺序就是优先级)"""
    ext_list = extensions or TEXTURE_EXTENSIONS
    return list(dict.fromkeys(ext.lower().lstrip(".") for ext in ext_list if ext.strip(". ")))


def get_texture_candidates(
    texture_dir: str | Path,
    extensions: list[str] | None = None,
    recursive: bool = True,
    exclude_dirs: Sequence[str] | None = DEFAULT_TEXTURE_EXCLUDE_DIRS,
) -> dict[str, Path]:
    """候选贴图: 文件名 stem -> 路径

    同名不同扩展名时按扩展名优先级只留一个 (png 优先于 psd), 同扩展名按路径排序取第一个;
    路径里含排除文件夹名的跳过 (默认排除 UV 展开图目录, 传空列表则不排除)。
    """
    ext_list = normalize_extensions(extensions)
    priority = {ext: index for index, ext in enumerate(ext_list)}
    exclude_names = {name.strip().lower() for name in (exclude_dirs or [])}

    if not str(texture_dir).strip():
        raise LookupError("贴图目录为空")

    folder = aspath(texture_dir)
    file_paths = [
        file_path
        for file_path in get_file_paths(folder, exts=ext_list, recursive=recursive)
        if not exclude_names
        & {part.lower() for part in file_path.relative_to(folder).parts[:-1]}
    ]
    file_paths.sort(
        key=lambda file_path: (
            priority[file_path.suffix.lower().lstrip(".")],
            str(file_path).lower(),
        )
    )

    name_path_map: dict[str, Path] = {}
    for file_path in file_paths:
        name_path_map.setdefault(file_path.stem, file_path)
    return name_path_map


def get_base_color_node(material: Material):
    """材质 Base Color 上直接连着的节点 (空着时为 None)"""
    bsdf_node = get_bsdf_node(material)
    if not bsdf_node:
        return None

    for link in bsdf_node.inputs["Base Color"].links:
        return link.from_node
    return None


def get_base_color_image(material: Material) -> Image | None:
    """材质 Base Color 上直接连着的贴图 (连着别的节点时为 None)"""
    node = get_base_color_node(material)
    if node is None or node.type != "TEX_IMAGE":
        return None
    return node.image


def is_image_available(image: Image | None) -> bool:
    """贴图是否读得到 (打包的 / 生成的都算可用)"""
    if image is None:
        return False
    if image.source != "FILE" or image.packed_file:
        return True
    return Path(bpy.path.abspath(image.filepath)).is_file()


def load_texture_image(texture_path: Path) -> Image:
    """加载贴图, 已经加载过同一路径就复用 (不重复生成 .001 数据块)"""
    target = str(texture_path)
    for image in bpy.data.images:
        if image.filepath and bpy.path.abspath(image.filepath) == target:
            return image
    return bpy.data.images.load(target)


def get_material_texture_keys(material: Material) -> list[str]:
    """材质的匹配线索, 按可靠性排序: 旧贴图文件名 > 用到它的网格名 > 材质名"""
    keys: list[str] = []

    image = get_base_color_image(material)
    if image is not None and Path(image.filepath).suffix:
        # fbx 里的贴图路径有时只剩目录, 这种名字是垃圾 (Untitled), 跳过
        keys.append(Path(image.filepath).stem)

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        slot_materials = {slot.material for slot in obj.material_slots if slot.material}
        # 一个网格挂多个材质时网格名分不清该给谁, 不能当线索 (身体网格常同时挂脸 / 脸遮罩)
        if slot_materials != {material}:
            continue
        keys.extend((obj.name, obj.data.name))

    keys.append(material.name)
    return keys


def is_mask_material(material: Material) -> bool:
    """遮罩类材质 (alpha / shadow / outline ...) 需要专门的遮罩图, 不该拿漫反射贴图填"""
    return bool(name_tokens(material.name) & TEXTURE_MASK_TOKENS)


@dataclass
class TextureImportResult:
    """单个材质的补图结果"""

    material: str
    # 配上的贴图路径; 没配上时为 None
    path: str | None = None
    score: float = 0.0
    # 没配图的原因
    reason: str = ""


@dataclass
class TextureImportReport:
    """一次补图的全部结果"""

    results: list[TextureImportResult] = field(default_factory=list)
    # 删掉的旧贴图 / 孤立贴图节点数
    removed_nodes: int = 0
    # 删掉的没法线贴图的法线节点数
    removed_normal_maps: int = 0
    # 删掉的没人引用的贴图数据块名
    removed_images: list[str] = field(default_factory=list)


def remove_unused_node(material: Material, node) -> bool:
    """删掉已经没有下游连线的节点"""
    if any(output.links for output in node.outputs):
        return False
    material.node_tree.nodes.remove(node)
    return True


def remove_missing_texture_nodes(material: Material) -> int:
    """删掉读不到图且已经没有下游的贴图节点 (换下来的旧节点会变成这种)"""
    removed = 0
    for node in list(material.node_tree.nodes):
        if node.type != "TEX_IMAGE" or is_image_available(node.image):
            continue
        if remove_unused_node(material, node):
            removed += 1
    return removed


def remove_unused_normal_map_nodes(material: Material) -> int:
    """删掉没有法线贴图的法线节点 (没接图或图读不到), 空着的法线节点只会误导人"""
    removed = 0
    for node in list(material.node_tree.nodes):
        if node.type != "NORMAL_MAP":
            continue
        image_node = find_upstream_texture_node(node.inputs["Color"])
        if image_node is not None and is_image_available(image_node.image):
            continue
        material.node_tree.nodes.remove(node)
        removed += 1
    return removed


def remove_missing_images() -> list[str]:
    """清掉没人引用且读不到的贴图数据块"""
    removed: list[str] = []
    for image in list(bpy.data.images):
        if image.users or image.source != "FILE" or is_image_available(image):
            continue
        removed.append(image.name)
        bpy.data.images.remove(image)
    return removed


def get_alpha_link_targets(bsdf_node) -> list:
    """新贴图 Alpha 该接的输入口: 旧贴图 Alpha 的去向 + 接在 Alpha 口上的丢失贴图"""
    targets = []
    base_color_input = bsdf_node.inputs["Base Color"]
    for link in base_color_input.links:
        alpha_output = link.from_node.outputs.get("Alpha")
        if alpha_output is not None:
            targets.extend(alpha_link.to_socket for alpha_link in alpha_output.links)

    # 有的 fbx 把 Alpha 口接在另一张 (读不到的) 贴图的颜色上, 跟着新贴图换成 Alpha
    for link in bsdf_node.inputs["Alpha"].links:
        source_node = link.from_node
        if source_node.type == "TEX_IMAGE" and not is_image_available(source_node.image):
            targets.append(bsdf_node.inputs["Alpha"])
    return list(dict.fromkeys(targets))


def match_material_texture(
    material: Material,
    name_path_map: dict[str, Path],
    candidate_names: list[str],
    threshold: float,
) -> TextureImportResult:
    """给单个材质找贴图并接上节点, 返回匹配结果"""
    bsdf_node = get_bsdf_node(material)
    base_color_input = bsdf_node.inputs["Base Color"]
    alpha_targets = get_alpha_link_targets(bsdf_node)

    match_name, score = find_best_name_match(
        get_material_texture_keys(material), candidate_names, threshold
    )
    if match_name is None:
        return TextureImportResult(material.name, score=score, reason="相似度不够")

    texture_path = name_path_map[match_name]
    texture_node = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture_node.image = load_texture_image(texture_path)
    material.node_tree.links.new(texture_node.outputs["Color"], base_color_input)

    # 新贴图沿用旧贴图的 Alpha 连线 (旧贴图多为丢失的图, 只能靠连线猜用途)
    for target in alpha_targets:
        material.node_tree.links.new(texture_node.outputs["Alpha"], target)

    return TextureImportResult(material.name, str(texture_path), score)


def import_missing_texture(
    texture_dir: str | Path,
    recursive: bool = True,
    extensions: list[str] | None = None,
    exclude_dirs: Sequence[str] | None = None,
    threshold: float = DEFAULT_TEXTURE_MATCH_THRESHOLD,
    only_missing: bool = True,
    skip_masks: bool = True,
    cleanup: bool = True,
) -> TextureImportReport:
    """给材质补上 Base Color 贴图, 返回每个材质的结果

    匹配线索按可靠性排序: 旧贴图文件名 > 独占该材质的网格名 > 材质名;
    分数低于 threshold 的材质不配图, 遮罩类材质默认也不碰。
    cleanup 开启时顺手删掉换下来的丢失贴图节点与没人引用的贴图数据块。
    """
    name_path_map = get_texture_candidates(
        texture_dir, extensions=extensions, recursive=recursive, exclude_dirs=exclude_dirs
    )
    if not name_path_map:
        raise LookupError(
            f"没有可用的贴图文件\n贴图目录: {texture_dir}\n扩展名: {extensions or TEXTURE_EXTENSIONS}"
        )

    candidate_names = list(name_path_map)
    report = TextureImportReport()

    for material in bpy.data.materials:
        material.use_nodes = True

        bsdf_node = get_bsdf_node(material)
        if not bsdf_node:
            continue

        # 没接可用法线贴图的法线节点先清掉, 留着只会误导
        removed_normal_maps = remove_unused_normal_map_nodes(material) if cleanup else 0

        result: TextureImportResult | None = None
        if not (only_missing and is_image_available(get_base_color_image(material))):
            if skip_masks and is_mask_material(material):
                result = TextureImportResult(material.name, reason="遮罩类材质")
            else:
                result = match_material_texture(
                    material, name_path_map, candidate_names, threshold
                )

        # 换下来的旧贴图节点失去下游连线, 这一步一并带走
        removed_nodes = remove_missing_texture_nodes(material) if cleanup else 0
        report.removed_normal_maps += removed_normal_maps
        report.removed_nodes += removed_nodes

        if result is not None:
            report.results.append(result)

        # 节点有增删就重新摆一遍, 否则新节点会压在旧节点上
        if removed_nodes or removed_normal_maps or (result and result.path):
            arrange_nodes_layout(material.node_tree.nodes)

    if cleanup:
        report.removed_images = remove_missing_images()

    return report
