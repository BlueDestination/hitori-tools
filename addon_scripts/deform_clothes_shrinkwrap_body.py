"""让衣物跟随 vrc/mmd 身体形变

用法: 选中 1 个 vrc/mmd 身体网格(名称包含 "body") + 若干衣物网格 -> 服装工具 -> 衣物形变
效果:
    · 每个衣物网格加 SurfaceDeform(目标为身体) 并绑定, 再补一个 CorrectiveSmooth
    · 衣物绑定时反转 skip_transfer_group 当掩码: 标过的顶点不跟身体形变 (与导出时不传权重的掩码一致)
    · 身体网格加 Shrinkwrap(目标为 bodytight), 追加后隐藏身体
要求:
    · 场景里已有 bodytight (先显示官方身体; 身体要先缩裹好再运行本脚本, 否则衣物跟着旧形态走)
    · 衣物 / 身体网格都没加过本脚本的修改器 (重复运行要先删掉或撤销)
"""

import bpy
from bpy.types import Object

from hitori_addon.error import ObjectError
from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.obj import (
    get_obj,
    hide_obj,
    select_obj,
    select_objs,
    set_mode,
    show_obj,
)
from hitori_addon.template_link import BODYTIGHT_NAME, SKIP_TRANSFER_GROUP_NAME

TITLE = "衣物形变"


def get_bodytight() -> Object:
    bodytight = get_obj(BODYTIGHT_NAME)
    if bodytight is None or bodytight.type != "MESH":
        raise ObjectError([], f"场景里没有 {BODYTIGHT_NAME} 网格, 请先显示官方身体")
    return bodytight


def require_faces(objs: list[Object]) -> None:
    """没有面的网格既不能绑定也不能当投影目标"""
    empty = [obj for obj in objs if not obj.data.polygons]
    if empty:
        raise ObjectError(empty, "网格没有面, 无法参与形变")


def require_not_deformed(body: Object, clothes: list[Object], bodytight: Object) -> None:
    """已经加过就报错, 避免叠第二套修改器"""
    deformed = [
        obj
        for obj in clothes
        if any(
            mod.type == "SURFACE_DEFORM" and mod.target == body
            for mod in obj.modifiers
        )
    ]
    if deformed:
        raise ObjectError(deformed, "已有绑定到这个身体的 SurfaceDeform, 请先删除或撤销上次运行")

    wrapped = [
        obj
        for obj in (body,)
        if any(
            mod.type == "SHRINKWRAP" and mod.target == bodytight for mod in obj.modifiers
        )
    ]
    if wrapped:
        raise ObjectError(
            wrapped, f"身体已有缩裹到 {bodytight.name} 的 Shrinkwrap, 请先删除或撤销上次运行"
        )


def get_body_and_clothes(bodytight: Object) -> tuple[Object, list[Object]]:
    objs = selected_meshes()
    if not objs:
        raise ObjectError(objs, "请选中 1 个身体网格(名称包含 body)和要形变的衣物网格")

    if bodytight in objs:
        raise ObjectError(bodytight, f"{BODYTIGHT_NAME} 是缩裹基准, 不要选中它")

    body_objs = [obj for obj in objs if "body" in obj.name.lower()]
    if not body_objs:
        raise ObjectError(objs, '没有选中 vrc/mmd 的身体网格(名称包含 "body" 的网格)')
    if len(body_objs) > 1:
        raise ObjectError(body_objs, "只能选中 1 个身体网格")

    body = body_objs[0]
    clothes = [obj for obj in objs if obj is not body]
    if not clothes:
        raise ObjectError(objs, "只选中了身体网格, 没有要形变的衣物网格")

    require_faces([body, *clothes])
    require_not_deformed(body, clothes, bodytight)
    return body, clothes


def bind_clothes(obj: Object, body: Object) -> None:
    """衣物绑定到身体上, 再补一个平滑减少形变后的褶皱"""
    modifier = obj.modifiers.new(name="SurfaceDeform", type="SURFACE_DEFORM")
    modifier.target = body
    # skip_transfer_group 的顶点自带权重(归自己的动骨), 这里也不跟身体形变, 与导出时的不传权重掩码一致
    # 组缺失 / 为空时这行静默成 "", 等同整片绑定
    modifier.vertex_group = SKIP_TRANSFER_GROUP_NAME
    modifier.invert_vertex_group = True
    modifier.show_in_editmode = True
    modifier.show_on_cage = True

    select_obj(obj)
    bpy.ops.object.surfacedeform_bind(modifier=modifier.name)
    if not modifier.is_bound:
        obj.modifiers.remove(modifier)
        raise ObjectError(obj, f"绑定到 {body.name} 失败, 检查身体网格是否可用")

    modifier = obj.modifiers.new(name="CorrectiveSmooth", type="CORRECTIVE_SMOOTH")
    modifier.show_in_editmode = True
    modifier.show_on_cage = True


def count_mask_verts(obj: Object) -> int:
    """skip_transfer_group 里有非零权重的顶点数 (组缺失 / 空组返回 0)"""
    vg = obj.vertex_groups.get(SKIP_TRANSFER_GROUP_NAME)
    if vg is None:
        return 0
    vg_index = vg.index
    return sum(
        1
        for vertex in obj.data.vertices
        if any(
            group.group == vg_index and group.weight for group in vertex.groups
        )
    )


def shrinkwrap_body(body: Object, bodytight: Object) -> None:
    """身体追加缩裹(排在已有修改器之后), 衣物跟着缩裹后的形态走"""
    modifier = body.modifiers.new(name="Shrinkwrap", type="SHRINKWRAP")
    modifier.wrap_method = "TARGET_PROJECT"
    modifier.wrap_mode = "ABOVE_SURFACE"
    modifier.target = bodytight
    modifier.show_in_editmode = True
    modifier.show_on_cage = True


def main():
    set_mode("OBJECT")

    bodytight = get_bodytight()
    body, clothes = get_body_and_clothes(bodytight)

    # 绑定要求目标可用, 身体最后会重新隐藏
    show_obj(body)
    for obj in clothes:
        bind_clothes(obj, body)
    shrinkwrap_body(body, bodytight)

    select_objs(clothes)
    hide_obj(body)

    lines = [
        f"身体: {body.name} 已缩裹到 {bodytight.name}, 并隐藏",
        f"衣物 {len(clothes)} 个已绑定 SurfaceDeform + CorrectiveSmooth:",
        *[f"  {obj.name}" for obj in clothes],
    ]
    masked: list[tuple[Object, int]] = []
    for obj in clothes:
        count = count_mask_verts(obj)
        if count:
            masked.append((obj, count))
    if masked:
        lines.append(
            f"按 skip_transfer_group 不跟形变: {len(masked)} 个网格 / "
            f"{sum(count for _, count in masked)} 个顶点"
        )
        lines.extend(f"  {obj.name}: {count}" for obj, count in masked)

    lines.extend(
        [
            "",
            "身体缩裹的 offset 在修改器里调(默认 0 = 贴合 bodytight)",
        ]
    )
    message_box("\n".join(lines), title=TITLE)


if __name__ == "__main__":
    main()
