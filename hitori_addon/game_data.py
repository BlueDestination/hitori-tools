"""游戏衍生的小型数据表, 运行时从 external_resources/data/kk_game_data.json 读取."""

import json
from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType

import numpy as np

DATA_FILE_NAME = "data/kk_game_data.json"


@lru_cache(maxsize=1)
def _load_game_data() -> dict:
    from hitori_addon.const import EXTERNAL_RESOURCES_DIR, require_external_resources

    require_external_resources()
    return json.loads(
        (EXTERNAL_RESOURCES_DIR / DATA_FILE_NAME).read_text(encoding="utf-8")
    )


def get_kk_neck_vertex_positions() -> np.ndarray:
    """26 个 KK 脖颈接缝顶点坐标"""
    return np.asarray(_load_game_data()["neck_vertex_positions"], dtype=float)


@lru_cache(maxsize=1)
def get_kk_head_blend_shape_names() -> tuple[str, ...]:
    """按 KK 形态键顺序排列的 176 个名称"""
    return tuple(_load_game_data()["head_blend_shape_names"])


@lru_cache(maxsize=1)
def get_kk_expression_code_name_map() -> Mapping[str, str]:
    """表情代码到形态键名称的映射"""
    return MappingProxyType(dict(_load_game_data()["expression_code_name_map"]))


def get_kk_color_curve_nodes() -> np.ndarray:
    """KK 校色曲线, 每通道 17 个节点"""
    return np.asarray(_load_game_data()["kklut_color_curve_nodes"], dtype=float)
