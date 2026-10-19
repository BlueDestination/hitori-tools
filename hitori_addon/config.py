"""插件路径配置的读写

机器相关路径全部来自插件目录下的 `hitori_addon_config.json`。
安装脚本写好配置后, 该文件随 `hitori_addon/` 一起复制进 Blender,
所以项目里的副本和 Blender 里的副本各自带一份配置, 多个 Blender 版本互不影响。
"""

import json
from collections.abc import Mapping
from pathlib import Path

# 配置文件名, 与 hitori_addon/ 放在一起
CONFIG_FILE_NAME = "hitori_addon_config.json"

# 配置文件路径覆盖, 只在测试里用, 传 None 恢复默认
_PATH_OVERRIDE: Path | None = None


def get_default_config_path() -> Path:
    """插件目录下的默认配置文件路径"""
    return Path(__file__).absolute().parent / CONFIG_FILE_NAME


def get_config_path() -> Path:
    """当前使用的配置文件路径(测试可覆盖)"""
    return _PATH_OVERRIDE or get_default_config_path()


def set_config_path(path: Path | None) -> None:
    """覆盖配置文件路径, 传 None 恢复默认, 只在测试里用"""
    global _PATH_OVERRIDE
    _PATH_OVERRIDE = Path(path) if path else None


def load_config(path: Path | None = None) -> dict[str, str]:
    """读配置文件, 不存在或损坏时返回空字典"""
    path = Path(path) if path else get_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if value}


def get_value(name: str, config: Mapping[str, str] | None = None) -> str:
    """取单个配置项, 没有时返回空字符串"""
    if config is None:
        config = load_config()
    return config.get(name, "")


def write_config(values: dict[str, str], path: Path | None = None) -> Path:
    """写配置文件, 返回写入路径"""
    path = Path(path) if path else get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(values, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    return path
