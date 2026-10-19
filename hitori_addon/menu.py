import traceback
import unicodedata
from collections.abc import Callable, Iterable
from functools import wraps
from itertools import count
from typing import Any, ClassVar

import bpy
from bpy.types import (
    BoolProperty,
    Context,
    EnumProperty,
    Event,
    Operator,
    StringProperty,
)

from hitori_addon.error import REPORTED_ERROR_TYPES, ObjectError, UserError
from hitori_addon.path import get_default_pick_dir
from hitori_addon.settings import RUN_STATE

# 弹窗显示上限: 超出的行只显示首尾, 完整文本走"复制全部"
MAX_POPUP_LINES = 40
HEAD_POPUP_LINES = 30
TAIL_POPUP_LINES = 10
MAX_POPUP_LINE_WIDTH = 120
# 弹窗里的名字列表最多列几个 (骨骼名 / 顶点组名这类动辄上百个)
MAX_POPUP_NAMES = 24

# 待复制的完整文本 (弹窗关闭后残留, 只留最近几份, 不会累积)
_POPUP_TEXTS: dict[str, str] = {}
POPUP_TEXT_LIMIT = 4
_POPUP_KEY_COUNTER = count(1)

# 弹窗次数: 按钮跑完后据此判断脚本是否已经自己弹过反馈
POPUP_COUNT = 0


def get_popup_count() -> int:
    return POPUP_COUNT


def get_display_width(text: str) -> int:
    """显示宽度 (中日韩字符算 2 格)"""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def wrap_line(line: str) -> list[str]:
    """按显示宽度折行 (中日韩字符算 2 格)"""
    chunks: list[str] = []
    chunk = ""
    width = 0
    for char in line:
        char_width = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if width + char_width > MAX_POPUP_LINE_WIDTH:
            chunks.append(chunk)
            chunk = ""
            width = 0
        chunk += char
        width += char_width
    chunks.append(chunk)
    return chunks


def format_name_list(
    names: Iterable[str], limit: int = MAX_POPUP_NAMES, indent: str = ""
) -> str:
    """弹窗里的名字列表: 按显示宽度折行, 超过 limit 只列前 limit 个, 后面写 "... 共 N 个"

    名单动辄上百个, 全列出来会挤满弹窗并把其他信息顶出去; 折行按名字边界切, 不把名字劈成两半。
    返回的文本每行都带 indent (调用方不用再补缩进)。
    """
    names = list(names)
    budget = MAX_POPUP_LINE_WIDTH - get_display_width(indent)
    lines: list[str] = []
    line = ""
    for name in names[:limit]:
        candidate = f"{line}, {name}" if line else name
        if line and get_display_width(candidate) > budget:
            lines.append(line)
            line = name
        else:
            line = candidate
    if len(names) > limit:
        line += f" ... 共 {len(names)} 个"
    lines.append(line)
    return indent + ("\n" + indent).join(lines)


def format_popup_lines(text: str) -> tuple[list[str], int]:
    """文本转成弹窗里的行 (超长行折行, 超长文本只留首尾), 同时返回省略的行数"""
    lines = text.split("\n")
    omitted = max(len(lines) - MAX_POPUP_LINES, 0)
    head_lines = lines
    tail_lines: list[str] = []
    if omitted:
        head_lines = lines[:HEAD_POPUP_LINES]
        tail_lines = lines[-TAIL_POPUP_LINES:]
    formatted = [chunk for line in head_lines for chunk in wrap_line(line)]
    if omitted:
        # 用 ... 单行标出中间被省略, 免得看起来像正常换行
        formatted.append("...")
        formatted.extend(chunk for line in tail_lines for chunk in wrap_line(line))
    return formatted, omitted


def remember_popup_text(text: str) -> str:
    """暂存完整文本, 返回取用它的 key"""
    while len(_POPUP_TEXTS) >= POPUP_TEXT_LIMIT:
        _POPUP_TEXTS.pop(next(iter(_POPUP_TEXTS)))
    key = str(next(_POPUP_KEY_COUNTER))
    _POPUP_TEXTS[key] = text
    return key


def get_popup_text(key: str) -> str:
    """按 key 取回暂存的文本 (operator 用函数取, 热重载后拿到的是新模块的缓存)"""
    return _POPUP_TEXTS.get(key, "")


class CopyPopupText(Operator):
    """把弹窗里的完整文本复制到剪贴板"""

    bl_idname: str = "wm.copy_popup_text"
    bl_label: str = "复制全部文本"

    key: bpy.props.StringProperty()

    def execute(self, context: Context) -> set[str]:
        # 热重载后 `hitori_addon.menu` 换成新模块, 所以每次现取
        from hitori_addon import menu

        text = menu.get_popup_text(self.key)
        if not text:
            self.report({"WARNING"}, "文本已过期, 请重新运行")
            return {"CANCELLED"}
        context.window_manager.clipboard = text
        self.report({"INFO"}, f"已复制 {len(text)} 个字符")
        return {"FINISHED"}


def ensure_popup_operator() -> bool:
    """首次弹窗时注册复制按钮的 operator (已注册就跳过, 不注销重注册, 免得弄坏还开着的弹窗)"""
    if hasattr(bpy.types, "WM_OT_copy_popup_text"):
        return True
    try:
        bpy.utils.register_class(CopyPopupText)
    except (RuntimeError, ValueError):
        return False
    return True


