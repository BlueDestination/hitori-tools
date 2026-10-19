"""把选中的眼线网格沿 Y 轴正交投影到 kk_eyeline 的 uv 布局上, 生成眼线贴图

正视图里颜色只与世界坐标 (x, z) 有关, 与 y 无关, 所以目标网格表面点 (x, z) 在源网格正视图里的颜色
就是投影结果. 与源网格有没有厚度 / 有几层结构无关, 不需要缩裹, 也不需要烘焙.
脚本只做贴图处理: 不新建 / 不改动场景里的物体、相机和渲染设置; 模板材质只换贴图节点上的贴图
(材质里没有贴图节点时按原来的兜底逻辑新建一个).
源网格可以带多个材质槽, 按三角形所属材质分别取贴图; 源贴图带 alpha 时透明处会一起投影过来.
投影结果写进工程目录, 并写进人物卡的 Material Editor 数据(材质主贴图), 并让游戏重载该卡.
"""

import tempfile
from pathlib import Path

import bpy
import numpy as np

from hitori_addon.card import get_card_path, reload_kk_card, set_material_editor_texture
from hitori_addon.error import ObjectError
from hitori_addon.image import backup_image_file, img_to_kk_color, set_named_image
from hitori_addon.material import (
    ensure_alpha_clip,
    get_source_image,
    get_texture_material_and_node,
)
from hitori_addon.menu import message_box, register_and_invoke_menu, report_errors
from hitori_addon.mesh import selected_meshes
from hitori_addon.obj import get_obj
from hitori_addon.path import get_blend_file_dir, get_blend_file_stem
from hitori_addon.projection import project
from hitori_addon.template_link import EYELINE_NAME

TEMPLATE_NAME = EYELINE_NAME
TITLE = "写入眼线贴图"
IMAGE_NAME = "kk_eyeline"
# 人物卡 Material Editor 里要写入的眼线材质(头模自带的官方眼线材质)
CARD_MATERIAL_NAME = "cf_m_eyeline_00_up"
IMG_SIZE = 512


class ProjectEyelineMenu(bpy.types.Operator):
    """把选中网格正交投影到 kk_eyeline 的贴图"""

    bl_idname = "wm.eyeline_bake_menu"
    bl_label = "写入眼线贴图"

    @report_errors
    def execute(self, context):
        main()
        return {"FINISHED"}


def main():
    objs = selected_meshes()
    if len(objs) != 1:
        raise ObjectError(objs, "请只选中一个眼线网格")

    src_obj = objs[0]
    template = get_obj(TEMPLATE_NAME)
    if not template:
        raise ObjectError(objs, f"场景中找不到模板物体 {TEMPLATE_NAME}")
    if src_obj is template:
        raise ObjectError(objs, "请选中眼线网格, 而不是模板")
    if src_obj.mode != "OBJECT" or template.mode != "OBJECT":
        raise ObjectError(objs, "请先退出编辑模式")

    images = [get_source_image(slot.material) for slot in src_obj.material_slots]
    if not any(images):
        raise ObjectError(objs, "源网格的材质里找不到贴图")

    material, texture_node = get_texture_material_and_node(template, TEMPLATE_NAME)
    old_image = texture_node.image
    old_size = old_image.size if old_image else ()
    size = old_size if len(old_size) == 2 and all(old_size) else (IMG_SIZE, IMG_SIZE)

    pixels, coverage = project(src_obj, template, size, images, IMG_SIZE)
    if coverage < 0.01:
        raise ObjectError(
            objs, f"源网格与 {TEMPLATE_NAME} 在正视图中没有重合, 检查选中物体和朝向"
        )

    img_path = get_blend_file_dir() / f"{IMAGE_NAME}.png"
    image = bpy.data.images.new("kk_eyeline_projection", size[0], size[1], alpha=True)
    image.pixels.foreach_set(np.ascontiguousarray(pixels[::-1], dtype="f4").ravel())

    try:
        # 保存贴图到工程目录(不覆盖模板原贴图)
        backup_image_file(img_path)
        image.save(filepath=str(img_path))
    except Exception:
        bpy.data.images.remove(image)
        raise

    # 新贴图接进模板原有材质的贴图节点(保留材质本身及其透明设置)
    set_named_image(texture_node, image, img_path, IMAGE_NAME)

    ensure_alpha_clip(material, texture_node)
    print(f"眼线贴图已保存到: {img_path}")
    write_eyeline_to_card(img_path, CARD_MATERIAL_NAME)
    return image


def write_eyeline_to_card(img_path, material_name):
    """把投影好的眼线贴图转成游戏颜色后写进默认人物卡, 并让游戏重载该卡"""
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
        card_image_path = Path(temp_dir) / f"{IMAGE_NAME}.png"
        img_to_kk_color(img_path, card_image_path, "PNG")
        set_material_editor_texture(card_path, material_name, card_image_path)
    if not reload_kk_card(card_path):
        message_box(
            f"贴图已写入人物卡, 但游戏重载失败(游戏可能没在运行):\n{card_path}",
            title=TITLE,
            icon="ERROR",
        )
    print(f"眼线贴图已写入人物卡: {card_path}")


if __name__ == "__main__":
    register_and_invoke_menu(ProjectEyelineMenu)
