"""改完 hitori_addon 里的代码后自动生效, 不用重启 Blender

运行插件脚本前比对 lib 目录里 `.py` 的 (相对路径, 修改时间, 大小), 有变化就把整个包从 `sys.modules` 移除,
下次 import 重新读源码 (同 streamlit 的做法)。`addon_scripts` 不用这种处理: 按钮每次都是重新读文件执行的。
`hitori_addon_ui` (菜单) 不重载, 改菜单仍要重跑 `setup.bat`; 这里只把 UI 模块缓存过的库函数换成新模块的,
否则新旧两份 `run` 模块各记一份"上次脚本", "重复上次操作"会记到子脚本上。

默认关闭, 需要 `hitori_addon_config.json` 里写 `"hotreload": "true"` 才启用。
"""

import importlib
import os
import sys
from pathlib import Path

from hitori_addon.config import load_config

PACKAGE_NAME = "hitori_addon"
UI_MODULE_NAME = "hitori_addon_ui"
CONFIG_KEY = "hotreload"
ENABLED_VALUES: tuple[str, ...] = ("1", "true", "yes", "on")
# UI 模块缓存过的库函数, 重载后改指向新模块 (只改属性, 不重新注册菜单)
UI_REBINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hitori_addon.run", ("run_addon_script", "REPEAT_LAST_SCRIPT")),
    ("hitori_addon.menu", ("message_box", "get_popup_count", "report_error")),
    ("hitori_addon.error", ("REPORTED_ERROR_TYPES",)),
    ("hitori_addon.settings", ("RUN_STATE",)),
    (f"{PACKAGE_NAME}.autoreload", ("reload_if_changed",)),
)

# 上次重载时的目录签名, 重载后由新模块接着用, 否则下次运行又会当成"变了"
_SIGNATURE: tuple[tuple[str, int, int], ...] | None = None


def get_lib_dir() -> Path:
    """当前在用的插件 lib 目录"""
    return Path(__file__).resolve().parent


def get_signature(lib_dir: Path) -> tuple[tuple[str, int, int], ...]:
    """lib 目录里每个 .py 的 (相对路径, 修改时间, 大小)

    只看 mtime + 大小 (和 importlib 判断 .pyc 是否过期同一精度), 不读文件内容, 一次 0.3ms
    """
    signature = []
    stack = [(lib_dir, "")]
    while stack:
        directory, prefix = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_dir():
                    # __pycache__ 里的 .pyc 变化不算 lib 改动
                    if entry.name != "__pycache__":
                        stack.append((Path(entry.path), f"{prefix}{entry.name}/"))
                elif entry.name.endswith(".py"):
                    stat = entry.stat()
                    signature.append(
                        (f"{prefix}{entry.name}", stat.st_mtime_ns, stat.st_size)
                    )
    return tuple(sorted(signature))


def is_enabled() -> bool:
    """配置里开了才检查, 默认关闭"""
    return load_config().get(CONFIG_KEY, "").strip().lower() in ENABLED_VALUES


def remove_package() -> list[str]:
    """从 sys.modules 移除整个包, 返回移除的模块名"""
    names = [
        name
        for name in list(sys.modules)
        if name == PACKAGE_NAME or name.startswith(f"{PACKAGE_NAME}.")
    ]
    for name in names:
        del sys.modules[name]
    return names


def rebind_ui_module() -> None:
    """把 UI 模块缓存的库函数换成重载后的新模块, 顺便把新模块带进 sys.modules"""
    ui_module = sys.modules.get(UI_MODULE_NAME)
    for module_name, attribute_names in UI_REBINDS:
        module = importlib.import_module(module_name)
        if ui_module is None:
            continue
        for attribute_name in attribute_names:
            setattr(ui_module, attribute_name, getattr(module, attribute_name))


def reload_if_changed() -> bool:
    """lib 目录变了就重载, 返回是否重载过

    重载失败时异常照常抛出 (包已清空, 下次 import 会重新报同一个错), 调用方不用特殊处理
    """
    global _SIGNATURE

    if not is_enabled():
        return False

    signature = get_signature(get_lib_dir())
    if signature == _SIGNATURE:
        return False
    if _SIGNATURE is None:
        # 第一次只记基线: Blender 启动时加载的就是当前代码
        _SIGNATURE = signature
        return False

    names = remove_package()
    # 失败时签名留在旧模块里, 下次运行会再试一次
    rebind_ui_module()
    new_module = importlib.import_module(f"{PACKAGE_NAME}.autoreload")
    new_module.__dict__["_SIGNATURE"] = signature
    print(f"插件库已热重载, 移除 {len(names)} 个模块")
    return True
