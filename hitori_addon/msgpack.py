"""极简 msgpack 编解码(只覆盖恋活人物卡用到的类型)

Blender 自带的 Python 没有 msgpack 库, 这里不引入外部依赖
"""

import struct


def packb(value) -> bytes:
    """编码对象, 字符串用 str, bytes 用 bin"""
    parts = []
    _pack(value, parts)
    return b"".join(parts)


def unpackb(data: bytes):
    """解码第一个对象(忽略末尾多余字节)"""
    value, _ = unpack_from(data, 0)
    return value


def unpack_from(data: bytes, offset: int):
    """解码 offset 处的一个对象, 返回 (值, 下一个偏移)"""
    tag = data[offset]
    offset += 1
    if tag <= 0x7F:
        return tag, offset
    if tag >= 0xE0:
        return tag - 0x100, offset
    if 0x80 <= tag <= 0x8F:
        return _unpack_map(data, offset, tag & 0x0F)
    if 0x90 <= tag <= 0x9F:
        return _unpack_array(data, offset, tag & 0x0F)
    if 0xA0 <= tag <= 0xBF:
        size = tag & 0x1F
        return data[offset : offset + size].decode("utf-8"), offset + size
    if tag == 0xC0:
        return None, offset
    if tag == 0xC2:
        return False, offset
    if tag == 0xC3:
        return True, offset
    if tag == 0xC4:
        size = data[offset]
        return bytes(data[offset + 1 : offset + 1 + size]), offset + 1 + size
    if tag == 0xC5:
        size = int.from_bytes(data[offset : offset + 2], "big")
        return bytes(data[offset + 2 : offset + 2 + size]), offset + 2 + size
    if tag == 0xC6:
        size = int.from_bytes(data[offset : offset + 4], "big")
        return bytes(data[offset + 4 : offset + 4 + size]), offset + 4 + size
    if tag == 0xCA:
        return struct.unpack_from(">f", data, offset)[0], offset + 4
    if tag == 0xCB:
        return struct.unpack_from(">d", data, offset)[0], offset + 8
    if tag == 0xCC:
        return data[offset], offset + 1
    if tag == 0xCD:
        return int.from_bytes(data[offset : offset + 2], "big"), offset + 2
    if tag == 0xCE:
        return int.from_bytes(data[offset : offset + 4], "big"), offset + 4
    if tag == 0xCF:
        return int.from_bytes(data[offset : offset + 8], "big"), offset + 8
    if tag == 0xD0:
        return int.from_bytes(data[offset : offset + 1], "big", signed=True), offset + 1
    if tag == 0xD1:
        return int.from_bytes(data[offset : offset + 2], "big", signed=True), offset + 2
    if tag == 0xD2:
        return int.from_bytes(data[offset : offset + 4], "big", signed=True), offset + 4
    if tag == 0xD3:
        return int.from_bytes(data[offset : offset + 8], "big", signed=True), offset + 8
    if tag == 0xD9:
        size = data[offset]
        return data[offset + 1 : offset + 1 + size].decode("utf-8"), offset + 1 + size
    if tag == 0xDA:
        size = int.from_bytes(data[offset : offset + 2], "big")
        return data[offset + 2 : offset + 2 + size].decode("utf-8"), offset + 2 + size
    if tag == 0xDB:
        size = int.from_bytes(data[offset : offset + 4], "big")
        return data[offset + 4 : offset + 4 + size].decode("utf-8"), offset + 4 + size
    if tag == 0xDC:
        size = int.from_bytes(data[offset : offset + 2], "big")
        return _unpack_array(data, offset + 2, size)
    if tag == 0xDD:
        size = int.from_bytes(data[offset : offset + 4], "big")
        return _unpack_array(data, offset + 4, size)
    if tag == 0xDE:
        size = int.from_bytes(data[offset : offset + 2], "big")
        return _unpack_map(data, offset + 2, size)
    if tag == 0xDF:
        size = int.from_bytes(data[offset : offset + 4], "big")
        return _unpack_map(data, offset + 4, size)
    raise ValueError(f"不支持的 msgpack 标记: 0x{tag:02x}")


