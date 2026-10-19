"""读写恋活人物卡里的 KSOX 覆盖层和 Sideloader 解析信息"""

import re
import socket
import struct
import winsound
from collections.abc import Iterable
from pathlib import Path

from hitori_addon import msgpack
from hitori_addon.path import aspath

# KKEx 里 Skin Overlay Mod 的插件 GUID
KSOX_GUID = "KSOX"
# KKEx 里 Sideloader 的自动解析信息插件 GUID
UAR_GUID = "com.bepis.sideloader.universalautoresolver"
# KoiSkinOverlayX.TexType 里的虹膜上层(左右眼)
TEX_TYPE_EYE_OVER_L = 8
TEX_TYPE_EYE_OVER_R = 10
# 覆盖层数据结构版本
KSOX_VERSION = 2
# 固定的贴图 ID, 重复烘焙时覆盖同一张贴图, 避免人物卡膨胀
PUPIL_TEXTURE_ID = 8172635
# 官方瞳孔的"无": DeathWeasel 的 No Iris zipmod 往 mt_eye 注册的 None
NO_IRIS_GUID = "com.DeathWeasel.NoIris"
NO_IRIS_SLOT = 1
NO_IRIS_AUTHOR = "DeathWeasel"
NO_IRIS_WEBSITE = "https://github.com/IllusionMods/KK_Plugins"
NO_IRIS_NAME = "No Iris"
# No Iris 在本机 Sideloader 里的解析 ID: 加载时按 GUID+Slot 重新解析, 这个值只用于回退和展示
NO_IRIS_LOCAL_SLOT = 100010660
# mt_eye(瞳孔)的 ChaListDefine.CategoryNo
PUPIL_CATEGORY_NO = 408
# Sideloader 里左右眼瞳孔的属性名(见 UniversalAutoResolver 的 StructReference)
PUPIL_PROPERTIES = ("ChaFileFace.Pupil1", "ChaFileFace.Pupil2")
# 默认覆盖的服装编号(0-3 是基础的四套)
DEFAULT_COORDINATES = (0, 1, 2, 3)
# KKEx 里 Material Editor 的插件 GUID
MATERIAL_EDITOR_GUID = "com.deathweasel.bepinex.materialeditor"
# Material Editor 的插件数据版本
MATERIAL_EDITOR_VERSION = 0
# Material Editor 数据里的键名
MATERIAL_EDITOR_TEXTURES_KEY = "TextureDictionary"
MATERIAL_EDITOR_PROPERTIES_KEY = "MaterialTexturePropertyList"
MATERIAL_EDITOR_SHADERS_KEY = "MaterialShaderList"
# Material Editor 的 ObjectType.Character, 眼睛等角色本体材质用它
MATERIAL_EDITOR_OBJECT_TYPE_CHARACTER = 4
# 材质属性默认的服装编号和槽位
MATERIAL_EDITOR_DEFAULT_COORDINATE = 0
MATERIAL_EDITOR_DEFAULT_SLOT = 0
# lstInfo 里 KKEx 条目的 size 字段(5 字节的 msgpack uint32)
KKEX_SIZE_REGEX = re.compile(
    rb"\xa4name\xa4KKEx\xa7version.{0,8}?\xa3pos.{1,5}?\xa4size\xce(....)", re.DOTALL
)
CARD_MARKER = "【KoiKatuCharaSun】".encode()
# 官方 Koikatsu 人物卡的标记(比 KKS 的少一个 Sun)
KK_CARD_MARKER = "【KoiKatuChara】".encode()
# Parameter 数据块的版本号, KKS 是 0.0.6, KK 是 0.0.5
KKS_PARAMETER_VERSION = b"0.0.6"
KK_PARAMETER_VERSION = b"0.0.5"
# lstInfo 里 Parameter 条目的版本号(msgpack: {name: "Parameter", version: ...})
PARAMETER_LSTINFO_VERSION = (
    b"\xa4name\xa9Parameter\xa7version\xa5" + KKS_PARAMETER_VERSION
)
# Parameter 数据块自己的版本号(紧跟其后的是 sex 字段, 用它和 lstInfo 里的同名条目区分)
PARAMETER_BLOCK_VERSION = b"\xa7version\xa5" + KKS_PARAMETER_VERSION + b"\xa3sex"
# Face 数据里左右眼瞳孔数组(键名 + fixarray(2))以及每一项的 id 字段
FACE_PUPIL_MARKER = b"\xa5pupil\x92"
FACE_PUPIL_ID_MARKER = b"\x88\xa2id"


