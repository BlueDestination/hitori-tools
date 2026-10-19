"""常驻的无头导出子进程

由 `bg_export.run_addon_script_in_background()` 拉起并复用: 主进程保存工程后把任务发过来, 它先
`open_mainfile` 换掉整个工程数据库再跑导出脚本, 所以上一个任务的脏状态不会残留, 用户当前工程也不受影响。

- 只在回环端口上收任务, 一次连接一条命令。
- 会带一个控制台窗口, 从这里能看到导出进度, 也知道有这么个子进程。
- 用户关掉那个窗口 / 主 Blender 退出, 它都会结束; 下次导出自动重开。
- 改了本文件的代码后主进程会自动把它重启, 不用手工关窗口。
"""

import ctypes
import io
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

# 子进程标记, 只在本插件启动的子进程里存在, 用来防止子进程再启动子进程
CHILD_EXPORT_ENV_NAME = "hitori_child_export"

# 配置文件路径的传递通道, 只在子进程环境里存在(测试用沙箱配置时靠它)
CHILD_CONFIG_ENV_NAME = "hitori_child_config"

# 子进程报错的输出标记, 主进程只提取标记之间的精简 traceback
CHILD_ERROR_START = "===== hitori child export error start ====="
CHILD_ERROR_END = "===== hitori child export error end ====="

# 常驻导出子进程用的回环端口, 与游戏侧的 14145 区分开
WORKER_PORT = 14147

# 控制台窗口标题, 让用户知道这个子进程是干什么的
CONSOLE_TITLE = "Hitori 导出子进程"

# 常驻进程隔多久检查一次主 Blender 还在不在
PARENT_CHECK_INTERVAL = 1.0

# 拉起常驻进程后等它就绪的最长时间(含预热导入)
START_TIMEOUT = 30.0

# 回环端口连不通时要等满超时才返回, 所以探测常驻进程的超时必须短
PROBE_TIMEOUT = 0.3

# 等常驻进程就绪时的轮询间隔和探测超时
PROBE_INTERVAL = 0.05
READY_PROBE_TIMEOUT = 0.15

# 连接常驻进程用的超时, 正式发任务前的这一步失败就该赶紧退回
CONNECT_TIMEOUT = 5.0

# 单次导出的等待上限(大 mod 导出可能很慢)
JOB_TIMEOUT = 600.0

# 导出要用到的模块, 空闲时先导进来, 第一次导出就不用等
PREWARM_MODULES = (
    "UnityPy",
    "hitori_addon.fbx",
    "hitori_addon.hotreload",
    "hitori_addon.image",
    "hitori_addon.sb3u",
    "hitori_addon.u3d",
)

WORKER_SCRIPT: Path = Path(__file__).resolve()

from hitori_addon import config

# 必须在导入 const(它一导入就读配置)之前应用覆盖
_CONFIG_OVERRIDE = os.getenv(CHILD_CONFIG_ENV_NAME)
if _CONFIG_OVERRIDE:
    config.set_config_path(Path(_CONFIG_OVERRIDE))

import bpy

from hitori_addon.const import BLENDER_DIR
from hitori_addon.run import run_script

BLENDER_EXE: Path = BLENDER_DIR / "blender.exe"


# ----------------------------------------------------------------------------
# 子进程侧
# ----------------------------------------------------------------------------


class TeeStream:
    """把任务输出同时写进控制台和捕获缓冲"""

    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()

    def isatty(self) -> bool:
        return False


def run_job(blend_file: Path, script_file: Path) -> tuple[str, str]:
    """换掉当前工程并跑一次导出脚本, 返回状态和捕获的输出"""
    buffer = io.StringIO()
    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout = TeeStream(stdout, buffer)
    sys.stderr = TeeStream(stderr, buffer)
    status = "ok"
    try:
        print(f"载入工程: {blend_file}", flush=True)
        bpy.ops.wm.open_mainfile(filepath=str(blend_file))
        run_script(script_file)
    except SystemExit as error:
        # run_child_scripts 报错后靠结束进程来熔断脚本, 在这里只算这次任务失败, 常驻进程继续留着
        status = "error"
        print(f"导出脚本提前结束: {error.code}", flush=True)
    except BaseException:  # noqa: BLE001  脚本的任意异常都只算这次任务失败
        status = "error"
        print(
            f"{CHILD_ERROR_START}\n{traceback.format_exc().strip()}\n{CHILD_ERROR_END}",
            flush=True,
        )
    finally:
        sys.stdout, sys.stderr = stdout, stderr
    return status, buffer.getvalue()


