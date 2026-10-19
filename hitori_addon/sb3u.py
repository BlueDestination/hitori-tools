from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from hitori_addon.const import ACC_TYPES, CLOTH_TYPES, SB3U_DIR
from hitori_addon.run import run_command

SB3U_EXE = SB3U_DIR / "SB3UtilityScript.exe"

CLOTH_TYPE_ANIMATOR_NAME_MAP: Mapping[str, str] = MappingProxyType(
    {
        cloth_type: f"{i}.{cloth_type}"
        for i, cloth_type in enumerate(CLOTH_TYPES, start=1)
    }
    | {acc_type: f"9.{acc_type}" for acc_type in ACC_TYPES}
)

CLOTH_TYPE_BY_ANIMATOR_NAME: Mapping[str, str] = MappingProxyType(
    {
        animator_name: cloth_type
        for cloth_type, animator_name in CLOTH_TYPE_ANIMATOR_NAME_MAP.items()
        if cloth_type in CLOTH_TYPES
    }
)

MESH_ANIMATOR_MAP: Mapping[str, str] = MappingProxyType(
    {
        "hair": "0.hair",
        "cloth_top": "1.top",
        "cloth_top.001": "1.top",
        "cloth_top_top": "1.top",
        "cloth_top_top.001": "1.top",
        "cloth_top_bot": "1.top",
        "cloth_top_bot.001": "1.top",
        "cloth_bot": "2.bot",
        "cloth_bot.001": "2.bot",
        "cloth_bra": "3.bra",
        "cloth_bra.001": "3.bra",
        "cloth_bra_top": "3.bra",
        "cloth_bra_top.001": "3.bra",
        "cloth_bra_bot": "3.bra",
        "cloth_bra_bot.001": "3.bra",
        "pants": "4.pants",
        "pants.001": "4.pants",
        "pants.002": "4.pants",
        "glove": "5.glove",
        "panty": "6.panty",
        "panty.001": "6.panty",
        "sock": "7.sock",
        "shoe": "8.shoe",
        "acc": "9.acc",
        "acc2": "9.acc2",
        "acc3": "9.acc3",
        "acc4": "9.acc4",
        "acc5": "9.acc5",
        "acc6": "9.acc6",
        "acc7": "9.acc7",
        "acc8": "9.acc8",
        "acc9": "9.acc9",
    }
)

MESH_FRAME_ID_MAP: Mapping[str, int] = MappingProxyType(
    {
        "hair": 1,
        "cloth_top": 1,
        "cloth_top.001": 2,
        "cloth_top_top": 1,
        "cloth_top_top.001": 2,
        "cloth_top_bot": 3,
        "cloth_top_bot.001": 4,
        "cloth_bot": 1,
        "cloth_bot.001": 2,
        "cloth_bra": 1,
        "cloth_bra.001": 2,
        "cloth_bra_top": 1,
        "cloth_bra_top.001": 2,
        "cloth_bra_bot": 3,
        "cloth_bra_bot.001": 4,
        "pants": 1,
        "pants.001": 2,
        "pants.002": 3,
        "glove": 1,
        "panty": 1,
        "panty.001": 2,
        "sock": 1,
        "shoe": 1,
        "acc": 1,
        "acc2": 1,
        "acc3": 1,
        "acc4": 1,
        "acc5": 1,
        "acc6": 1,
        "acc7": 1,
        "acc8": 1,
        "acc9": 1,
    }
)

def get_cloth_type(mesh_name: str) -> str | None:
    """网格名对应的服装类型; 饰品 / 头发 / 头模 / 非法名(如 `_pants`)返回 None

    不需要单独维护映射: 类型先经 `MESH_ANIMATOR_MAP` 换成 animator 名, 再由
    `CLOTH_TYPE_ANIMATOR_NAME_MAP` 反查, 只有服装类(不含 acc)能查到。
    """
    animator_name = MESH_ANIMATOR_MAP.get(mesh_name)
    if animator_name is None:
        return None
    return CLOTH_TYPE_BY_ANIMATOR_NAME.get(animator_name)


CLOTH_MESH_NAMES: tuple[str, ...] = tuple(
    mesh_name
    for mesh_name in MESH_ANIMATOR_MAP
    if (
        mesh_name in MESH_ANIMATOR_MAP
        and mesh_name not in ACC_TYPES
        and mesh_name != "hair"
    )
)
ACC_MESH_NAMES: tuple[str, ...] = ACC_TYPES


@dataclass
class Sb3uFbxMesh:
    index: int
    name: str
    is_headmod: bool = False
    is_acc: bool = False
    arm_name: str = ""
    arm_dst_parent_id: int = 0
    frame_id: int = 0

    def __post_init__(self):
        self.is_headmod = self.name.endswith("_headmod")
        self.is_acc = self.name.startswith("acc")
        self.arm_name = "arm_" + self.name if self.is_acc else "Armature"
        self.arm_dst_parent_id = 2 if self.is_acc else 0
        self.frame_id = MESH_FRAME_ID_MAP[self.name] if not self.is_headmod else 92


def sb3u_run_script(script_path: str | Path):
    command = [SB3U_EXE, script_path]
    run_command(command)