def get_card_path(chara_name: str) -> Path:
    from hitori_addon.const import KK_CARDS_DIR

    return KK_CARDS_DIR / f"{chara_name}.png"


def set_pupil_overlay(
    card_path: str | Path,
    image_path: str | Path,
    right_image_path: str | Path | None = None,
    texture_id: int = PUPIL_TEXTURE_ID,
    coordinates: Iterable[int] | None = None,
) -> None:
    """把贴图写进人物卡的 KSOX 覆盖层, 用作左右眼的虹膜(瞳孔)

    给了 right_image_path 时右眼用单独的贴图(例如水平镜像)
    """
    image = aspath(image_path).read_bytes()
    right_image = (
        aspath(right_image_path).read_bytes() if right_image_path is not None else None
    )

    def build_value(existing):
        return build_ksox_value(
            image, right_image, texture_id, coordinates, existing=existing
        )

    write_kkex_entry(card_path, KSOX_GUID, build_value)


def set_material_editor_texture(
    card_path: str | Path,
    material_name: str,
    image_path: str | Path,
    property_name: str = "MainTex",
) -> None:
    """把贴图写进人物卡的 Material Editor 数据, 作为某个材质的贴图属性(默认主贴图)

    贴图按内容去重, 也会复用该材质原本的贴图 ID, 重复烘焙不会让人物卡膨胀
    """
    image = aspath(image_path).read_bytes()

    def build_value(existing):
        return build_material_editor_value(
            existing, material_name, property_name, image
        )

    write_kkex_entry(card_path, MATERIAL_EDITOR_GUID, build_value)


def write_kkex_entry(card_path: str | Path, guid: str, build_value) -> None:
    """替换 KKEx 里某个插件的数据块(不存在时新增), 并同步所有长度字段

    build_value 接收该 GUID 原有的值(不存在时为 None), 返回新值
    """
    card_path = aspath(card_path)
    card = card_path.read_bytes()
    block1_start, block1_end, block2_prefix, block2_start = parse_card_offsets(card)
    block1 = card[block1_start:block1_end]
    old_kkex_size = read_kkex_size(block1)
    old_block2_len = struct.unpack_from("<i", card, block2_prefix)[0]
    kkex_start = len(card) - old_kkex_size
    if kkex_start <= block2_start:
        raise ValueError(f"人物卡的 KKEx 数据块位置异常: {card_path}")

    kkex = card[kkex_start:]
    value, value_start, value_end, entry_count, map_header_end = find_kkex_entry(
        kkex, guid
    )
    if value is None:
        new_kkex = (
            msgpack.pack_map_header(entry_count + 1)
            + kkex[map_header_end:]
            + msgpack.packb(guid)
            + msgpack.packb(build_value(None))
        )
    else:
        new_kkex = (
            kkex[:value_start] + msgpack.packb(build_value(value)) + kkex[value_end:]
        )

    new_kkex_size = len(new_kkex)
    new_block2_len = old_block2_len + new_kkex_size - old_kkex_size
    new_card = (
        card[:block1_start]
        + replace_kkex_size(block1, old_kkex_size, new_kkex_size)
        + card[block1_end:block2_prefix]
        + struct.pack("<i", new_block2_len)
        + card[block2_start:kkex_start]
        + new_kkex
    )
    card_path.write_bytes(new_card)


def set_official_pupil_no_iris(card_path: str | Path) -> None:
    """把左右眼的官方瞳孔换成 No Iris zipmod 的空白瞳孔, 并写入 Sideloader 的解析信息

    只改 id 不够: 没有解析信息时 id 1 会被基础表 mt_eye 的"类型 2"占住
    """
    set_pupil_ids(card_path, NO_IRIS_SLOT)
    set_pupil_resolve_info(card_path)


