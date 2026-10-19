from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

COLORS: Mapping[str, str] = MappingProxyType(
    {
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "magenta": "\033[35m",
        "cyan": "\033[36m",
        "white": "\033[37m",
        "reset": "\033[0m",
    }
)

COLOR_ABBREVIATIONS: Mapping[str, str] = MappingProxyType(
    {
        "r": "red",
        "g": "green",
        "y": "yellow",
        "b": "blue",
        "m": "magenta",
        "c": "cyan",
        "w": "white",
    }
)


def color_text(obj: Any, color: str) -> str:
    color = color.lower()
    color = COLOR_ABBREVIATIONS.get(color, color)
    color_code = COLORS.get(color, COLORS["reset"])
    return f"{color_code}{obj}{COLORS['reset']}"
