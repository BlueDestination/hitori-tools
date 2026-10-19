import socket
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from time import perf_counter

try:
    import bpy  # noqa: F401  只用来探测是否跑在 Blender 里

    IN_BLENDER: bool = True
except ImportError:
    IN_BLENDER: bool = False

PROGRAM_START_TIME: float = perf_counter()
LAST_RECORD_TIME: float = PROGRAM_START_TIME


def send_module_code(
    module_path: str | Path,
    address: str = "127.0.0.1",
    port: int = 61001,
    use_print: bool = True,
) -> None:
    if IN_BLENDER:
        return

    with open(module_path, "r", encoding="utf-8") as f:
        code = f.read()

    code += """
if __name__ == '__main__':
    main()
"""

    send_code(code, address, port, use_print)


def send_code(
    code: str,
    address: str = "127.0.0.1",
    port: int = 61001,
    use_print: bool = True,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.connect((address, port))
        client_socket.send(code.encode("utf-8"))
        response_str = client_socket.recv(8192).decode("utf-8")
        if use_print:
            print(response_str.strip())


@contextmanager
def timing(description: str = "") -> AbstractContextManager[None]:
    start_time = perf_counter()
    try:
        yield
    finally:
        print(f"{description} {perf_counter() - start_time:.3f}s")


def print_timing(
    description: str = "", print_total: bool = False, start: bool = False
) -> None:
    global LAST_RECORD_TIME
    now_time = perf_counter()
    total_time = now_time - PROGRAM_START_TIME
    elapsed_time = now_time - LAST_RECORD_TIME
    LAST_RECORD_TIME = now_time

    if start:
        return

    stdout = description
    if print_total:
        stdout += f"{total_time:6.3f}s "
    stdout += f"{elapsed_time:6.3f}s"
    print(stdout)