def set_pupil_ids(card_path: str | Path, pupil_id: int) -> bool:
    """把人物卡里左右眼的官方瞳孔改成 pupil_id, 必要时同步长度字段, 返回是否修改过"""
    card_path = aspath(card_path)
    card = card_path.read_bytes()
    block1_start, block1_end, block2_prefix, block2_start = parse_card_offsets(card)
    old_face_size = struct.unpack_from("<i", card, block2_start + 4)[0]
    face_start = block2_start + 8
    face = card[face_start : face_start + old_face_size]
    new_face = replace_pupil_ids(face, pupil_id)
    if new_face == face:
        return False
    delta = len(new_face) - old_face_size
    old_block2_len = struct.unpack_from("<i", card, block2_prefix)[0]
    new_card = (
        card[:block1_start]
        + patch_lstinfo_sizes(card[block1_start:block1_end], delta)
        + card[block1_end:block2_prefix]
        + struct.pack("<i", old_block2_len + delta)
        + card[block2_start : block2_start + 4]
        + struct.pack("<i", old_face_size + delta)
        + new_face
        + card[face_start + old_face_size :]
    )
    card_path.write_bytes(new_card)
    return True


def set_pupil_resolve_info(card_path: str | Path) -> None:
    """把 KKEx 里 Sideloader 解析信息中的左右眼瞳孔指向 No Iris"""
    write_kkex_entry(card_path, UAR_GUID, build_uar_value)


def build_uar_value(existing: list | None = None) -> list:
    """构造 Sideloader 的解析信息 [版本, {'info': [每条 ResolveInfo 的字节]}]"""
    version, data_map = 0, {}
    if (
        isinstance(existing, (list, tuple))
        and len(existing) == 2
        and isinstance(existing[1], dict)
    ):
        version, data_map = existing[0], dict(existing[1])

    infos = [
        info for info in read_uar_infos(data_map) if not is_pupil_resolve_info(info)
    ]
    infos.extend(build_no_iris_resolve_info(name) for name in PUPIL_PROPERTIES)
    data_map["info"] = infos
    return [version, data_map]


def read_uar_infos(data_map: dict) -> list:
    """取 Sideloader 解析信息里的条目列表"""
    infos = data_map.get("info")
    return list(infos) if isinstance(infos, (list, tuple)) else []


def is_pupil_resolve_info(info) -> bool:
    """判断一条解析信息是不是左右眼瞳孔(可能来自别的瞳孔 zipmod)"""
    if not isinstance(info, (bytes, bytearray)):
        return False
    try:
        return msgpack.unpackb(bytes(info)).get("Property") in PUPIL_PROPERTIES
    except (ValueError, IndexError, struct.error, AttributeError):
        return False


def build_no_iris_resolve_info(property_name: str) -> bytes:
    """按 No Iris zipmod 的 manifest 构造一条解析信息(字段与游戏写出的完全一致)"""
    return msgpack.packb(
        {
            "ModID": NO_IRIS_GUID,
            "Slot": NO_IRIS_SLOT,
            "LocalSlot": NO_IRIS_LOCAL_SLOT,
            "Property": property_name,
            "CategoryNo": PUPIL_CATEGORY_NO,
            "Author": NO_IRIS_AUTHOR,
            "Website": NO_IRIS_WEBSITE,
            "Name": NO_IRIS_NAME,
        }
    )


def replace_pupil_ids(face: bytes, pupil_id: int) -> bytes:
    """替换 Face 数据里左右眼瞳孔的 id"""
    offset = face.find(FACE_PUPIL_MARKER)
    if offset < 0:
        raise ValueError("Face 数据里找不到 pupil")
    offset += len(FACE_PUPIL_MARKER)
    value = msgpack.packb(pupil_id)
    pieces = []
    cursor = 0
    for _ in range(2):
        entry = face.find(FACE_PUPIL_ID_MARKER, offset)
        if entry < 0:
            raise ValueError("Face 数据里的 pupil 结构异常")
        start = entry + len(FACE_PUPIL_ID_MARKER)
        _, end = msgpack.unpack_from(face, start)
        pieces.append(face[cursor:start])
        pieces.append(value)
        cursor = end
        offset = end
    pieces.append(face[cursor:])
    return b"".join(pieces)


