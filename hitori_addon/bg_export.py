"""把导出流程放到无头 Blender 子进程里执行

导出流程会改动工程里的物体/骨骼/贴图/集合, 在无头子进程里跑就不会污染当前工程, 只把 mod 结果热更新出去。

默认复用常驻的导出子进程(见 `bg_worker.py`, 只在第一次导出时等它启动一下), 它能省掉每次重新启动 Blender
和载入工程的一两秒; 常驻的没启动起来 / 被用户关掉 / 半路断了, 就退回每次新开一个, 两者都不改动当前工程。

入口脚本用法:
    from hitori_addon.bg_export import is_child_export, run_addon_script_in_background, run_child_scripts

    if is_child_export():
        run_child_scripts('legalize_texture_names.py', 'cloth_export.py')
    else:
        run_addon_script_in_background(__file__)
"""

import os
import sys
import time
import traceback
from pathlib import Path

import bpy

from hitori_addon.bg_worker import (
    BLENDER_EXE,
    CHILD_ERROR_END,
    CHILD_ERROR_START,
    CHILD_EXPORT_ENV_NAME,
    run_export_in_worker,
)
from hitori_addon.run import run_addon_script, run_command


def is_child_export() -> bool:
    """当前是否运行在无头导出子进程里"""
    return os.getenv(CHILD_EXPORT_ENV_NAME) == "1"


def run_child_scripts(*script_basenames: str) -> None:
    """子进程里依次运行导出脚本, 任一脚本报错就打印精简 traceback 并立即结束进程

    立即结束既是为了熔断后续脚本, 也避免 Blender 再打印一份完整 traceback。
    """
    for script_basename in script_basenames:
        try:
            run_addon_script(script_basename)
        except BaseException:  # noqa: BLE001  连 SystemExit 一起抓才能熔断后续脚本
            print(CHILD_ERROR_START, flush=True)
            print(traceback.format_exc().strip(), flush=True)
            print(CHILD_ERROR_END, flush=True)
            sys.exit(1)


def extract_child_error(output: str) -> str:
    """只取子进程标记的报错段, 没有标记时返回原文"""
    start = output.find(CHILD_ERROR_START)
    if start == -1:
        return output.strip()
    end = output.find(CHILD_ERROR_END, start)
    if end == -1:
        end = len(output)
    return output[start + len(CHILD_ERROR_START) : end].strip()


def save_blend_file() -> None:
    """保存当前工程, 没有改动时跳过

    无头模式下is_dirty恒为True, 这个判断只在界面里生效。
    """
    if not bpy.data.filepath:
        raise RuntimeError("当前工程还没有保存过, 请先手动保存一次 .blend 文件")

    if bpy.data.is_dirty:
        bpy.ops.wm.save_mainfile()
        print(f"工程已保存: {bpy.data.filepath}")


def run_addon_script_in_background(script_file: str | Path) -> None:
    """保存当前工程, 然后用无头子进程运行同一个脚本

    导出流程只改动子进程, 当前工程的物体/骨骼/贴图/集合保持原样。
    """
    script_file = Path(script_file)
    if is_child_export():
        raise RuntimeError("已经是无头导出子进程, 不能再启动无头导出")
    if not BLENDER_EXE.is_file():
        raise RuntimeError(f"找不到Blender, 请重新运行 setup.bat: {BLENDER_EXE}")

    save_blend_file()

    env = os.environ.copy()
    env[CHILD_EXPORT_ENV_NAME] = "1"
    command: list[str | Path] = [
        BLENDER_EXE,
        "--background",
        # 子进程只用 Blender 内置功能(导出脚本自行 import hitori_addon), 不加载用户插件与偏好, 启动更快
        "--factory-startup",
        bpy.data.filepath,
        # 必须写在--python前面, 否则脚本报错时子进程仍然返回0
        "--python-exit-code",
        "1",
        "--python",
        script_file,
    ]

    print(f"开始无头导出(当前工程不会被改动): {script_file.name}")

    start = time.perf_counter()
    result = run_export_in_worker(bpy.data.filepath, script_file)
    if result is not None:
        status, output = result
        print(output)
        if status != "ok":
            raise RuntimeError(
                f"无头导出失败, 当前工程没有被改动, 子进程报错:\n{extract_child_error(output)}"
            )
        print(
            f"无头导出完成, 当前工程没有被改动: {script_file.name}"
            f" (常驻子进程, 用时 {time.perf_counter() - start:.3f}s)"
        )
        return

    try:
        run_command(
            command,
            print_=True,
            print_all=True,
            return_text=True,
            env=env,
            path=sys.path,
        )
    except RuntimeError as error:
        # 把子进程的精简报错拼进主进程的报错, 用户不用翻控制台
        output = getattr(error, "text", "") or str(error)
        raise RuntimeError(
            f"无头导出失败, 当前工程没有被改动, 子进程报错:\n{extract_child_error(output)}"
        ) from None

    print(f"无头导出完成, 当前工程没有被改动: {script_file.name}")