def handle_command(command: str) -> tuple[str, str]:
    name, _, argument = command.partition(" ")
    if name == "ping":
        return (
            "pong",
            f"{config.get_config_path()}\t{os.getpid()}\t{WORKER_SCRIPT.stat().st_mtime_ns}",
        )
    if name == "export":
        blend_file, _, script_file = argument.partition("\t")
        return run_job(Path(blend_file), Path(script_file))
    return "error", f"未知命令: {command!r}"


def send_reply(conn: socket.socket, status: str, text: str) -> None:
    payload = text.encode("utf-8", errors="replace")
    conn.sendall(f"{status} {len(payload)}\n".encode() + payload)


def receive_reply(conn: socket.socket) -> tuple[str, str]:
    """读回包, 返回状态和正文"""
    buffer = b""
    while b"\n" not in buffer:
        chunk = conn.recv(4096)
        if not chunk:
            raise ConnectionError("常驻导出子进程没有回包")
        buffer += chunk
    header, _, payload = buffer.partition(b"\n")
    status, _, length = header.decode().partition(" ")
    while len(payload) < int(length):
        chunk = conn.recv(65536)
        if not chunk:
            raise ConnectionError("常驻导出子进程回包不完整")
        payload += chunk
    return status, payload.decode("utf-8", errors="replace")


def is_process_alive(pid: int) -> bool:
    """pid 对应的进程还在不在"""
    process_handle = ctypes.windll.kernel32.OpenProcess(
        0x00100000, False, pid
    )  # SYNCHRONIZE
    if not process_handle:
        return False
    try:
        return (
            ctypes.windll.kernel32.WaitForSingleObject(process_handle, 0) == 0x102
        )  # WAIT_TIMEOUT
    finally:
        ctypes.windll.kernel32.CloseHandle(process_handle)


def prewarm() -> None:
    """空闲时把导出要用的模块先导进来, 第一次导出就不用再等"""
    for module_name in PREWARM_MODULES:
        try:
            __import__(module_name)
        except BaseException:  # noqa: BLE001  预热失败不影响导出
            print(
                f"预热 {module_name} 失败, 不影响导出:\n{traceback.format_exc().strip()}",
                flush=True,
            )


def serve(port: int) -> None:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(4)
    # 靠 accept 超时来定期检查主 Blender 是否已退出
    server.settimeout(PARENT_CHECK_INTERVAL)
    print(f"常驻导出子进程已就绪(端口 {port}), 导出进度会显示在这里", flush=True)
    print("关掉这个窗口就是关掉子进程, 不影响导出结果, 下次导出会自动重开", flush=True)

    threading.Thread(target=prewarm, daemon=True).start()

    parent_pid = os.getppid()
    while True:
        try:
            conn, _ = server.accept()
        except TimeoutError:
            if not is_process_alive(parent_pid):
                print("主 Blender 已退出, 常驻导出子进程结束", flush=True)
                return
            continue
        with conn:
            # 只等客户端把命令发过来, 免得一个不说话的连接把常驻进程卡住
            conn.settimeout(CONNECT_TIMEOUT)
            try:
                command = conn.recv(4096).decode("utf-8", errors="replace").strip()
            except TimeoutError:
                continue
            status, text = handle_command(command)
            send_reply(conn, status, text)


def get_port() -> int:
    """端口默认取 WORKER_PORT, 支持 `--python bg_worker.py -- <端口>` 覆盖(测试用)"""
    if "--" in sys.argv:
        arguments = sys.argv[sys.argv.index("--") + 1 :]
        if arguments:
            return int(arguments[0])
    return WORKER_PORT


def main() -> None:
    os.environ[CHILD_EXPORT_ENV_NAME] = "1"
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(CONSOLE_TITLE)
    except BaseException:  # noqa: BLE001, S110  改控制台标题失败无需处理
        pass
    print(f"===== {CONSOLE_TITLE} =====", flush=True)
    serve(get_port())


