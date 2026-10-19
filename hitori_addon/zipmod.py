import errno
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from hitori_addon.const import ABDATA_DIR_IN_ZIP, MODS_DIR
from hitori_addon.path import aspath, remove_suffix

# 热重载期间不压缩(store): 每次更新 mod 只要 0.11s(压 deflate 要 1.20s), 游戏重载也不用解压
# 代价是 zipmod 会涨到解压后的大小(约 6.8 倍), 发布时 compress_zipmod 会压回 deflate
ZIPMOD_COMPRESS_TYPE: int = zipfile.ZIP_STORED


def to_arcname(path: str | Path) -> str:
    """zip 里的条目名: 分隔符统一用正斜杠"""
    return aspath(path).as_posix()


def copy_zip_info(old_info: zipfile.ZipInfo, compress_type: int) -> zipfile.ZipInfo:
    """沿用旧条目的名称, 时间戳和文件属性, 只改压缩方式"""
    new_info = zipfile.ZipInfo(old_info.filename, date_time=old_info.date_time)
    new_info.compress_type = compress_type
    new_info.external_attr = old_info.external_attr
    new_info.internal_attr = old_info.internal_attr
    new_info.create_system = old_info.create_system
    return new_info


def temp_zipmod_path(zipmod_path: str | Path) -> Path:
    """重建 zipmod 时先写的临时文件(放系统临时目录, 不污染 mod 目录)"""
    zipmod_path = aspath(zipmod_path)
    return Path(tempfile.gettempdir()) / f"{zipmod_path.name}.tmp"


def move_replace(temp_file_path: Path, file_path: Path) -> None:
    """把临时文件替换到目标路径

    临时文件在别的盘时 rename 会报 EXDEV, 先复制到目标目录的临时文件再原子替换
    """
    try:
        os.replace(temp_file_path, file_path)
        return
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise

    file_descriptor, local_name = tempfile.mkstemp(
        prefix=f"{file_path.name}.", suffix=".tmp", dir=file_path.parent
    )
    os.close(file_descriptor)
    local_temp_path = Path(local_name)
    try:
        shutil.copyfile(temp_file_path, local_temp_path)
        os.replace(local_temp_path, file_path)
    finally:
        local_temp_path.unlink(missing_ok=True)
    os.remove(temp_file_path)


def replace_file(
    temp_file_path: Path,
    file_path: Path,
    retry_count: int = 5,
    retry_interval: float = 0.2,
):
    """原子替换文件

    游戏可能正好在读这个zipmod, Windows下被别的进程读着就没法替换,
    稍微等一下再试, 免得热重载因为撞上游戏读文件而失败
    """
    for attempt in range(retry_count):
        try:
            move_replace(temp_file_path, file_path)
            return
        except PermissionError:
            if attempt == retry_count - 1:
                raise
            time.sleep(retry_interval)


def build_zipmod_temp(
    zipmod_path: str | Path,
    arcname_path_map: dict[str, str | Path] | None = None,
    compress_type: int = ZIPMOD_COMPRESS_TYPE,
) -> Path:
    """重建 zipmod 到临时文件, 返回临时文件路径(不替换原文件)

    arcname_path_map 是 {zip里的条目名: 本地文件}, 对应条目会被本地文件替换,
    zipmod 里没有的条目追加到最后; 其余条目原样搬运, 顺序不变。
    zipfile 没法搬运原来的压缩流, 所以整个 zipmod 都要重新压一遍(见 ZIPMOD_COMPRESS_TYPE)。
    """
    zipmod_path = aspath(zipmod_path)
    path_map = {
        to_arcname(arcname): aspath(path)
        for arcname, path in (arcname_path_map or {}).items()
    }
    temp_path = temp_zipmod_path(zipmod_path)

    with (
        zipfile.ZipFile(zipmod_path) as old_zipmod,
        zipfile.ZipFile(temp_path, "w", compress_type) as new_zipmod,
    ):
        new_zipmod.comment = old_zipmod.comment
        for old_info in old_zipmod.infolist():
            new_path = path_map.pop(old_info.filename, None)
            new_info = copy_zip_info(old_info, compress_type)
            with (
                open(new_path, "rb") if new_path else old_zipmod.open(old_info) as src,
                new_zipmod.open(new_info, "w") as dst,
            ):
                shutil.copyfileobj(src, dst, 1024 * 1024)

        # zipmod 里原本没有的条目(比如初始化时没勾头模, 后来又改了头模的u3d)
        for arcname, new_path in path_map.items():
            new_info = zipfile.ZipInfo.from_file(new_path, arcname)
            new_info.compress_type = compress_type
            with (
                open(new_path, "rb") as src_file,
                new_zipmod.open(new_info, "w") as dst_file,
            ):
                shutil.copyfileobj(src_file, dst_file, 1024 * 1024)

    return temp_path


