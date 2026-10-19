"""注册服装动骨接骨: 按根骨子树里有权的服装网格自动判断类型, 写进 u3d 并热重载, 完成后弹窗列出写了哪些

类型不看骨名(`<type>_root` 命名不再需要): 根骨子树 ∩ 有权重的服装网格 -> 网格名 -> 类型。
只挂在饰品 / 非法网格名(如 `_pants`)上的链没有类型, 跳过并在弹窗里列出来。
"""

from hitori_addon.bonegroup import get_group_bone_names
from hitori_addon.const import ABDATA_DIR
from hitori_addon.dynbone import ROOT_BONE_GROUP_NAME, find_cloth_root_bone_types
from hitori_addon.error import UserError
from hitori_addon.hotreload import update_and_refresh_mod
from hitori_addon.menu import format_name_list, message_box
from hitori_addon.obj import get_obj
from hitori_addon.path import get_blend_file_stem
from hitori_addon.template_link import ARMATURE_NAME
from hitori_addon.u3d import (
    RootBonesError,
    format_root_bones_report,
    register_u3d_root_bones,
)

TITLE = "注册服装动骨接骨"

arm = get_obj(ARMATURE_NAME)

root_bone_names = get_group_bone_names(arm, ROOT_BONE_GROUP_NAME)
if not root_bone_names:
    message = (
        f"没有找到接骨根骨 (`{ROOT_BONE_GROUP_NAME}` 骨骼组是空的), 未写入动骨接骨\n"
        "请先接骨, 再注册"
    )
    message_box(message, title=TITLE, icon="ERROR")
    raise UserError(message)

root_bone_infos = find_cloth_root_bone_types(arm, root_bone_names)

# 一条链同时挂在多种服装的网格上: 分不出类型, 注册进去游戏里会跟错衣服
conflict_lines = [
    f"    {root_bone_name}: {', '.join(sorted(info.cloth_types))}"
    for root_bone_name, info in root_bone_infos.items()
    if len(info.cloth_types) > 1
]
if conflict_lines:
    message = (
        "这些根骨的动骨同时挂在多种服装的网格上, 分不出类型, 未写入动骨接骨\n"
        "请拆开权重 (一条链只服务一种服装) 后重跑\n" + "\n".join(conflict_lines)
    )
    message_box(message, title=TITLE, icon="ERROR")
    raise UserError(message)

cloth_root_bones: dict[str, list[str]] = {}
skipped_lines: list[str] = []
for root_bone_name, info in root_bone_infos.items():
    if not info.cloth_types:
        mesh_names = format_name_list(sorted(info.mesh_names), limit=6) or "没有任何权重"
        skipped_lines.append(f"    {root_bone_name} -> {mesh_names}")
        continue
    cloth_root_bones.setdefault(info.cloth_types.pop(), []).append(root_bone_name)

if not cloth_root_bones:
    message = (
        "这些根骨都没有挂在可导出的服装网格上, 未写入动骨接骨\n"
        "请先给服装网格命名 (如 cloth_top / sock), 饰品请用饰品注册\n"
        + "\n".join(skipped_lines)
    )
    message_box(message, title=TITLE, icon="ERROR")
    raise UserError(message)

chara_name = get_blend_file_stem()
u3d_path = ABDATA_DIR / f"{chara_name}.unity3d"

try:
    reports = register_u3d_root_bones(u3d_path, cloth_root_bones)
except RootBonesError as error:
    message_box(str(error), title=TITLE, icon="ERROR")
    raise UserError(str(error)) from error

# u3d 里没有"链挂了哪些网格", 弹窗的来源按自动分类结果补上
for cloth_type, typed_root_bone_names in cloth_root_bones.items():
    reports[cloth_type].mesh_names = {
        mesh_name
        for root_bone_name in typed_root_bone_names
        for mesh_name in root_bone_infos[root_bone_name].mesh_names
    }

update_and_refresh_mod(u3d_path)

text, is_written = format_root_bones_report("服装", u3d_path.name, reports)

if skipped_lines:
    text += "\n跳过 (没挂在可导出的服装网格上, 命中的网格见行末):\n" + "\n".join(
        skipped_lines
    )

message_box(text, title=TITLE, icon="INFO" if is_written else "ERROR")
