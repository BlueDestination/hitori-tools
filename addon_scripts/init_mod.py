import bpy

from hitori_addon.const import KK_CARDS_DIR, KK_DIR, MODS_DIR
from hitori_addon.menu import register_menu_and_run
from hitori_addon.path import get_blend_file_stem, is_valid_identifier
from hitori_addon.run import run_command
from hitori_addon.template import create_card, create_u3d, create_zipmod
from hitori_addon.thumb import confirm_thumb_crop

HEAD_PROPERTY = bpy.props.EnumProperty(
    name="包含头模",
    items=[
        ("否", "否", "zipmod 里不写头模(unity3d 和头部的 csv)"),
        ("是", "是", "zipmod 里写头模(unity3d 和头部的 csv)"),
    ],
    default="否",
)

LAUNCH_GAME_PROPERTY = bpy.props.BoolProperty(
    name="启动游戏",
    description="初始化完成后启动游戏",
    default=True,
)

THUMB_PROPERTY = bpy.props.EnumProperty(
    name="mod缩略图",
    items=[
        (
            "框选截取",
            "框选截取",
            "自动切正交前视图并建一个方形线框, 对齐后按回车截取",
        ),
        ("文字图片", "文字图片", "生成透明底、居中带角色ID的图片"),
        (
            "模板图片",
            "模板图片",
            "沿用 resources/template/zipmod/img/thumb.png, 没有则生成文字图片",
        ),
    ],
    default="框选截取",
)


def init_mod_card_u3d(
    chara_name: str, include_head: bool = False, use_text_thumb: bool = False
):
    # 初始化mod
    zipmod_path = MODS_DIR / f"{chara_name}.zipmod"
    create_zipmod(
        chara_name,
        zipmod_path,
        overwrite=False,
        include_head=include_head,
        use_text_thumb=use_text_thumb,
    )

    # 初始化人物卡
    card_path = KK_CARDS_DIR / f"{chara_name}.png"
    create_card(chara_name, card_path, overwrite=False)

    # 初始化u3d文件
    create_u3d(chara_name, overwrite=False)


def set_kk_default_chara(chara_name: str):
    cfg_template = """\
[Config]
Enabled = true
Default Female Card Replacement =
Default Female Card Path = {card_path}
Default Male Card Replacement =
Default Male Card Path =
"""
    card_path = KK_CARDS_DIR / f"{chara_name}.png"
    cfg_content = cfg_template.format(card_path=card_path)
    default_chara_cfg = (
        KK_DIR / "BepInEx" / "config" / "IllusionMods.CharacterReplacer.cfg"
    )
    with open(default_chara_cfg, "w", encoding="utf-8") as f:
        f.write(cfg_content)


def try_init_mod_card_u3d(
    chara_name: str,
    include_head: bool = False,
    launch_game: bool = True,
    use_text_thumb: bool = False,
):
    if not is_valid_identifier(chara_name) or len(chara_name) > 27:
        raise ValueError(
            f"角色ID只能由字母,下划线和数字组成,且长度要<=27,当前blend角色ID为:\n{chara_name}"
        )

    zipmod_path = MODS_DIR / f"{chara_name}.zipmod"
    if not zipmod_path.exists():
        init_mod_card_u3d(chara_name, include_head, use_text_thumb)
        set_kk_default_chara(chara_name)

    if launch_game:
        kk_exe = KK_DIR / "KoikatsuSunshine.exe"
        run_command([kk_exe], block=False, window=True)


def main(
    include_head: str = "否",
    launch_game: bool = True,
    thumb: str = "框选截取",
):
    chara_name = get_blend_file_stem()
    include_head_bool = include_head == "是"
    use_text_thumb = thumb == "文字图片"

    # 缩略图要在建 zipmod 之前准备好; zipmod 已存在时原流程不会再动它, 不用截
    zipmod_path = MODS_DIR / f"{chara_name}.zipmod"
    if thumb == "框选截取" and not zipmod_path.exists():
        confirm_thumb_crop(
            lambda: try_init_mod_card_u3d(
                chara_name, include_head_bool, launch_game, use_text_thumb
            )
        )
        return

    try_init_mod_card_u3d(
        chara_name, include_head_bool, launch_game, use_text_thumb
    )


if __name__ == "__main__":
    # zipmod 已经存在时初始化流程不会再动它, 不用再问, 直接启动调试
    if (MODS_DIR / f"{get_blend_file_stem()}.zipmod").exists():
        try_init_mod_card_u3d(get_blend_file_stem())
    else:
        register_menu_and_run(
            main,
            HEAD_PROPERTY,
            bool_property=LAUNCH_GAME_PROPERTY,
            enum_property_2=THUMB_PROPERTY,
        )
