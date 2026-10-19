from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import numpy as np

from hitori_addon.acc import KkAcc
from hitori_addon.config import get_config_path, get_value, load_config
from hitori_addon.error import UserError

# 路径配置全部来自 hitori_addon_config.json
_CONFIG: Mapping[str, str] = MappingProxyType(load_config())


def _get_dir(name: str) -> Path:
    """取必需的文件夹路径, 缺失时报错提示重新安装"""
    value = get_value(name, _CONFIG)
    if not value:
        raise RuntimeError(
            f"缺少配置项 {name}, 请先运行 setup.bat 生成 {get_config_path()}"
        )
    return Path(value)


def _get_optional_dir(name: str) -> Path | None:
    """取可选的文件夹路径, 未配置时返回None"""
    value = get_value(name, _CONFIG)
    return Path(value) if value else None


BLENDER_DIR: Path = _get_dir("blender")
PROJECT_DIR: Path = _get_dir("project")
RESOURCES_DIR: Path = _get_dir("resources")
SB3U_DIR: Path = _get_dir("sb3u")
ABDATA_DIR: Path = _get_dir("abdata")
KK_DIR: Path = _get_dir("kk")
MODS_DIR: Path = _get_dir("mods")
DESKTOP_DIR: Path = _get_dir("desktop")
RELEASE_DIR: Path = _get_dir("release")
SHAPEKEY_SCREENSHOT_DIR: Path = _get_dir("shapekey_screenshot")
# magick是非必须的, 未安装时配置里没有该项
MAGICK_DIR: Path | None = _get_optional_dir("magick")

# 脚本路径
ADDON_SCRIPTS_DIR: Path = PROJECT_DIR / "addon_scripts"
TESTS_DIR: Path = PROJECT_DIR / "tests"

# 资源路径
# 游戏衍生的模板与数据(不随公开仓库分发), 单独放仓库根
EXTERNAL_RESOURCES_DIR: Path = PROJECT_DIR / "external_resources"
# 外部资源清单: 运行时检查 / 打包脚本都用这份 (安装脚本里有一份内容相同的副本, 改这里要同步)
EXTERNAL_RESOURCES_FILE_LIST: tuple[str, ...] = (
    "card/chara_name.png",
    "data/kk_game_data.json",
    "kk_blend/official_template.blend",
    # 贴图不再强要求, 缺少时 blender 自动显示紫色表示缺失
    # 'kk_blend/textures/cf_bodytights_n-DXT5.dds',
    # 'kk_blend/textures/cf_bodytights_n-RGBA32.tga',
    "u3d/chara_name.unity3d",
    "u3d/chara_name-head.unity3d",
)
KK_CARDS_DIR: Path = KK_DIR / "UserData" / "chara" / "female"
ABDATA_DIR_IN_ZIP: Path = Path("abdata")

# 模型内固定名称: 会随 mod 写进游戏, 改名会让旧模型对不上
# 从 MMD 转过来时装贴图的形态键名
USER_EDIT_KEY_NAME: str = "user_edit_key"

CLOTH_TYPES: tuple[str, ...] = (
    "top",
    "bot",
    "bra",
    "pants",
    "glove",
    "panty",
    "sock",
    "shoe",
)
ACC_TYPES: tuple[str, ...] = (
    "acc",
    "acc2",
    "acc3",
    "acc4",
    "acc5",
    "acc6",
    "acc7",
    "acc8",
    "acc9",
)

# 挂点数据取自游戏 oo_base.unity3d 的 a_n_* 世界变换 (见 docs/automation.md)
KK_ACCS: tuple[KkAcc, ...] = (
    KkAcc("head", pos=(0, 0.020762, 1.580417), rot=(0, 0, 0, 1), parent="a_n_headside"),
    KkAcc(
        "neck",
        pos=(0, 0.024762, 1.488417),
        rot=(0.104528, 0, 0, 0.994522),  # 12 度 X
        parent="a_n_neck",
    ),
    KkAcc("back", pos=(0, 0.086762, 1.3825), rot=(0, 1, 0, 0), parent="a_n_back"),
    KkAcc("waist", pos=(0, 0, 1.1385), rot=(0, 0, 0, 1), parent="a_n_waist"),
    KkAcc("chest", pos=(0, 0.029262, 1.4485), rot=(0, 0, 0, 1), parent="a_n_bust"),
)

KK_ACC_POSITIONS_ARR: np.ndarray = np.array([kk_acc.pos for kk_acc in KK_ACCS])

AXIS_INDEX_MAP: Mapping[str, int] = MappingProxyType({"x": 0, "y": 1, "z": 2})

IDENTITY_CAMERA_ORTHOGONAL_SCALE: float = 1.77777


def missing_external_resources() -> list[str]:
    """外部资源里缺失的文件, 取值是相对 external_resources 的路径"""
    return [
        name
        for name in EXTERNAL_RESOURCES_FILE_LIST
        if not (EXTERNAL_RESOURCES_DIR / name).is_file()
    ]


def require_external_resources() -> None:
    """外部资源不随仓库分发, 用到时才检查; 缺失时弹窗提示并中断"""
    missing = missing_external_resources()
    if not missing:
        return

    from hitori_addon.menu import message_box

    message = "\n".join(
        (
            "缺少外部资源, 无法继续.",
            "请下载外部资源包, 解压后把 external_resources 文件夹放到项目根目录:",
            f"    {EXTERNAL_RESOURCES_DIR}",
            "缺少的文件:",
            *[f"    {name}" for name in missing],
            "放好后重新运行 setup.bat.",
        )
    )
    message_box(message, title="缺少外部资源", icon="ERROR")
    raise UserError(message)
