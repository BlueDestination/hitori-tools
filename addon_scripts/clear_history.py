"""清除 Blender 的历史记录

三项可分: 文件浏览器的书签目录 / 近期目录 (同在 bookmarks.txt 的两段),
近期打开的文件 (recent-files.txt)。
改完文件调 wm.read_history 让运行中的 Blender 重新读盘, 否则内存里的旧列表
会在下次收藏 / 打开文件时把刚清掉的内容写回文件。
"""

from pathlib import Path

import bpy
from bpy.props import BoolProperty
from bpy.types import Context, Event, Operator

from hitori_addon.menu import message_box, register_and_invoke_menu, report_errors

BOOKMARKS_FILE = "bookmarks.txt"
RECENT_FILES_FILE = "recent-files.txt"
SECTION_BOOKMARKS = "[Bookmarks]"
SECTION_RECENT = "[Recent]"


def get_config_path(file_name: str) -> Path:
    """Blender 用户配置目录下的配置文件 (便携版在 <Blender>/<版本>/config)"""
    return Path(bpy.utils.user_resource("CONFIG")) / file_name


def clear_bookmark_sections(
    path: Path, clear_bookmarks: bool, clear_recent_dirs: bool
) -> tuple[int, int]:
    """按段落清空 bookmarks.txt, 返回 (书签目录, 近期目录) 各清掉几条"""
    if not path.is_file():
        return 0, 0

    dropped_sections = set()
    if clear_bookmarks:
        dropped_sections.add(SECTION_BOOKMARKS)
    if clear_recent_dirs:
        dropped_sections.add(SECTION_RECENT)

    counts: dict[str, int] = {SECTION_BOOKMARKS: 0, SECTION_RECENT: 0}
    kept_lines: list[str] = []
    section: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text in (SECTION_BOOKMARKS, SECTION_RECENT):
            section = text
            kept_lines.append(text)
        elif not text:
            continue
        elif section in dropped_sections:
            counts[section] += 1
        else:
            kept_lines.append(line)

    removed = counts[SECTION_BOOKMARKS] + counts[SECTION_RECENT]
    if removed:
        path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
    return counts[SECTION_BOOKMARKS], counts[SECTION_RECENT]


def clear_recent_files(path: Path) -> int:
    """清空 recent-files.txt, 返回清掉几条"""
    if not path.is_file():
        return 0
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    path.write_text("", encoding="utf-8")
    return len(lines)


def main(
    bookmarks: bool = True, recent_dirs: bool = True, recent_files: bool = True
) -> None:
    if not (bookmarks or recent_dirs or recent_files):
        message_box("没有勾选要清除的项目")
        return

    bookmark_count = recent_dir_count = file_count = 0
    if bookmarks or recent_dirs:
        bookmark_count, recent_dir_count = clear_bookmark_sections(
            get_config_path(BOOKMARKS_FILE), bookmarks, recent_dirs
        )
    if recent_files:
        file_count = clear_recent_files(get_config_path(RECENT_FILES_FILE))

    # 重新读盘, 让运行中的 Blender 内存里也只剩清空后的列表
    bpy.ops.wm.read_history()

    report_lines = []
    if bookmarks:
        report_lines.append(f"书签目录: {bookmark_count} 条")
    if recent_dirs:
        report_lines.append(f"近期目录: {recent_dir_count} 条")
    if recent_files:
        report_lines.append(f"近期文件: {file_count} 条")
    message_box("已清除\n" + "\n".join(report_lines), title="清除历史记录")


class ClearHistoryMenu(Operator):
    bl_idname = "wm.clear_history_menu"
    bl_label = "清除历史记录"

    bookmarks: BoolProperty(
        name="书签目录",
        description="文件浏览器里收藏的文件夹 (bookmarks.txt 的 [Bookmarks])",
        default=False,
    )
    recent_dirs: BoolProperty(
        name="近期目录",
        description="文件浏览器里访问过的文件夹 (bookmarks.txt 的 [Recent])",
        default=True,
    )
    recent_files: BoolProperty(
        name="近期文件",
        description="文件 > 打开最近的文件 (recent-files.txt)",
        default=True,
    )

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    @report_errors
    def execute(self, context: Context) -> set[str]:
        main(self.bookmarks, self.recent_dirs, self.recent_files)
        return {"FINISHED"}


if __name__ == "__main__":
    # 重复运行本脚本时先注销, 否则 register_class 会报已注册
    if hasattr(bpy.types, "WM_OT_clear_history_menu"):
        bpy.utils.unregister_class(bpy.types.WM_OT_clear_history_menu)
    register_and_invoke_menu(ClearHistoryMenu)