def patch_lstinfo_sizes(block1: bytes, delta: int) -> bytes:
    """把 lstInfo 里 Custom 的 size 和后续子块的 pos 一起加上 delta"""
    buf = bytearray(block1)
    for name, (pos_offset, size_offset) in find_lstinfo_fields(block1).items():
        value_offset = size_offset if name == "Custom" else pos_offset
        value, end = msgpack.unpack_from(block1, value_offset)
        buf[value_offset:end] = encode_int_like(block1[value_offset:end], value + delta)
    return bytes(buf)


def find_lstinfo_fields(block1: bytes) -> dict:
    """返回 lstInfo 每个条目的 {名字: (pos 值偏移, size 值偏移)}"""
    fields = {}
    for match in re.finditer(rb"\xa4name", block1):
        offset = match.end()
        name, offset = msgpack.unpack_from(block1, offset)
        offsets = {}
        for key in ("version", "pos", "size"):
            actual, offset = msgpack.unpack_from(block1, offset)
            if actual != key:
                raise ValueError(f"lstInfo 结构异常, 期望 {key}")
            offsets[key] = offset
            _, offset = msgpack.unpack_from(block1, offset)
        fields[name] = (offsets["pos"], offsets["size"])
    if not fields:
        raise ValueError("人物卡里找不到 lstInfo 条目")
    return fields


def encode_int_like(old: bytes, value: int) -> bytes:
    """把非负整数编码成和 old 同样的字节长度(msgpack 允许非最短编码)"""
    length = len(old)
    if value < 0:
        raise ValueError(f"不支持的整数: {value}")
    if length == 1:
        if value > 0x7F:
            raise ValueError(f"无法用 1 字节编码整数: {value}")
        return bytes([value])
    prefix = {2: b"\xcc", 3: b"\xcd", 5: b"\xce", 9: b"\xcf"}.get(length)
    if prefix is None or value >= 1 << (8 * (length - 1)):
        raise ValueError(f"整数 {value} 无法用 {length} 字节编码")
    return prefix + value.to_bytes(length - 1, "big")