def message_box(obj: Any = "", title: str = "", icon: str = "INFO"):
    global POPUP_COUNT
    POPUP_COUNT += 1
    text = str(obj).strip()
    if bpy.app.background:
        print(text)
        return

    lines, omitted = format_popup_lines(text)
    key = remember_popup_text(text) if text and ensure_popup_operator() else ""

    def draw_func(self, _context: Context):
        for line in lines:
            self.layout.label(text=line)
        if not key:
            return
        self.layout.separator()
        row = self.layout.row(align=True)
        row.operator(CopyPopupText.bl_idname, text="复制全部", icon="COPYDOWN").key = key
        if omitted:
            row.label(text=f"中间省略 {omitted} 行")

    bpy.context.window_manager.popup_menu(draw_func, title=title.strip(), icon=icon)


def report_error(error: Exception, title: str = "") -> None:
    """用户能看懂的错误统一弹窗提示; 不是预先判定过的错误额外在控制台留一份 traceback"""
    if not isinstance(error, ObjectError):
        print(traceback.format_exc().strip())
    message = error.message if isinstance(error, ObjectError) else str(error)
    message_box(message, title=title, icon="ERROR")


def report_errors(func: Callable) -> Callable:
    """装到 operator 的 execute 上: 用户级错误改成弹窗, 不打 traceback

    弹窗标题取按钮名 (bl_label); UserError 按约定已经自己弹过窗, 直接当取消处理
    """

    @wraps(func)
    def wrapper(self, context: Context) -> set[str]:
        try:
            return func(self, context)
        except UserError:
            return {"CANCELLED"}
        except REPORTED_ERROR_TYPES as error:
            report_error(error, title=getattr(self, "bl_label", ""))
            return {"CANCELLED"}

    return wrapper


def get_script_run_menu(
    target_func: Callable,
    enum_property: EnumProperty | None = None,
    string_property: StringProperty | None = None,
    bool_property: BoolProperty | None = None,
    string_property_2: StringProperty | None = None,
    enum_property_2: EnumProperty | None = None,
    bool_property_2: BoolProperty | None = None,
) -> type[Operator]:
    class ScriptRunMenu(Operator):
        bl_idname: str = "wm.script_run_menu"
        bl_label: str = ""
        # 带 UNDO: 确认对话框的动作整体算一个 undo 步骤 (内部 bpy.ops 不再各自压步骤)
        bl_options: ClassVar[set[str]] = {"REGISTER", "UNDO"}

        if enum_property:
            enum_input: enum_property
        if enum_property_2:
            enum_input_2: enum_property_2
        if string_property:
            string_input: string_property
        if string_property_2:
            string_input_2: string_property_2
        if bool_property:
            bool_input: bool_property
        if bool_property_2:
            bool_input_2: bool_property_2

        def invoke(self, context: Context, event: Event) -> set[str]:
            wm = context.window_manager
            return wm.invoke_props_dialog(self)

        def execute(self, context: Context) -> set[str]:
            # 参数的顺序固定为 enum, string, string2, bool, enum2, bool2
            args = []
            if enum_property:
                args.append(self.enum_input)
            if string_property:
                args.append(self.string_input)
            if string_property_2:
                args.append(self.string_input_2)
            if bool_property:
                args.append(self.bool_input)
            if enum_property_2:
                args.append(self.enum_input_2)
            if bool_property_2:
                args.append(self.bool_input_2)
            target_func(*args)

            return {"FINISHED"}

        execute = report_errors(execute)

    return ScriptRunMenu


def register_and_invoke_menu(menu_class: type[Operator]):
    # 改动在对话框确认后才发生, 调用方据此不留空的 undo 步骤
    RUN_STATE.dialog_opened = True
    bpy.utils.register_class(menu_class)

    sub_attribute_names = menu_class.bl_idname.split(".")

    sub_attribute = bpy.ops
    for sub_attribute_name in sub_attribute_names:
        sub_attribute = getattr(sub_attribute, sub_attribute_name)

    invoke_func = sub_attribute
    invoke_func("INVOKE_DEFAULT")


def register_menu_and_run(
    target_func: Callable,
    enum_property: EnumProperty | None = None,
    string_property: StringProperty | None = None,
    bool_property: BoolProperty | None = None,
    string_property_2: StringProperty | None = None,
    enum_property_2: EnumProperty | None = None,
    bool_property_2: BoolProperty | None = None,
):
    menu_class = get_script_run_menu(
        target_func,
        enum_property,
        string_property,
        bool_property,
        string_property_2,
        enum_property_2,
        bool_property_2,
    )
    register_and_invoke_menu(menu_class)


class DirectoryPicker(Operator):
    bl_idname: str = "wm.directory_picker"
    bl_label: str = "选择当前文件夹"

    directory: bpy.props.StringProperty(subtype="DIR_PATH")

    def execute(self, context: Context) -> set[str]:
        message_box(self.directory)
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        if not self.directory:
            default_dir = get_default_pick_dir()
            if default_dir is not None:
                self.directory = default_dir.as_posix() + "/"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
