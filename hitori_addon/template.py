import re
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from re import Match
from types import MappingProxyType
from xml.etree import ElementTree

from hitori_addon.bytes import add_len_prefix, escape_backslash, offset_bytes
from hitori_addon.const import (
    ABDATA_DIR,
    ABDATA_DIR_IN_ZIP,
    ACC_TYPES,
    CLOTH_TYPES,
    EXTERNAL_RESOURCES_DIR,
    MODS_DIR,
    RESOURCES_DIR,
    require_external_resources,
)
from hitori_addon.path import aspath
from hitori_addon.zip import create_zip
from hitori_addon.zipmod import rebuild_zipmod, to_arcname

TEMPLATE_DIR: Path = RESOURCES_DIR / "template"
TEMPLATE_CARD_PATH: Path = EXTERNAL_RESOURCES_DIR / "card" / "chara_name.png"
ZIPMOD_TEMPLATE_DIR: Path = TEMPLATE_DIR / "zipmod"
U3D_TEMPLATE_DIR: Path = EXTERNAL_RESOURCES_DIR / "u3d"

TEMPLATE_CARD_CAHRA_NAME: str = "chara_name"
MANIFEST_XML_BASENAME: str = "manifest.xml"

# 人物卡里的两张卡面图: 文件开头的缩略图 PNG 和 block0 里的头部图(游戏里的头像卡面)
CARD_FRONT_SIZE: tuple[int, int] = (252, 352)
CARD_FACE_SIZE: tuple[int, int] = (240, 320)

# 自动生成的 mod 缩略图 (模板 img/ 里没有 thumb.png 时的兜底)
THUMB_PNG_BASENAME: str = "thumb.png"
THUMB_SIZE: int = 256
THUMB_PADDING: int = 16
THUMB_MAX_FONT_SIZE: int = 128
THUMB_MIN_FONT_SIZE: int = 24
THUMB_LINE_SPACING: int = 8
THUMB_TEXT_COLOR: tuple[int, int, int, int] = (255, 255, 255, 255)
THUMB_OUTLINE_COLOR: tuple[int, int, int, int] = (0, 0, 0, 255)
THUMB_OUTLINE_WIDTH: int = 3

# 头模的纯色贴图: 不随仓库分发, 只在生成头模时由代码画出来
HEAD_TEX_SIZE: tuple[int, int] = (1024, 1024)
HEAD_MAIN_TEX_BASENAME: str = "white.png"
HEAD_MAIN_TEX_COLOR: tuple[int, int, int, int] = (255, 255, 255, 255)
HEAD_COLOR_MASK_TEX_BASENAME: str = "red.png"
HEAD_COLOR_MASK_TEX_COLOR: tuple[int, int, int, int] = (255, 0, 0, 255)

ANIMATOR_TYPES_WITH_HEAD_AND_HAIR: tuple[str, ...] = (
    "head",
    "hair",
    *CLOTH_TYPES,
    *ACC_TYPES,
)

ANIMATOR_TYPE_CSV_ID_MAP: Mapping[str, int] = MappingProxyType(
    {
        "head": 100,
        "hair": 101,
        "top": 105,
        "bot": 106,
        "bra": 107,
        "pants": 108,
        "glove": 109,
        "panty": 110,
        "sock": 111,
        "shoe": 112,
        "acc": 122,
        "acc2": 122,
        "acc3": 122,
        "acc4": 122,
        "acc5": 122,
        "acc6": 122,
        "acc7": 122,
        "acc8": 122,
        "acc9": 122,
    }
)

ANIMATOR_TYPE_KK_ID_MAP: Mapping[str, int] = MappingProxyType(
    {
        "head": 9876,
        "hair": 9876,
        "top": 9876,
        "bot": 9876,
        "bra": 9876,
        "pants": 9876,
        "glove": 9876,
        "panty": 9876,
        "sock": 9876,
        "shoe": 9876,
        "acc": 9876,
        "acc2": 98762,
        "acc3": 98763,
        "acc4": 98764,
        "acc5": 98765,
        "acc6": 98766,
        "acc7": 98767,
        "acc8": 98768,
        "acc9": 98769,
    }
)

