"""u3d 保存后重建 zipmod, 并让游戏清 mod 缓存热重载"""

import socket
import winsound
from datetime import datetime
from pathlib import Path

from hitori_addon.const import KK_CARDS_DIR
from hitori_addon.path import aspath, remove_suffix
from hitori_addon.printf import color_text
from hitori_addon.zipmod import replace_file, temp_zipmod_path, u3d_update_zipmod

# 热重载次数, 只用于日志编号
UPDATE_COUNTER: int = 0
# 替换 zipmod 的重试次数: 替换前游戏可能又重新加载了这个 mod
REPLACE_ATTEMPTS: int = 3
# 等游戏卸载 mod 的超时(秒), 要比插件里的 ClearTimeoutMs 长
UNLOAD_TIMEOUT: float = 10.0


def send_reload_command(
    message: str,
    address: str = "127.0.0.1",
    port: int = 14145,
    timeout: float = UNLOAD_TIMEOUT,
) -> str:
    """连一次游戏发一条指令, 返回回包文本; 连不上返回空串

    游戏侧一条连接只处理一条指令(处理完就关), 所以每次都要新连接
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((address, port))
            sock.send(message.encode())
            return sock.recv(64).decode("utf-8", "replace").strip()
    except OSError:
        return ""


def request_clear_cache(
    address: str = "127.0.0.1",
    port: int = 14145,
    timeout: float = UNLOAD_TIMEOUT,
    zipmod_path: str | Path | None = None,
) -> bool:
    """让游戏卸载 mod 释放 zipmod 文件句柄, 返回是否真的卸完了

    传 zipmod_path 只卸这一个 mod(快, 不动其它 mod 和游戏本体资产), 不传是全量。
    定向指令没被认(游戏里是旧版插件)或超时就退全量, 不会比原来更差。
    游戏没在运行或等待超时就返回 False, 调用方退回"直接替换 + 重试"
    """
    messages = ["ClearCache"]
    if zipmod_path:
        messages.insert(0, f"ClearCacheOne {aspath(zipmod_path)}")

    for message in messages:
        if send_reload_command(message, address, port, timeout).endswith("ok"):
            return True

    return False


def refresh_kk_card_mod(
    card_path: str | Path, address: str = "127.0.0.1", port: int = 14145
) -> None:
    """通知游戏重新读取人物卡(mod 缓存已由 request_clear_cache 清过, 这里只重读, 不再清)"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((address, port))
            sock.send(f"ReadCard {aspath(card_path)}".encode())
    except OSError as error:
        print(f"重载人物卡失败(游戏可能没在运行): {error}")


def update_zipmod_file(u3d_path: str | Path) -> None:
    """把 u3d 写进 zipmod: 先写临时文件, 让游戏卸掉 mod 后再替换

    游戏流式加载 zipmod 里的 AssetBundle 时会一直占着这个文件, 不先卸载就替换不掉:
    写临时文件不需要游戏放锁, 替换前才发指令, 等游戏回包说卸完了再换
    只要求游戏卸这一个 mod, 不动其它 mod 和游戏本体资产
    """
    zipmod_path = u3d_update_zipmod(u3d_path, replace=False)
    temp_path = temp_zipmod_path(zipmod_path)
    for attempt in range(REPLACE_ATTEMPTS):
        is_unloaded = request_clear_cache(zipmod_path=zipmod_path)
        try:
            replace_file(temp_path, zipmod_path)
            return
        except PermissionError:
            # 卸完又被游戏重新加载了(比如捏人界面在刷新), 再卸一次重试
            if not is_unloaded or attempt == REPLACE_ATTEMPTS - 1:
                raise


def update_and_refresh_mod(u3d_path: str | Path) -> None:
    """u3d 保存后重建对应 zipmod, 再让游戏清缓存热重载"""
    global UPDATE_COUNTER

    u3d_path = aspath(u3d_path)
    try:
        update_zipmod_file(u3d_path)
        is_successful = True
        winsound.Beep(750, 100)
    except Exception:  # noqa: BLE001  更新失败只换提示音, 不中断流程
        is_successful = False
        winsound.Beep(3000, 100)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = (
        color_text("successfully", "g") if is_successful else color_text("failed", "r")
    )
    print(f"{now} ({color_text(UPDATE_COUNTER, 'c')}) update {u3d_path.name} {status}")
    UPDATE_COUNTER += 1

    if not is_successful:
        return

    chara_name = remove_suffix(u3d_path.stem, "-head")
    refresh_kk_card_mod(KK_CARDS_DIR / f"{chara_name}.png")
