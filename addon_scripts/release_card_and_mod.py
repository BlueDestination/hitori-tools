from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from hitori_addon.card import convert_kks_card_to_kk
from hitori_addon.const import KK_CARDS_DIR, MODS_DIR, RELEASE_DIR
from hitori_addon.hotreload import request_clear_cache
from hitori_addon.path import get_blend_file_stem
from hitori_addon.run import run_command
from hitori_addon.zip import create_zip
from hitori_addon.zipmod import compress_zipmod

chara_name = get_blend_file_stem()

zipmod_name = f"{chara_name}.zipmod"

kks_card_name = f"{chara_name}.png"
kk_card_name = f"KK_{chara_name}.png"

zipmod_path = MODS_DIR / zipmod_name

kks_card_path = KK_CARDS_DIR / kks_card_name

# KK卡片不落盘, 直接以字节写进发布包, 避免失败时在人物卡目录留下残留
kk_card_bytes = convert_kks_card_to_kk(kks_card_path.read_bytes())

release_zip_file_path = RELEASE_DIR / f"{chara_name}_Release.zip"

# 热重载期间zipmod是不压缩的, 发布前压回deflate, 游戏在运行时先让它放掉zipmod文件句柄
compress_zipmod(
    zipmod_path, release=lambda: request_clear_cache(zipmod_path=zipmod_path)
)

file_path_map: Mapping[bytes | Path, Path | str] = MappingProxyType(
    {
        kk_card_bytes: Path("KK") / kk_card_name,
        kks_card_path: Path("KKS") / f"KKS_{kks_card_name}",
        zipmod_path: zipmod_name,
    }
)

create_zip(release_zip_file_path, file_path_map)

run_command(["explorer", "/select,", str(Path(release_zip_file_path))], block=False)