def read_map_header(data: bytes, offset: int = 0):
    """读取 map 头, 返回 (键值对数量, 头之后的偏移)"""
    tag = data[offset]
    if 0x80 <= tag <= 0x8F:
        return tag & 0x0F, offset + 1
    if tag == 0xDE:
        return int.from_bytes(data[offset + 1 : offset + 3], "big"), offset + 3
    if tag == 0xDF:
        return int.from_bytes(data[offset + 1 : offset + 5], "big"), offset + 5
    raise ValueError(f"不是 msgpack map: 0x{tag:02x}")


def pack_map_header(size: int) -> bytes:
    """只编码 map 头"""
    if size <= 0x0F:
        return bytes([0x80 | size])
    if size <= 0xFFFF:
        return b"\xde" + size.to_bytes(2, "big")
    return b"\xdf" + size.to_bytes(4, "big")


def _pack(value, parts: list):
    if value is None:
        parts.append(b"\xc0")
    elif value is True:
        parts.append(b"\xc3")
    elif value is False:
        parts.append(b"\xc2")
    elif isinstance(value, int):
        parts.append(_pack_int(value))
    elif isinstance(value, float):
        parts.append(b"\xcb" + struct.pack(">d", value))
    elif isinstance(value, str):
        data = value.encode("utf-8")
        parts.append(_pack_str_header(len(data)))
        parts.append(data)
    elif isinstance(value, (bytes, bytearray)):
        data = bytes(value)
        parts.append(_pack_bin_header(len(data)))
        parts.append(data)
    elif isinstance(value, (list, tuple)):
        parts.append(_pack_array_header(len(value)))
        for item in value:
            _pack(item, parts)
    elif isinstance(value, dict):
        parts.append(pack_map_header(len(value)))
        for key, item in value.items():
            _pack(key, parts)
            _pack(item, parts)
    else:
        raise TypeError(f"不支持的 msgpack 类型: {type(value)}")


def _pack_int(value: int) -> bytes:
    if 0 <= value <= 0x7F:
        return bytes([value])
    if -32 <= value < 0:
        return bytes([value & 0xFF])
    if 0 <= value <= 0xFF:
        return b"\xcc" + value.to_bytes(1, "big")
    if 0 <= value <= 0xFFFF:
        return b"\xcd" + value.to_bytes(2, "big")
    if 0 <= value <= 0xFFFFFFFF:
        return b"\xce" + value.to_bytes(4, "big")
    if 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        return b"\xcf" + value.to_bytes(8, "big")
    if -0x80 <= value < 0:
        return b"\xd0" + value.to_bytes(1, "big", signed=True)
    if -0x8000 <= value < 0:
        return b"\xd1" + value.to_bytes(2, "big", signed=True)
    if -0x80000000 <= value < 0:
        return b"\xd2" + value.to_bytes(4, "big", signed=True)
    return b"\xd3" + value.to_bytes(8, "big", signed=True)


def _pack_str_header(size: int) -> bytes:
    if size <= 0x1F:
        return bytes([0xA0 | size])
    if size <= 0xFF:
        return b"\xd9" + size.to_bytes(1, "big")
    if size <= 0xFFFF:
        return b"\xda" + size.to_bytes(2, "big")
    return b"\xdb" + size.to_bytes(4, "big")


def _pack_bin_header(size: int) -> bytes:
    if size <= 0xFF:
        return b"\xc4" + size.to_bytes(1, "big")
    if size <= 0xFFFF:
        return b"\xc5" + size.to_bytes(2, "big")
    return b"\xc6" + size.to_bytes(4, "big")


def _pack_array_header(size: int) -> bytes:
    if size <= 0x0F:
        return bytes([0x90 | size])
    if size <= 0xFFFF:
        return b"\xdc" + size.to_bytes(2, "big")
    return b"\xdd" + size.to_bytes(4, "big")


def _unpack_array(data: bytes, offset: int, size: int):
    values = []
    for _ in range(size):
        value, offset = unpack_from(data, offset)
        values.append(value)
    return values, offset


def _unpack_map(data: bytes, offset: int, size: int):
    values = {}
    for _ in range(size):
        key, offset = unpack_from(data, offset)
        value, offset = unpack_from(data, offset)
        values[key] = value
    return values, offset
