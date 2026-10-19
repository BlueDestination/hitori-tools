"""把贴图文件名里的 `.` 换成 `_` (三个智能更新流程调用, 不要单独运行)"""

import shutil

import bpy

from hitori_addon.mesh import selected_meshes
from hitori_addon.path import get_file_dir_stem_ext

LEGAL_CHAR = "_"

ILLEGAL_CHAR = "."

legalized_cache: dict[str, str] = {}

for obj in selected_meshes():
    materials = [material_slot.material for material_slot in obj.material_slots]
    for material in materials:
        for node in material.node_tree.nodes:
            if node.type != "TEX_IMAGE":
                continue

            tex = node
            if not tex.image:
                continue

            img_filepath = bpy.path.abspath(tex.image.filepath)
            file_dir, file_stem, file_ext = get_file_dir_stem_ext(img_filepath)

            if ILLEGAL_CHAR not in file_stem:
                continue

            illegal_name = file_stem
            illegal_path = img_filepath

            if illegal_name not in legalized_cache:
                legal_name = illegal_name.replace(ILLEGAL_CHAR, LEGAL_CHAR)
                legalized_cache[illegal_name] = legal_name

                legal_path = file_dir / f"{legal_name}{file_ext}"

                if not legal_path.exists():
                    shutil.copy(illegal_path, legal_path)

                tex.image = bpy.data.images.load(legal_path)
            else:
                legal_name = legalized_cache[illegal_name]
                tex.image = bpy.data.images[legal_name]