def rebuild_zipmod(
    zipmod_path: str | Path,
    arcname_path_map: dict[str, str | Path] | None = None,
    compress_type: int = ZIPMOD_COMPRESS_TYPE,
    release=None,
):
    """重建 zipmod

    先写临时文件再原子替换, 避免游戏读到写了一半的 zipmod。
    release: 替换原文件前调用, 用于让游戏先放掉 zipmod 文件句柄
    """
    zipmod_path = aspath(zipmod_path)
    temp_path = build_zipmod_temp(zipmod_path, arcname_path_map, compress_type)
    try:
        if release is not None:
            release()
        replace_file(temp_path, zipmod_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def u3d_update_zipmod(
    u3d_path: str | Path,
    print_: bool = False,
    raise_: bool = True,
    replace: bool = True,
) -> Path | None:
    """把 u3d 写进对应的 zipmod, 返回 zipmod 路径(失败且不抛异常时返回 None)

    replace=False 时只写出临时文件(见 temp_zipmod_path), 不替换原 zipmod:
    热重载要先让游戏放掉 zipmod 文件句柄再换
    """
    u3d_path = aspath(u3d_path)
    u3d_basename = u3d_path.name
    chara_name = remove_suffix(u3d_path.stem, "-head")

    zipmod_path = MODS_DIR / f"{chara_name}.zipmod"
    if not zipmod_path.exists():
        raise FileNotFoundError(f"mod文件夹不存在对应mod: {zipmod_path}")

    zip_u3d_path = ABDATA_DIR_IN_ZIP / f"data-{chara_name}" / u3d_basename
    if print_:
        print(f"更新zipmod: {to_arcname(zip_u3d_path)} <- {u3d_path}")

    try:
        if replace:
            rebuild_zipmod(zipmod_path, {to_arcname(zip_u3d_path): u3d_path})
        else:
            build_zipmod_temp(zipmod_path, {to_arcname(zip_u3d_path): u3d_path})
        return zipmod_path
    except Exception:
        if raise_:
            raise
        return None


def is_zipmod_compressed(zipmod_path: str | Path) -> bool:
    """zipmod 里的文件条目是不是都压缩过(deflate)

    目录条目在 zip 里只能是 store, 不算数
    """
    with zipfile.ZipFile(aspath(zipmod_path)) as zipmod_file:
        return all(
            info.compress_type == zipfile.ZIP_DEFLATED
            for info in zipmod_file.infolist()
            if not info.is_dir()
        )


def compress_zipmod(zipmod_path: str | Path, release=None):
    """把 zipmod 压成 deflate

    热重载期间是不压缩(store)的, 发布前要压小体积(56MB 的 u3d 能压到 15%), 已经压过的不再动。
    release: 替换原文件前调用, 用于让游戏放掉 zipmod 文件句柄(游戏正在运行时否则压缩会因文件被占用失败)
    """
    zipmod_path = aspath(zipmod_path)
    if is_zipmod_compressed(zipmod_path):
        return

    rebuild_zipmod(zipmod_path, compress_type=zipfile.ZIP_DEFLATED, release=release)
    print(f"zipmod 已压缩: {zipmod_path}")
