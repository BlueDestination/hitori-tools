import time
from dataclasses import dataclass
from typing import ClassVar

import bpy
from bpy.props import EnumProperty

from hitori_addon.autoreload import reload_if_changed
from hitori_addon.error import REPORTED_ERROR_TYPES
from hitori_addon.menu import get_popup_count, message_box, report_error
from hitori_addon.run import REPEAT_LAST_SCRIPT, run_addon_script
from hitori_addon.settings import RUN_STATE

bl_info = {
    "name": "hitori_addon_ui",
    "category": "Object",
    "version": (5, 0),
    "blender": (2, 80, 0),
    "location": "View3D",
}


SEPARATOR: str | None = None


@dataclass
class Button:
    name: str | None = None
    # 无脚本的手动步骤按钮, 标识留空
    identifier: str | None = None
    description: str = ""
    # 跑完是否补一条"运行完成"弹窗; 高频切换类 / 自己会开对话框的脚本设 False
    feedback: bool = True

    def to_enum_item(self) -> tuple[str, str, str] | None:
        """枚举项; name 留空的返回 None, Blender 会把这一项画成分隔线"""
        if self.name is None:
            return None
        # 枚举标识不能为空且需唯一, 手动步骤用名称占位
        return self.identifier or self.name, self.name, self.description


def find_button(buttons: tuple[Button, ...], enum_input: str) -> Button:
    """按枚举标识找按钮 (分隔符没有标识, 会被跳过)"""
    for button in buttons:
        item = button.to_enum_item()
        if item and item[0] == enum_input:
            return button
    raise RuntimeError(f"未知按钮: {enum_input}")


def run_button(button: Button) -> set[str]:
    """运行按钮的脚本, 手动步骤只弹窗提示; 返回 FINISHED 才给这次运行压 undo 步骤"""
    if button.identifier is None:
        message_box(f"{button.name}\n\n该步骤需要自己操作, 没有可运行的脚本")
        # 不会改数据, 不留 undo 步骤
        return {"CANCELLED"}
    # lib 代码改过就先热重载(配置里开了才检查), 保证按钮总是跑最新代码
    reload_if_changed()
    popup_count = get_popup_count()
    start = time.perf_counter()
    RUN_STATE.dialog_opened = False
    try:
        run_addon_script(button.identifier)
    except REPORTED_ERROR_TYPES as error:
        # 脚本的报错统一弹窗提示, 不让 Blender 打长 traceback
        report_error(error, title=button.name)
    # 脚本自己弹过窗(结果 / 报错 / 对话框)就不再补一条, 免得挡住用户
    if button.feedback and get_popup_count() == popup_count:
        message_box(f"{button.name}\n用时 {time.perf_counter() - start:.2f} 秒", title="运行完成")
    # 只弹出了对话框: 真正的改动在确认对话框时发生, 那时才压 undo 步骤
    return {"CANCELLED"} if RUN_STATE.dialog_opened else {"FINISHED"}


class HitoriAddonButtonMenu(bpy.types.Operator):
    """按钮菜单基类: 子类只需定义 bl_idname / bl_label / buttons"""

    bl_property = "enum_input"
    # 带 UNDO: 整个按钮算一个 undo 步骤 (内部 bpy.ops 不再各自压步骤)
    bl_options: ClassVar[set[str]] = {"REGISTER", "UNDO"}

    buttons: tuple[Button, ...] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 枚举项来自子类的 buttons; Blender 在注册时才读 annotations, 分隔符是 None 项
        if "__annotations__" not in cls.__dict__:
            cls.__annotations__ = {}
        cls.__annotations__["enum_input"] = EnumProperty(
            items=[button.to_enum_item() for button in cls.buttons]
        )

    def execute(self, _context):
        # CANCELLED 不压 undo 步骤: 只开了对话框 / 没跑脚本时本次没有改动
        return run_button(find_button(self.buttons, self.enum_input))


class HitoriAddonPluginMenu(bpy.types.Menu):
    bl_idname = "HITORIADDON_MT_PLUGIN_MENU"
    bl_label = "插件"

    def draw(self, context):
        self.layout.operator_enum(MainMenu.bl_idname, property=MainMenu.bl_property)
        for menu in SUBMENUS:
            self.layout.operator_menu_enum(menu.bl_idname, property=menu.bl_property)


class MainMenu(HitoriAddonButtonMenu):
    bl_idname = "hitori_addon.main_menu"
    bl_label = "常用"

    buttons: tuple[Button, ...] = (
        Button("重复上次操作", REPEAT_LAST_SCRIPT, feedback=False),
        Button("★服装智能更新mod", "cloth_export_update_mod.py"),
        Button("★饰品智能更新mod", "acc_export_update_mod.py"),
        Button("备份物体", "backup_objects.py"),
        Button("显示穿模顶点组", "show_clipping_vgroups.py", feedback=False),
        Button("显示官方身体", "show_official_body.py", feedback=False),
        Button(SEPARATOR),
    )


