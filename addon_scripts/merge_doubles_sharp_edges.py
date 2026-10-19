"""合并选中网格的重合顶点

运行会弹窗询问重合距离和是否合并锐边, 取消弹窗则不做任何操作。
合并锐边: 合并后按顶点法线判断哪些边原本是硬边(法线有折角), 自动给这些边标上锐边,
避免光滑着色把原本硬边的接缝抹平。
隐藏的几何不参与合并也不会被显示出来; 结束时取消选择所有顶点, 并把模式和顶点/边/面
选择模式恢复成运行前的样子。
"""

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty

from hitori_addon.menu import message_box, register_and_invoke_menu, report_errors
from hitori_addon.obj import set_mode

THRESHOLD_PROPERTY = FloatProperty(
    name="重合距离",
    description="距离小于该值的顶点会被合并(单位米), 数值越小合并得越保守",
    default=0.0001,
    min=0.0,
    soft_max=0.01,
    precision=6,
)

SHARP_PROPERTY = BoolProperty(
    name="合并锐边",
    description="按合并前的顶点法线, 自动给原本的硬边标上锐边",
    default=True,
)


def get_counts(objects: list) -> tuple[int, int]:
    """参与编辑的网格共有的 (顶点数, 锐边数), 隐藏的顶点也算"""
    vertex_count = sharp_edge_count = 0
    for obj in objects:
        bm = bmesh.from_edit_mesh(obj.data)
        vertex_count += len(bm.verts)
        sharp_edge_count += sum(1 for edge in bm.edges if not edge.smooth)
        bm.free()
    return vertex_count, sharp_edge_count


def main(threshold: float = 0.0001, sharp: bool = True) -> tuple[int, int, int, int]:
    """合并重合顶点, 返回 (合并前顶点, 顶点减少, 锐边增加, 合并后锐边)

    只选可见几何(不 reveal 隐藏部分), 结束时取消选择并还原模式与选择模式。
    """
    context = bpy.context
    previous_mode = context.active_object.mode if context.active_object else "OBJECT"
    previous_select_mode = tuple(context.tool_settings.mesh_select_mode)

    set_mode("EDIT")
    try:
        context.tool_settings.mesh_select_mode = (True, False, False)
        bpy.ops.mesh.select_all(action="SELECT")

        objects = list(context.objects_in_mode_unique_data)
        vertex_before, sharp_before = get_counts(objects)
        bpy.ops.mesh.remove_doubles(
            threshold=threshold, use_sharp_edge_from_normals=sharp
        )
        vertex_after, sharp_after = get_counts(objects)
    finally:
        bpy.ops.mesh.select_all(action="DESELECT")
        context.tool_settings.mesh_select_mode = previous_select_mode
        set_mode(previous_mode)

    return (
        vertex_before,
        vertex_before - vertex_after,
        sharp_after - sharp_before,
        sharp_after,
    )


class MergeDoublesMenu(bpy.types.Operator):
    """按弹窗里的参数合并重合顶点, 取消则不做任何操作"""

    bl_idname = "wm.merge_doubles_menu"
    bl_label = "合并重合顶点"

    threshold: THRESHOLD_PROPERTY
    sharp: SHARP_PROPERTY

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "threshold")
        self.layout.prop(self, "sharp")
        self.layout.label(text="对所有选中网格生效")

    @report_errors
    def execute(self, context):
        vertex_before, vertex_removed, sharp_added, sharp_after = main(
            self.threshold, self.sharp
        )
        message_box(
            f"重叠顶点: {vertex_before} -> {vertex_before - vertex_removed}"
            f" (减少 {vertex_removed})\n"
            f"锐边: {sharp_after} (增加 {sharp_added})",
            title="合并重合顶点",
        )
        return {"FINISHED"}


if __name__ == "__main__":
    register_and_invoke_menu(MergeDoublesMenu)
