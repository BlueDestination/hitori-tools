import os
import shutil

import bpy
import numpy as np

from hitori_addon.const import IDENTITY_CAMERA_ORTHOGONAL_SCALE, SHAPEKEY_SCREENSHOT_DIR
from hitori_addon.mesh import get_axis_range, get_keys
from hitori_addon.obj import (
    create_obj,
    get_objs,
    hide_render_objs,
    select_obj,
    set_mode,
)
from hitori_addon.path import get_blend_file_stem, legalize_filename

# 添加对齐物体的正交摄像机
MARGIN_RATIO = 0.1

obj = bpy.context.object
obj_z_range = get_axis_range(obj, axis="z", local=False)
obj_height = obj_z_range[1] - obj_z_range[0]
obj_z_center = float(np.mean(obj_z_range))

camera = create_obj("Camera", "CAMERA")
bpy.context.scene.camera = camera

set_mode("OBJECT")
select_obj(camera)
bpy.ops.view3d.object_as_camera()

camera.rotation_euler.x = 1.5708
camera.location = (0, -1, obj_z_center)

camera.data.type = "ORTHO"
camera.data.ortho_scale = (
    obj_height * IDENTITY_CAMERA_ORTHOGONAL_SCALE * (1 + MARGIN_RATIO)
)

# 设置渲染属性
scene = bpy.context.scene

render = scene.render
render.engine = "BLENDER_WORKBENCH"

workbench = scene.display
workbench.shading.light = "FLAT"
workbench.shading.color_type = "TEXTURE"

# 隐藏渲染其他物体
hide_render_objs(get_objs())
obj.hide_render = False

# 开始渲染形态键截图
chara_name = get_blend_file_stem()
output_dir = SHAPEKEY_SCREENSHOT_DIR / chara_name

keys = get_keys(obj)

for key in keys:
    key.value = 1
    img_name = legalize_filename(key.name) + ".png"
    scene.render.filepath = str(output_dir / img_name)
    bpy.ops.render.render(write_still=True)
    key.value = 0

# 创建常用表情分类文件夹
common_expression_types: tuple[str, ...] = ("b", "e", "m", "mc")
other_expression_types: tuple[str, ...] = ("瞳孔", "特殊", "无用")

for expression_type in common_expression_types + other_expression_types:
    os.makedirs(output_dir / expression_type, exist_ok=True)

# 复制默认表情到常用分类文件夹中
default_expression_filepath = output_dir / f"{legalize_filename(keys[0].name)}.png"

for expression_type in common_expression_types:
    shutil.copy(default_expression_filepath, output_dir / expression_type)

# 打开输出文件夹
os.startfile(output_dir)
