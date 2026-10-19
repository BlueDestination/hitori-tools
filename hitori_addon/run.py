import ctypes
import io
import os
import subprocess
import sys
import time
from pathlib import Path

from hitori_addon.const import ADDON_SCRIPTS_DIR, TESTS_DIR
from hitori_addon.error import UserError
from hitori_addon.path import get_file_stem

RUN_SEPARATOR = "-" * 40


def decode_streams(stdout: bytes, encodings: tuple[str, ...]) -> str:
    for encoding in encodings:
        try:
            return stdout.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"all stdout encodings failed: {encodings}")


def run_command(
    args: list[str | Path],
    return_text: bool = False,
    print_: bool = False,
    block: bool = True,
    raise_: bool = True,
    encodings: tuple[str, ...] = (
        "cp" + str(ctypes.windll.kernel32.GetConsoleOutputCP()),
        "utf-8",
        "gbk",
    ),
    window: bool = False,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    path: list[str] | None = None,
    # 同时打印stdout和stderr(子进程的报错信息在两个流里都有可能出现)
    print_all: bool = False,
) -> str | int:
    # 只有 window(走 start) 需要 shell, 其余直接传列表, 省一层 cmd.exe
    shell = window
    if window:
        args = ["start", ""] + args

    if path:
        if env is None:
            env = os.environ.copy()
        else:
            env = env.copy()
        python_path = env.get("PYTHONPATH")
        if python_path:
            env["PYTHONPATH"] = ";".join(path + [python_path])
        else:
            env["PYTHONPATH"] = ";".join(path)

    if not block:
        subprocess.Popen(args, shell=shell, cwd=cwd, env=env)
        return "" if return_text else 0

    process = subprocess.Popen(
        args,
        shell=shell,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 以下为阻塞并等待进程结果
    # 使用process.wait()可能会因为缓冲区满而阻塞造成进程卡死,因此使用process.communicate()
    stdout, stderr = process.communicate()
    exit_code = process.returncode

    text = (
        "\n".join(
            decode_streams(stream, encodings)
            for stream in (
                (stdout, stderr) if print_all else (stderr if exit_code else stdout,)
            )
        )
        if return_text or print_
        else ""
    )

    if print_ or exit_code:
        print(text)

    if raise_ and exit_code:
        error = RuntimeError(f"Run command error:\n{args}\n{text}")
        # 让调用方可以只拿子进程输出
        error.text = text
        raise error

    return text if return_text else exit_code


def run_script(filepath: str | Path) -> None:
    filepath = str(filepath)
    global_namespace = {"__file__": filepath, "__name__": "__main__"}
    with open(filepath, "rb") as file:
        code_bytes = file.read()
    exec(compile(code_bytes, filepath, "exec"), global_namespace)  # noqa: S102  按设计执行脚本文件


def run_test_script(script_basename: str) -> None:
    filepath = str(TESTS_DIR / script_basename)

    globals_ = {"__file__": filepath, "__name__": "__main__"}
    with open(filepath, "rb") as file:
        code_bytes = file.read()

    test_code_lines = """
if __name__ == '__main__':
    for var_name in dir():
        if var_name.startswith('test_'):
            globals()[var_name]()
"""
    code_bytes += test_code_lines.encode("utf-8")

    start = time.perf_counter()
    output = io.StringIO()
    sys.stdout = output

    exec(compile(code_bytes, filepath, "exec"), globals_)  # noqa: S102  按设计执行测试文件

    used_time = time.perf_counter() - start
    sys.stdout = sys.__stdout__
    result = output.getvalue()
    output.close()

    timing_str = f"运行测试 {get_file_stem(script_basename)}: {used_time:.3f}s\n"
    print(result + timing_str + RUN_SEPARATOR)

    from hitori_addon.menu import message_box

    message_box(result, title=timing_str)


# "重复上次操作"按钮的标识, 由run_addon_script解析成上次运行的脚本
REPEAT_LAST_SCRIPT: str = "repeat_last_script"

# 上次由用户触发的脚本, 脚本内部嵌套调用的子脚本不覆盖
_LAST_ADDON_SCRIPT: str | None = None
_RUN_ADDON_SCRIPT_DEPTH: int = 0


def run_addon_script(script_basename: str) -> None:
    """运行插件脚本, 记录最外层脚本供"重复上次操作"使用"""
    global _LAST_ADDON_SCRIPT, _RUN_ADDON_SCRIPT_DEPTH

    if script_basename == REPEAT_LAST_SCRIPT:
        if _LAST_ADDON_SCRIPT is None:
            from hitori_addon.menu import message_box

            message = "还没有运行过插件脚本, 没有可以重复的操作"
            message_box(message, title="重复上次操作", icon="ERROR")
            # 已经弹窗提示过, 不用再让 Blender 报错
            return
        script_basename = _LAST_ADDON_SCRIPT

    if not _RUN_ADDON_SCRIPT_DEPTH:
        _LAST_ADDON_SCRIPT = script_basename

    _RUN_ADDON_SCRIPT_DEPTH += 1
    try:
        run_script(ADDON_SCRIPTS_DIR / script_basename)
    except UserError:
        # 已经弹窗告诉过用户, 不用再让 Blender 报错
        pass
    finally:
        _RUN_ADDON_SCRIPT_DEPTH -= 1


def profile_run_addon_script(
    script_basename: str,
    webpage_timeout: int = 3,
) -> None:
    import cProfile
    import tempfile
    import time

    with tempfile.NamedTemporaryFile(delete=False, suffix=".prof") as temp_file:
        profile_file = temp_file.name

    profiler = cProfile.Profile()
    profiler.enable()
    run_addon_script(script_basename)
    profiler.disable()
    profiler.dump_stats(profile_file)

    process = subprocess.Popen(["snakeviz", profile_file])
    time.sleep(webpage_timeout)
    process.terminate()
