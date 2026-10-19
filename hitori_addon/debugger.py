import io
import socket
import sys
import threading
import traceback


def start_listener(
    address: str = "127.0.0.1",
    port: int = 61001,
) -> None:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((address, port))
    server_socket.listen(4)
    while True:
        client_socket, _addr = server_socket.accept()
        data = client_socket.recv(4096)
        output = io.StringIO()
        sys.stdout = output
        try:
            exec(data.decode("utf-8"))  # noqa: S102  调试监听按设计执行外部发来的代码
            output_str = output.getvalue()
            client_socket.send(output_str.encode("utf-8"))
        except Exception as e:  # noqa: BLE001  任何异常都要回传给外部客户端
            error_message = traceback.format_exc()
            print(f"{error_message}\n{e}")
            client_socket.send(error_message.encode("utf-8"))
        finally:
            output_str = output.getvalue()
            client_socket.close()
            output.close()
            sys.stdout = sys.__stdout__
            print(output_str.strip())


def run_debugger(
    address: str = "127.0.0.1",
    port: int = 61001,
) -> None:
    listener_thread = threading.Thread(target=start_listener, args=(address, port))
    listener_thread.daemon = True
    listener_thread.start()
    print(f"调试器正在监听: {address}:{port}...")


if __name__ == "__main__":
    run_debugger()