class StepMenu(HitoriAddonButtonMenu):
    bl_idname = "hitori_addon.step_menu"
    bl_label = "移植步骤"

    buttons: tuple[Button, ...] = (
        Button("▲符号需自己操作"),
        Button(SEPARATOR),
        Button("↓导入外部模型", "import_external_model.py", feedback=False),
        Button("↓备份删除无用mmd材质网格", "backup_delete_useless_mmd_meshes.py"),
        Button("↓命名服装饰品", "name_clothes.py"),
        Button("↓追加官模头模眼线", "append_official_head_eyeline.py", feedback=False),
        Button("↓对齐官方骨架", "align_official_armature.py"),
        Button(SEPARATOR),
        Button("↓合并重合顶点", "merge_doubles_sharp_edges.py", feedback=False),
        Button("↓归一化权重 (改原权重)", "normalize_weights.py"),
        Button("↓构建user_edit_key", "build_user_edit_key.py"),
        Button("↓构建skip_transfer_group", "build_skip_transfer_group.py"),
        Button("↓▲服装贴合"),
        Button("↓▲服装第二状态"),
        Button("↓生成动骨骨架", "dynbone_cleanup.py"),
        Button("↓动骨骨架接骨", "dynbone_join_bones.py"),
        Button("↓初始化mod", "init_mod.py", feedback=False),
        Button("→★更新服装mod", "cloth_export_update_mod.py"),
        Button("↓注册服装动骨接骨", "register_cloth_dynbones.py"),
        Button(SEPARATOR),
        Button("→★更新饰品mod", "acc_export_update_mod.py"),
        Button("↓注册饰品动骨", "register_acc_dynbones.py"),
        Button("↓▲游戏内设置饰品父级并对齐"),
        Button(SEPARATOR),
        Button("↓写入瞳孔贴图", "write_pupil_texture.py", feedback=False),
        Button("↓写入眼线贴图", "write_eyeline_texture.py", feedback=False),
        Button("→查看捏脸指南", "face_guide.py"),
        Button(SEPARATOR),
        Button("→发布人物卡和mod", "release_card_and_mod.py"),
    )


class ClothMenu(HitoriAddonButtonMenu):
    bl_idname = "hitori_addon.cloth_menu"
    bl_label = "服装工具"

    buttons: tuple[Button, ...] = (
        Button("自动缩裹烘焙", "auto_shrinkwrap_bake.py", feedback=False),
        Button("衣物形变(需外部身体缩裹)", "deform_clothes_shrinkwrap_body.py"),
        Button("衣物缩裹", "shrinkwrap_to_template.py"),
        Button(SEPARATOR),
        Button("拆分上下双状态网格", "split_upper_lower_meshes.py"),
    )


class VgroupMenu(HitoriAddonButtonMenu):
    bl_idname = "hitori_addon.vgroup_menu"
    bl_label = "顶点组"

    buttons: tuple[Button, ...] = (
        Button("构建整网格skip_transfer_group", "build_full_skip_transfer_group.py"),
        Button("合并顶点组", "merge_vgroups.py", feedback=False),
        Button("合并vrc/mmd权重到kk顶点组", "merge_vrc_mmd_weights_to_kk.py"),
        Button(SEPARATOR),
        Button("删除空顶点组", "delete_empty_vgroups.py"),
    )


class BoneMenu(HitoriAddonButtonMenu):
    bl_idname = "hitori_addon.bone_menu"
    bl_label = "骨骼"

    buttons: tuple[Button, ...] = (
        Button("骨骼姿势水平化", "pose_horizontal.py", feedback=False),
        Button("骨骼姿势镜像", "pose_mirror.py", feedback=False),
        Button(SEPARATOR),
        Button("添加叶骨", "add_leaf_bones.py"),
        Button(SEPARATOR),
        Button("骨架优化显示", "armature_optimize_display.py", feedback=False),
    )


class MaterialMenu(HitoriAddonButtonMenu):
    bl_idname = "hitori_addon.material_menu"
    bl_label = "材质"

    buttons: tuple[Button, ...] = (
        Button("材质寻找缺失贴图", "find_missing_textures.py"),
        Button(SEPARATOR),
        Button("统一UV层", "unify_uv_layers.py"),
    )


class DevMenu(HitoriAddonButtonMenu):
    bl_idname = "hitori_addon.dev_menu"
    bl_label = "开发调试"

    buttons: tuple[Button, ...] = (
        Button("启动游戏", "launch_game.py", feedback=False),
        Button("运行测试", "run_tests.py", feedback=False),
        Button("生成调试脚本", "gen_debug_script.py"),
        Button(SEPARATOR),
        Button("清除历史记录", "clear_history.py", feedback=False),
    )


class HeadmodMenu(HitoriAddonButtonMenu):
    bl_idname = "hitori_addon.headmod_menu"
    bl_label = "头模步骤"

    buttons: tuple[Button, ...] = (
        Button("↓▲对齐头模脖子接缝"),
        Button("↓头模初始化", "headmod_init.py"),
        Button("↓▲编辑生成的neck材质面积"),
        Button("↓构建表情布局", "build_expression_layout.py"),
        Button("↓形态键添加序号", "shapekey_add_numbers.py"),
        Button("↓渲染形态键截图", "render_shapekey_screenshots.py"),
        Button("★头模智能更新mod", "headmod_export_update_mod.py"),
        Button(SEPARATOR),
        Button("生成眼睛表情e22-27", "gen_eye_expressions_e22_27.py"),
        Button("生成嘴巴表情m25-36", "gen_mouth_expressions_m25_36.py"),
        Button("生成嘴巴表情mc25-36", "gen_mouth_expressions_mc25_36.py"),
    )


SUBMENUS: tuple[type, ...] = (
    StepMenu,
    ClothMenu,
    VgroupMenu,
    BoneMenu,
    MaterialMenu,
    DevMenu,
    HeadmodMenu,
)

ALL_MENUS: tuple[type, ...] = (HitoriAddonPluginMenu, MainMenu) + SUBMENUS


def plugin_menu_draw_func(self, _context):
    self.layout.menu(HitoriAddonPluginMenu.bl_idname)


def register():
    for menu in ALL_MENUS:
        bpy.utils.register_class(menu)
    bpy.types.VIEW3D_HT_header.prepend(plugin_menu_draw_func)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(plugin_menu_draw_func)
    for menu in reversed(ALL_MENUS):
        bpy.utils.unregister_class(menu)


if __name__ == "__main__":
    register()