# ----------------------------------------------------------------------------
# 主进程侧: 拉起 / 复用常驻子进程
# ----------------------------------------------------------------------------


def ping_worker(port: int, timeout: float = PROBE_TIMEOUT) -> list[str] | None:
    """常驻导出子进程在监听就返回它的配置路径/pid/代码时间戳, 否则返回 None"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout) as conn:
            conn.settimeout(timeout)
            conn.sendall(b"ping")
            status, text = receive_reply(conn)
    except OSError:
        return None
    return text.split("\t") if status == "pong" else None


def kill_worker(pid: int) -> None:
    """结束常驻子进程(代码更新后重启用)"""
    process_handle = ctypes.windll.kernel32.OpenProcess(
        0x0001, False, pid
    )  # PROCESS_TERMINATE
    if not process_handle:
        return
    try:
        ctypes.windll.kernel32.TerminateProcess(process_handle, 0)
    finally:
        ctypes.windll.kernel32.CloseHandle(process_handle)


def start_worker(port: int) -> None:
    """拉起常驻导出子进程, 它会带一个控制台窗口"""
    env = os.environ.copy()
    env[CHILD_EXPORT_ENV_NAME] = "1"
    env[CHILD_CONFIG_ENV_NAME] = str(config.get_config_path())
    existing_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        ";".join(list(sys.path) + [existing_path])
        if existing_path
        else ";".join(sys.path)
    )

    subprocess.Popen(
        [
            str(BLENDER_EXE),
            "--background",
            "--factory-startup",
            "--python",
            str(WORKER_SCRIPT),
            "--",
            str(port),
        ],
        # 和主 Blender 分开的控制台窗口, 用户能看到导出进度, 也能自己关掉
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        env=env,
    )


def ensure_worker(port: int = WORKER_PORT) -> bool:
    """确保有一个能用当前配置文件的常驻导出子进程, 可用返回 True"""
    if not BLENDER_EXE.is_file():
        print(f"找不到Blender, 无法启动常驻导出子进程: {BLENDER_EXE}")
        return False

    config_path = str(config.get_config_path())
    worker_info = ping_worker(port)
    if worker_info is not None:
        if worker_info[0] != config_path:
            # 端口被另一个工程/Blender 的常驻子进程占着, 不抢
            print(f"常驻导出子进程属于其它工程({worker_info[0]}), 这次退回一次性子进程")
            return False
        if worker_info[2] != str(WORKER_SCRIPT.stat().st_mtime_ns):
            print("常驻导出子进程的代码已更新, 重启它")
            kill_worker(int(worker_info[1]))
        else:
            return True

    print("启动常驻导出子进程(会新开一个控制台窗口, 之后的导出都复用它)")
    start_worker(port)

    deadline = time.perf_counter() + START_TIMEOUT
    while time.perf_counter() < deadline:
        worker_info = ping_worker(port, READY_PROBE_TIMEOUT)
        if worker_info is not None:
            if worker_info[0] != config_path:
                print(
                    f"常驻导出子进程属于其它工程({worker_info[0]}), 这次退回一次性子进程"
                )
                return False
            return True
        time.sleep(PROBE_INTERVAL)
    print(f"常驻导出子进程 {START_TIMEOUT:.0f}s 内没有就绪, 退回一次性子进程")
    return False


def run_export_in_worker(
    blend_file: str | Path,
    script_file: str | Path,
    port: int = WORKER_PORT,
) -> tuple[str, str] | None:
    """把一次导出交给常驻子进程, 返回状态和输出; 子进程不可用或半路没了返回 None

    返回 None 时调用方应该退回一次性子进程, 不会比原来更差。
    """
    if not ensure_worker(port):
        return None
    try:
        with socket.create_connection(
            ("127.0.0.1", port), timeout=CONNECT_TIMEOUT
        ) as conn:
            conn.settimeout(JOB_TIMEOUT)
            conn.sendall(f"export {blend_file}\t{script_file}".encode())
            return receive_reply(conn)
    except OSError as error:
        print(f"常驻导出子进程连接中断({error}), 退回一次性子进程")
        return None


if __name__ == "__main__":
    main()