ANIMATOR_TYPE_NAME_MAP: Mapping[str, str] = MappingProxyType(
    {
        "head": "0.head",
        "hair": "0.hair",
        "top": "1.top",
        "bot": "2.bot",
        "bra": "3.bra",
        "pants": "4.pants",
        "glove": "5.glove",
        "panty": "6.panty",
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

HEAD_CSV_STR: str = """{animator_type_csv_id}
0
0
ID,Kind,Possess,Name,MainManifest,MainAB,MainData,ShapeAnime,MatManifest,MatAB,MatData,MainTexAB,MainTex,ColorMaskAB,ColorMaskTex,ThumbAB,ThumbTex
{animator_type_kk_id},0,2,{chara_name}-head,abdata,data-{chara_name}/{chara_name}-head.unity3d,p_cf_head_00,cf_anmShapeHead_00,abdata,data-{chara_name}/{chara_name}-head.unity3d,neck,img-{chara_name}.unity3d,white,img-{chara_name}.unity3d,red,img-{chara_name}.unity3d,thumb"""

HAIR_CSV_STR: str = """{animator_type_csv_id}
0
0
ID,Kind,Possess,Name,MainManifest,MainAB,MainData,SetHair,ThumbAB,ThumbTex
{animator_type_kk_id},0,2,{chara_name}-hair,abdata,data-{chara_name}/{chara_name}.unity3d,{animator_name},0,img-{chara_name}.unity3d,thumb"""

TOP_CSV_STR: str = """{animator_type_csv_id}
0
0
ID,Kind,Possess,Name,MainManifest,MainAB,MainData,NormalData,StateType,Coordinate,NotBra,Sex,OverBodyMaskAB,OverBodyMask,OverBraMaskAB,OverBraMask,MainTexAB,MainTex,ColorMaskAB,ColorMaskTex,MainTex02AB,MainTex02,ColorMask02AB,ColorMask02Tex,KokanHide,ThumbAB,ThumbTex
{animator_type_kk_id},0,1,{chara_name}-{animator_type},abdata,data-{chara_name}/{chara_name}.unity3d,{animator_name},0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0,0,0,img-{chara_name}.unity3d,thumb
"""

CLOTH_CSV_STR: str = """{animator_type_csv_id}
0
0
ID,Kind,Possess,Name,MainManifest,MainAB,MainData,NormalData,StateType,Coordinate,NotBra,Sex,OverBodyMaskAB,OverBodyMask,OverBraMaskAB,OverBraMask,MainTexAB,MainTex,ColorMaskAB,ColorMaskTex,MainTex02AB,MainTex02,ColorMask02AB,ColorMask02Tex,KokanHide,ThumbAB,ThumbTex
{animator_type_kk_id},0,1,{chara_name}-{animator_type},abdata,data-{chara_name}/{chara_name}.unity3d,{animator_name},0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0,0,0,img-{chara_name}.unity3d,thumb"""

ACC_CSV_STR: str = """{animator_type_csv_id}
0
0
ID,Kind,Possess,Name,MainManifest,MainAB,MainData,Parent,HideHair,ThumbAB,ThumbTex
{animator_type_kk_id},0,1,{chara_name}-{animator_type},abdata,data-{chara_name}/{chara_name}.unity3d,{animator_name},{parent},0,img-{chara_name}.unity3d,thumb"""

# 初始化时不知道饰品最后挂在哪个挂点, 先写头部挂点(导出时会按实际选中的挂点改写)
ACC_DEFAULT_PARENT: str = "a_n_headside"


def get_csv_arcname(animator_type: str, chara_name: str) -> str:
    """csv 在 zipmod 里的路径"""
    return to_arcname(
        ABDATA_DIR_IN_ZIP
        / "list"
        / "characustom"
        / f"list-{chara_name}"
        / f"{ANIMATOR_TYPE_NAME_MAP[animator_type]}.csv"
    )


def get_csv_content(
    animator_type: str, chara_name: str, parent: str = ACC_DEFAULT_PARENT
) -> bytes:
    if animator_type == "head":
        template_str = HEAD_CSV_STR
    elif animator_type == "hair":
        template_str = HAIR_CSV_STR
    elif animator_type == "top":
        template_str = TOP_CSV_STR
    elif animator_type in CLOTH_TYPES:
        template_str = CLOTH_CSV_STR
    elif animator_type in ACC_TYPES:
        template_str = ACC_CSV_STR
    else:
        raise TypeError(f"{animator_type}不是有效的头部,头发,服装,饰品类型")

    format_dict = {
        "animator_type_csv_id": ANIMATOR_TYPE_CSV_ID_MAP[animator_type],
        "animator_type_kk_id": ANIMATOR_TYPE_KK_ID_MAP[animator_type],
        "chara_name": chara_name,
        "animator_type": animator_type,
        "animator_name": ANIMATOR_TYPE_NAME_MAP[animator_type],
        "parent": parent,
    }
    return template_str.format(**format_dict).encode("utf-8")


def update_acc_csv_parents(chara_name: str, acc_parent_map: Mapping[str, str]) -> None:
    """把 zipmod 里饰品 csv 的 Parent 改成导出时选中的挂点

    acc_parent_map 是 {饰品网格名: 挂点名}, 如 {"acc": "a_n_back"};
    csv 只在游戏启动时读, 改完要重启游戏。
    """
    zipmod_path = MODS_DIR / f"{chara_name}.zipmod"
    if not zipmod_path.is_file():
        return

    temp_paths = []
    arcname_path_map = {}
    try:
        with zipfile.ZipFile(zipmod_path) as zipmod_file:
            for acc_type, parent in acc_parent_map.items():
                arcname = get_csv_arcname(acc_type, chara_name)
                content = get_csv_content(acc_type, chara_name, parent)
                if arcname in zipmod_file.namelist() and (
                    zipmod_file.read(arcname) == content
                ):
                    continue

                temp_path = Path(tempfile.mkdtemp()) / f"{acc_type}.csv"
                temp_path.write_bytes(content)
                temp_paths.append(temp_path)
                arcname_path_map[arcname] = temp_path

        if arcname_path_map:
            try:
                rebuild_zipmod(zipmod_path, arcname_path_map)
            except OSError as error:
                # 游戏占着 zipmod 时换不了, 不影响本次导出(fbx 已经写完了)
                print(f"饰品挂点写不进 zipmod(退出游戏后重新导出即可): {error}")
                return

            print(f"更新饰品挂点: {zipmod_path}")
            for acc_type, parent in acc_parent_map.items():
                print(f"    {acc_type}: {parent}")
    finally:
        for temp_path in temp_paths:
            shutil.rmtree(temp_path.parent, ignore_errors=True)


def create_manifest_xml_content(chara_name: str) -> bytes:
    xml_path = ZIPMOD_TEMPLATE_DIR / MANIFEST_XML_BASENAME
    tree = ElementTree.parse(xml_path)
    root = tree.getroot()

    guid_element = root.find("guid")
    name_element = root.find("name")
    if guid_element is not None:
        guid_element.text = chara_name
    if name_element is not None:
        name_element.text = chara_name

    xml_content = ElementTree.tostring(root, encoding="utf-8", xml_declaration=False)
    return xml_content


def split_text_atoms(text: str) -> list[str]:
    """把文本按 _ 切成折行用的片段"""
    atoms = []
    start = 0
    for index, char in enumerate(text):
        if char == "_":
            atoms.append(text[start : index + 1])
            start = index + 1
    if start < len(text):
        atoms.append(text[start:])
    return atoms


def wrap_text_lines(
    draw, text: str, font, max_width: float, split_atoms: bool = False
) -> list[str]:
    """折行: 优先在 _ 处断开, split_atoms 时片段过宽再按字符断, 每行宽度不超过 max_width"""
    lines = []
    line = ""
    for atom in split_text_atoms(text):
        if draw.textlength(line + atom, font=font) <= max_width:
            line += atom
            continue
        if line:
            lines.append(line)
            line = ""
        while split_atoms and draw.textlength(atom, font=font) > max_width:
            cut = 1
            while (
                cut < len(atom)
                and draw.textlength(atom[: cut + 1], font=font) <= max_width
            ):
                cut += 1
            lines.append(atom[:cut])
            atom = atom[cut:]
        line = atom
    if line:
        lines.append(line)
    return lines


def load_thumb_font(size: int):
    """取可缩放的默认字体, 老版本 Pillow 退回位图默认字体"""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def fit_thumb_text(
    draw,
    chara_name: str,
    limit: float,
    max_font_size: int = THUMB_MAX_FONT_SIZE,
    min_font_size: int = THUMB_MIN_FONT_SIZE,
):
    """从大到小找第一组放得进画布的字号与折行结果, 先不拆散 _ 之间的片段, 再允许按字符拆"""
    font = lines = None
    for split_atoms in (False, True):
        for size in range(max_font_size, min_font_size - 1, -2):
            font = load_thumb_font(size)
            lines = wrap_text_lines(draw, chara_name, font, limit, split_atoms)
            boxes = [
                draw.textbbox((0, 0), line, font=font, stroke_width=THUMB_OUTLINE_WIDTH)
                for line in lines
            ]
            block_width = max(box[2] - box[0] for box in boxes)
            block_height = sum(
                box[3] - box[1] for box in boxes
            ) + THUMB_LINE_SPACING * (len(lines) - 1)
            if block_width <= limit and block_height <= limit:
                return font, lines
    return font, lines


def create_solid_png(color: tuple[int, int, int, int], size: tuple[int, int]) -> bytes:
    """生成纯色 png (头模的 MainTex 取纯白, ColorMask 取纯红)"""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def create_thumb_png(chara_name: str) -> bytes:
    """生成 256x256 透明底、居中带角色 id 的缩略图 png (模板 img/ 里没有 thumb.png 时的兜底)"""
    return create_text_png(chara_name, (THUMB_SIZE, THUMB_SIZE))


def create_text_png(chara_name: str, size: tuple[int, int]) -> bytes:
    """生成指定尺寸的透明底 png, 居中显示角色 id"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    image = Image.new("RGBA", size)
    draw = ImageDraw.Draw(image)
    font, lines = fit_thumb_text(draw, chara_name, min(size) - THUMB_PADDING * 2)

    text = "\n".join(lines)
    box = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=THUMB_LINE_SPACING,
        align="center",
        stroke_width=THUMB_OUTLINE_WIDTH,
    )
    draw.multiline_text(
        (
            (size[0] - box[2] + box[0]) / 2 - box[0],
            (size[1] - box[3] + box[1]) / 2 - box[1],
        ),
        text,
        font=font,
        fill=THUMB_TEXT_COLOR,
        spacing=THUMB_LINE_SPACING,
        align="center",
        stroke_width=THUMB_OUTLINE_WIDTH,
        stroke_fill=THUMB_OUTLINE_COLOR,
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def create_zipmod(
    chara_name: str,
    zipmod_path: str | Path,
    overwrite: bool = False,
    include_head: bool = False,
    use_text_thumb: bool = False,
):
    zipmod_path = aspath(zipmod_path)

    if zipmod_path.exists() and not overwrite:
        return

    require_external_resources()

    file_arcname_map = {}

    # 添加 manifest.xml
    manifest_xml_content = create_manifest_xml_content(chara_name)
    file_arcname_map[manifest_xml_content] = MANIFEST_XML_BASENAME

    # 添加u3d
    chara_u3d = U3D_TEMPLATE_DIR / "chara_name.unity3d"
    file_arcname_map[chara_u3d] = (
        ABDATA_DIR_IN_ZIP / f"data-{chara_name}" / f"{chara_name}.unity3d"
    )
    if include_head:
        head_u3d = U3D_TEMPLATE_DIR / "chara_name-head.unity3d"
        file_arcname_map[head_u3d] = (
            ABDATA_DIR_IN_ZIP / f"data-{chara_name}" / f"{chara_name}-head.unity3d"
        )

    # 添加img (模板 img/ 可以不存在, 里面的文件原样打包)
    img_dir = Path(ZIPMOD_TEMPLATE_DIR) / "img"
    img_arcname_dir = ABDATA_DIR_IN_ZIP / f"img-{chara_name}"
    if img_dir.is_dir():
        for img_path in img_dir.iterdir():
            # 要文字缩略图时盖模板里的 thumb.png
            if use_text_thumb and img_path.name == THUMB_PNG_BASENAME:
                continue
            if img_path.is_file():
                file_arcname_map[img_path] = img_arcname_dir / img_path.name

    # 头模的纯色贴图由代码生成 (模板里放了同名文件则用用户的), 不用头模时不打包
    if include_head:
        for basename, color in (
            (HEAD_MAIN_TEX_BASENAME, HEAD_MAIN_TEX_COLOR),
            (HEAD_COLOR_MASK_TEX_BASENAME, HEAD_COLOR_MASK_TEX_COLOR),
        ):
            if (img_dir / basename).exists():
                continue
            file_arcname_map[create_solid_png(color, HEAD_TEX_SIZE)] = (
                img_arcname_dir / basename
            )

    # 模板里没有缩略图时自动生成一张
    if use_text_thumb or not (img_dir / THUMB_PNG_BASENAME).exists():
        file_arcname_map[create_thumb_png(chara_name)] = (
            img_arcname_dir / THUMB_PNG_BASENAME
        )

    # 添加csv
    for animator_type in ANIMATOR_TYPES_WITH_HEAD_AND_HAIR:
        if animator_type == "head" and not include_head:
            continue
        file_arcname_map[get_csv_content(animator_type, chara_name)] = get_csv_arcname(
            animator_type, chara_name
        )

    create_zip(zipmod_path, file_arcname_map)


def create_u3d(chara_name: str, overwrite: bool = False):
    require_external_resources()

    chara_u3d = U3D_TEMPLATE_DIR / "chara_name.unity3d"
    dst_chara_u3d = ABDATA_DIR / f"{chara_name}.unity3d"
    if not dst_chara_u3d.exists() or overwrite:
        shutil.copy(chara_u3d, dst_chara_u3d)

    head_u3d = U3D_TEMPLATE_DIR / "chara_name-head.unity3d"
    dst_head_u3d = ABDATA_DIR / f"{chara_name}-head.unity3d"
    if not dst_head_u3d.exists() or overwrite:
        shutil.copy(head_u3d, dst_head_u3d)


def create_card(chara_name: str, card_path: str | Path, overwrite: bool = False):
    card_path = aspath(card_path)

    if card_path.exists() and not overwrite:
        return

    require_external_resources()

    with open(TEMPLATE_CARD_PATH, "rb") as f:
        card_content = f.read()

    # 1.替换卡里的 mod 名(模板卡里的旧名与模板卡面图上的文字一致)
    card_content = replace_card_name(
        card_content, TEMPLATE_CARD_CAHRA_NAME, chara_name
    )

    # 2.把两张卡面图换成透明底 + 角色 id
    card_content = replace_card_images(card_content, chara_name)

    # 保存人物卡
    with open(card_path, "wb") as f:
        f.write(card_content)


def replace_card_name(
    card_content: bytes, old_chara_name: str, new_chara_name: str
) -> bytes:
    """把卡里所有槽位的 mod 名换成新名, 并同步长度字段

    槽位名出现在两个字段(ModID / Name), 每个槽位里出现 2 次。
    """
    # 获取包含长度前缀的新旧名称字节(长度前缀偏移从A0开始)
    old_name = add_len_prefix(old_chara_name.encode(), offset=0xA0, length=1)
    new_name = add_len_prefix(new_chara_name.encode(), offset=0xA0, length=1)

    # 1.替换n个槽位内的mod名(包括每个槽位内的ModID字段和Name字段,共2n个,先获取槽位数再替换)
    slot_count = card_content.count(old_name) // 2
    card_content = card_content.replace(old_name, new_name)

    # 2.替换n个槽位的槽位长度字节(第一步完成后的槽位长度字节变化为2倍新旧长度差)
    # 使用.\xA5ModID{new_name}定位长度前缀
    len_diff = len(new_name) - len(old_name)
    old_content = b"(.)(.\xa5ModID" + new_name + b")"
    card_content = re.sub(
        escape_backslash(old_content),
        partial(offset_len_prefix, len_diff=len_diff),
        card_content,
    )

    # 3.替换2个父级长度前缀字节(用KKEx和About(小端字节序)定位,第一二步完成后的父级长度字节变化为2倍新旧长度差*槽位数)
    old_content = b"(\xa4name\xa4KKEx\xa7version\xa1.\xa3pos...\xa4size)(.....)"
    card_content = re.sub(
        escape_backslash(old_content),
        partial(offset_size_bytes, len_diff=len_diff, slot_count=slot_count),
        card_content,
    )
    old_content = b"(\xa4name\xa5About\xa7version\xa5.....\xa3pos...\xa4size..)(..)"
    card_content = re.sub(
        escape_backslash(old_content),
        partial(
            offset_size_bytes, len_diff=len_diff, slot_count=slot_count, reverse=True
        ),
        card_content,
    )
    return card_content


def replace_card_images(card: bytes, chara_name: str) -> bytes:
    """把人物卡的两张卡面图换成透明底 + 角色 id 的 png, 尺寸保持不变

    文件开头的缩略图 PNG 没有长度前缀, block0 头部图有 int32 长度前缀;
    lstInfo 里的 pos / size 都以 block2 内容起点为原点, 所以换 block0 不影响其他块。
    """
    from hitori_addon.card import skip_thumbnail_png

    front_end = skip_thumbnail_png(card)
    face_prefix = front_end + 4  # productNo
    face_prefix += 1 + card[face_prefix]  # 卡片标记
    face_prefix += 1 + card[face_prefix]  # 版本号
    face_size = int.from_bytes(
        card[face_prefix : face_prefix + 4], "little", signed=True
    )
    face_start = face_prefix + 4

    front_png = create_text_png(chara_name, CARD_FRONT_SIZE)
    face_png = create_text_png(chara_name, CARD_FACE_SIZE)
    return b"".join(
        (
            front_png,
            card[front_end:face_prefix],
            len(face_png).to_bytes(4, "little", signed=True),
            face_png,
            card[face_start + face_size :],
        )
    )


def offset_len_prefix(match: Match, len_diff: int) -> bytes:
    old_len_prefix = match.group(1)
    new_len_prefix = offset_bytes(old_len_prefix, 2 * len_diff)
    return new_len_prefix + match.group(2)


def offset_size_bytes(
    match: Match, len_diff: int, slot_count: int, reverse: bool = False
) -> bytes:
    old_size_bytes = match.group(2)
    new_size_bytes = offset_bytes(
        old_size_bytes, 2 * len_diff * slot_count, reverse=reverse
    )
    return match.group(1) + new_size_bytes
