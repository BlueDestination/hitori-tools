import bpy
from bpy.types import VertexGroups

from hitori_addon.menu import message_box, register_menu_and_run
from hitori_addon.mesh import selected_meshes
from hitori_addon.vg import get_vg_names, merge_vgs

TITLE = "合并顶点组"
HEADER = "已完成顶点组合并,原顶点组保留,只展示有合并发生的:"
MERGED_GROUP_NAME = "merged_group"


def get_unique_vg_name(obj_vgs: VertexGroups) -> str:
    """不覆盖已有的组: 重名时按 Blender 习惯加 .001 / .002 后缀"""
    if obj_vgs.get(MERGED_GROUP_NAME) is None:
        return MERGED_GROUP_NAME
    index = 1
    while obj_vgs.get(f"{MERGED_GROUP_NAME}.{index:03d}"):
        index += 1
    return f"{MERGED_GROUP_NAME}.{index:03d}"


def main(enum_input: str, string_input: str):
    objs = selected_meshes()
    if not objs:
        message_box("请先选中网格", title=TITLE, icon="ERROR")
        return

    vg_sub_names = string_input.split(",")
    inverse = enum_input != "合并"
    lines = [HEADER]
    for obj in objs:
        obj_vgs = obj.vertex_groups
        merge_vg_names = [
            vg_name
            for vg_name in get_vg_names(obj)
            if any(vg_sub_name in vg_name for vg_sub_name in vg_sub_names)
        ]
        new_vg_name = get_unique_vg_name(obj_vgs)
        merge_vgs(
            obj, merge_vg_names, new_vg_name, inverse=inverse, overwrite=False
        )

        if not obj_vgs.get(new_vg_name):
            continue
        if merge_vg_names:
            detail = ", ".join(merge_vg_names)
        elif inverse:
            detail = "没有组参与, 全部顶点权重 1"
        else:
            continue
        lines.append(f"--- {obj.name} ---")
        lines.append(f"{new_vg_name}: {detail}")
        lines.append("")

    message_box("\n".join(lines).strip(), title=TITLE)


enum_property = bpy.props.EnumProperty(
    name="合并模式",
    description=(
        "合并: 参与组权重相加写入 " + MERGED_GROUP_NAME + "; "
        "取反: 写入 1 - 权重和, 即没被这些组加权的顶点 = 1; "
        "已有的组不覆盖, 重名自动加 .001 后缀; 参与组本身不删"
    ),
    items=[
        ("合并", "合并", "参与组的权重相加, 写入 " + MERGED_GROUP_NAME),
        ("取反", "取反", "写入 1 - 权重和, 没被这些组加权的顶点权重为 1"),
    ],
    default="取反",
)
string_property = bpy.props.StringProperty(
    name="合并关键词(','分隔)",
    description=(
        "顶点组名包含任一关键词就参与 (子串匹配, 不要求完整匹配, 英文逗号分隔); "
        "留空 = 选中网格的全部顶点组"
    ),
    default="",
)

register_menu_and_run(main, enum_property, string_property)