def reload_kk_card(
    card_path: str | Path, address: str = "127.0.0.1", port: int = 14145
) -> bool:
    """通知游戏只重新读取人物卡, 不清 mod 缓存(比 ClearCacheReadCard 快), 返回是否发出去"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((address, port))
            sock.send(f"ReadCard {aspath(card_path)}".encode())
            winsound.Beep(750, 100)
    except OSError:
        return False
    return True


def parse_card_offsets(card: bytes) -> tuple[int, int, int, int]:
    """解析人物卡, 返回 (block1起始, block1结束, block2长度前缀偏移, block2内容起始)"""
    offset = skip_thumbnail_png(card)
    offset += 4  # productNo
    marker_size = card[offset]
    marker = card[offset + 1 : offset + 1 + marker_size]
    if marker != CARD_MARKER:
        raise ValueError(f"不是 KKS 人物卡, 缺少标记 {CARD_MARKER}")
    offset += 1 + marker_size
    offset += 1 + card[offset]  # 版本号

    block1_start = block1_end = block2_prefix = block2_start = 0
    for block_index in range(3):
        size = struct.unpack_from("<i", card, offset)[0]
        content_start = offset + 4
        if block_index == 1:
            block1_start, block1_end = content_start, content_start + size
        elif block_index == 2:
            block2_prefix, block2_start = offset, content_start
        offset = content_start + size
    return block1_start, block1_end, block2_prefix, block2_start


def skip_thumbnail_png(card: bytes) -> int:
    """跳过人物卡最前面的缩略图 PNG, 返回 PNG 结束之后的偏移"""
    offset = 8  # PNG 签名
    while True:
        size = int.from_bytes(card[offset : offset + 4], "big")
        chunk_type = card[offset + 4 : offset + 8]
        offset += 12 + size
        if chunk_type == b"IEND":
            return offset


def convert_kks_card_to_kk(card: bytes) -> bytes:
    """把 KKS 人物卡的数据转成 KK 人物卡

    KKS 卡和 KK 卡只有三处差别: 卡片标记少一个 Sun(BinaryWriter 的 7bit 长度前缀 21 -> 18),
    lstInfo 里 Parameter 条目的版本号, 以及 Parameter 数据块自己的版本号(都是 0.0.6 -> 0.0.5)。
    其余字节原样搬运, 所以输出只比输入短 3 字节。
    """
    marker_pos = card.find(CARD_MARKER)
    if marker_pos < 0:
        raise ValueError("不是 KKS 人物卡, 缺少卡片标记")
    if card[marker_pos - 1] != len(CARD_MARKER):
        raise ValueError("人物卡的标记长度前缀不对")

    body = card[marker_pos + len(CARD_MARKER) :]
    for pattern in (PARAMETER_LSTINFO_VERSION, PARAMETER_BLOCK_VERSION):
        match_pos = body.find(pattern)
        if match_pos < 0:
            raise ValueError(f"人物卡里找不到 {pattern!r}")
        version_pos = match_pos + pattern.index(KKS_PARAMETER_VERSION)
        body = (
            body[:version_pos]
            + KK_PARAMETER_VERSION
            + body[version_pos + len(KKS_PARAMETER_VERSION) :]
        )

    return card[: marker_pos - 1] + bytes([len(KK_CARD_MARKER)]) + KK_CARD_MARKER + body


def read_kkex_size(block1: bytes) -> int:
    """读取 lstInfo 里 KKEx 条目的数据长度"""
    match = KKEX_SIZE_REGEX.search(block1)
    if not match:
        raise ValueError("人物卡里找不到 KKEx 数据块")
    return int.from_bytes(match.group(1), "big")


def replace_kkex_size(block1: bytes, old_size: int, new_size: int) -> bytes:
    """改写 lstInfo 里 KKEx 条目的数据长度"""
    match = KKEX_SIZE_REGEX.search(block1)
    if not match:
        raise ValueError("人物卡里找不到 KKEx 数据块")
    if int.from_bytes(match.group(1), "big") != old_size:
        raise ValueError("人物卡的 KKEx 数据长度与预期不符")
    if not 0xFFFF < new_size <= 0xFFFFFFFF:
        raise ValueError(f"不支持的 KKEx 数据长度: {new_size}")
    return (
        block1[: match.start(1)] + new_size.to_bytes(4, "big") + block1[match.end(1) :]
    )


def find_kkex_entry(kkex: bytes, guid: str) -> tuple[list | None, int, int, int, int]:
    """在 KKEx 顶层 map 里找插件数据, 返回 (值, 值起始, 值结束, map键值对数量, map头结束偏移)

    找不到时返回 (None, 0, 0, 数量, 头结束偏移)
    """
    entry_count, offset = msgpack.read_map_header(kkex)
    map_header_end = offset
    value = None
    value_start = value_end = 0
    for _ in range(entry_count):
        key, offset = msgpack.unpack_from(kkex, offset)
        if key == guid:
            value_start = offset
            value, offset = msgpack.unpack_from(kkex, offset)
            value_end = offset
        else:
            _, offset = msgpack.unpack_from(kkex, offset)
    if offset != len(kkex):
        raise ValueError("人物卡的 KKEx 数据块解析异常")
    return value, value_start, value_end, entry_count, map_header_end


def build_ksox_value(
    image: bytes,
    right_image: bytes | None = None,
    texture_id: int = PUPIL_TEXTURE_ID,
    coordinates: Iterable[int] | None = None,
    existing: list | None = None,
) -> list:
    """构造 KSOX 的值 [版本, {贴图ID: 图片, Lookup: 服装→类型→贴图ID}]"""
    if (
        isinstance(existing, (list, tuple))
        and len(existing) == 2
        and isinstance(existing[1], dict)
    ):
        version, data_map = existing[0], dict(existing[1])
    else:
        version, data_map = KSOX_VERSION, {}

    data_map[f"_TextureID_{texture_id}"] = image
    right_texture_id = texture_id
    if right_image is not None:
        right_texture_id = texture_id + 1
        data_map[f"_TextureID_{right_texture_id}"] = right_image

    lookup = read_lookup(data_map.get("Lookup"))
    if coordinates is None:
        coordinates = sorted(lookup) or DEFAULT_COORDINATES
    for coordinate in coordinates:
        entries = lookup.get(coordinate)
        if not isinstance(entries, dict):
            entries = {}
            lookup[coordinate] = entries
        entries[TEX_TYPE_EYE_OVER_L] = texture_id
        entries[TEX_TYPE_EYE_OVER_R] = right_texture_id
    data_map["Lookup"] = msgpack.packb(lookup)
    return [version, data_map]


def read_lookup(data) -> dict:
    """解析 KSOX 的 Lookup(服装编号→{类型: 贴图ID})"""
    if not isinstance(data, (bytes, bytearray)):
        return {}
    try:
        lookup = msgpack.unpackb(bytes(data))
    except (ValueError, IndexError, struct.error):
        return {}
    return dict(lookup) if isinstance(lookup, dict) else {}


def build_material_editor_value(
    existing, material_name: str, property_name: str, image: bytes
) -> list:
    """在 Material Editor 数据里设置某个材质的贴图属性, 返回新的插件数据"""
    if (
        isinstance(existing, (list, tuple))
        and len(existing) == 2
        and isinstance(existing[1], dict)
    ):
        version, data = existing[0], dict(existing[1])
    else:
        version, data = MATERIAL_EDITOR_VERSION, {}

    textures = read_material_editor_blob(data.get(MATERIAL_EDITOR_TEXTURES_KEY), {})
    properties = read_material_editor_blob(data.get(MATERIAL_EDITOR_PROPERTIES_KEY), [])
    shaders = read_material_editor_blob(data.get(MATERIAL_EDITOR_SHADERS_KEY), [])

    record = next(
        (
            item
            for item in properties
            if item.get("MaterialName") == material_name
            and item.get("Property") == property_name
        ),
        None,
    )
    tex_id = record.get("TexID") if record is not None else None
    if tex_id is None:
        tex_id = add_material_editor_texture(textures, image)
    else:
        textures[tex_id] = image

    if record is None:
        properties.append(
            build_material_editor_texture_record(
                shaders, material_name, property_name, tex_id
            )
        )
    else:
        record["TexID"] = tex_id

    data[MATERIAL_EDITOR_TEXTURES_KEY] = msgpack.packb(textures)
    data[MATERIAL_EDITOR_PROPERTIES_KEY] = msgpack.packb(properties)
    return [version, data]


def read_material_editor_blob(value, default):
    """解析 Material Editor 里以 msgpack 字节存的数据, 解析不了就用默认值"""
    if isinstance(value, (bytes, bytearray)):
        try:
            parsed = msgpack.unpackb(bytes(value))
        except (ValueError, IndexError, struct.error):
            return default
        if isinstance(parsed, type(default)):
            return parsed
    return default


def add_material_editor_texture(textures: dict, image: bytes) -> int:
    """按内容找已有贴图, 找不到就用最大 ID + 1 新增(与游戏一致)"""
    for tex_id, data in textures.items():
        if data == image:
            return tex_id

    tex_id = max(textures, default=0) + 1
    textures[tex_id] = image
    return tex_id


def build_material_editor_texture_record(
    shaders: list, material_name: str, property_name: str, tex_id: int
) -> dict:
    """构造一条贴图属性记录, 坐标沿用该材质已有的记录(拿不到就用角色本体材质的默认值)"""
    shader = next(
        (item for item in shaders if item.get("MaterialName") == material_name), None
    )
    return {
        "ObjectType": shader.get("ObjectType", MATERIAL_EDITOR_OBJECT_TYPE_CHARACTER)
        if shader
        else MATERIAL_EDITOR_OBJECT_TYPE_CHARACTER,
        "CoordinateIndex": shader.get(
            "CoordinateIndex", MATERIAL_EDITOR_DEFAULT_COORDINATE
        )
        if shader
        else MATERIAL_EDITOR_DEFAULT_COORDINATE,
        "Slot": shader.get("Slot", MATERIAL_EDITOR_DEFAULT_SLOT)
        if shader
        else MATERIAL_EDITOR_DEFAULT_SLOT,
        "MaterialName": material_name,
        "Property": property_name,
        "TexID": tex_id,
        "Offset": None,
        "OffsetOriginal": None,
        "Scale": None,
        "ScaleOriginal": None,
    }
