def escape_backslash(data: bytes) -> bytes:
    return data.replace(b"\\", b"\\\\")


def offset_bytes(data: bytes, offset: int, reverse: bool = False) -> bytes:
    return (
        int.from_bytes(data, byteorder="big" if not reverse else "little") + offset
    ).to_bytes(length=len(data), byteorder="big" if not reverse else "little")


def add_len_prefix(data: bytes, offset: int = 0, length: int = 1) -> bytes:
    return (offset + len(data)).to_bytes(length=length, byteorder="big") + data
