"""自己解析 fbx, 拿插件要用的节点顺序 / 网格 / 材质 / 贴图

用来替代 Autodesk 的 fbx pyd: 只读自己刚用 bpy 导出的二进制 fbx,
不需要初始化 SDK 也不需要导入场景, 更快而且没有额外依赖。
节点顺序必须和 SDK / sb3u 一致: 深度优先, 同层按连接顺序。
格式参考 Kaydara FBX Binary (magic + 版本 + 节点树 + fbx 属性表)。
"""

import struct
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, NamedTuple

FBX_BINARY_MAGIC: bytes = b"Kaydara FBX Binary  \x00\x1a\x00"
FBX_MIN_VERSION: int = 7000
FBX_64BIT_VERSION: int = 7500
# 一层节点结束时的空记录字节数
NULL_RECORD_SIZES: tuple[int, int] = (13, 25)
# 数组属性的元素字节数 (只跳过长度的, 不解析内容)
ARRAY_ITEM_SIZES: Mapping[bytes, int] = MappingProxyType(
    {b"f": 4, b"i": 4, b"d": 8, b"l": 8, b"b": 1}
)
# 对象名存成 '名字\x00\x01类型', 取名字时切掉后缀
NAME_SEPARATOR: str = "\x00\x01"
# 材质上要读的贴图属性
TEXTURE_PROPERTY_NAMES: tuple[str, ...] = ("DiffuseColor", "NormalMap")
# 只解这些节点的属性 (数组属性一律跳过, 所以很快)
PROPERTY_NODE_NAMES = frozenset(
    {
        "Model",
        "Material",
        "Texture",
        "NodeAttribute",
        "Geometry",
        "C",
        "FileName",
        "RelativeFilename",
    }
)
# 只往这些节点里面走
CHILD_NODE_NAMES = frozenset({"Objects", "Connections", "Texture"})


class FbxError(RuntimeError):
    """fbx 文件读不了"""


class FbxModel(NamedTuple):
    """fbx 里的一个模型节点 (sb3u 里的一帧)"""

    uid: int
    name: str
    type: str


class FbxScene:
    """解析出来的 fbx 场景信息"""

    __slots__ = ("mesh_materials_textures", "models", "path")

    def __init__(
        self,
        path: Path,
        models: list[FbxModel],
        mesh_materials_textures: dict[int, dict[str, dict[str, str | None]]],
    ) -> None:
        self.path = path
        # 深度优先的模型节点 (只含带属性对象的, 和 SDK 的 node.GetNodeAttribute() 一致)
        self.models = models
        # 网格 uid -> {材质名: {'DiffuseColor': 贴图路径或 None, 'NormalMap': ...}}
        self.mesh_materials_textures = mesh_materials_textures


def _read_property(data: bytes, pos: int) -> tuple[Any, int]:
    """读一个属性, 返回 (值, 新位置); 数组只算长度不解析"""
    code = data[pos : pos + 1]
    pos += 1
    if code == b"Y":
        return struct.unpack_from("<h", data, pos)[0], pos + 2
    if code == b"C":
        return bool(data[pos]), pos + 1
    if code == b"I":
        return struct.unpack_from("<i", data, pos)[0], pos + 4
    if code == b"F":
        return struct.unpack_from("<f", data, pos)[0], pos + 4
    if code == b"D":
        return struct.unpack_from("<d", data, pos)[0], pos + 8
    if code == b"L":
        return struct.unpack_from("<q", data, pos)[0], pos + 8
    if code in ARRAY_ITEM_SIZES:
        array_len, encoding, compressed_len = struct.unpack_from("<III", data, pos)
        if encoding:
            return None, pos + 12 + compressed_len
        return None, pos + 12 + array_len * ARRAY_ITEM_SIZES[code]
    if code in (b"S", b"R"):
        str_len = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        raw = data[pos : pos + str_len]
        if code == b"S":
            return raw.decode("utf-8", "replace"), pos + str_len
        return raw, pos + str_len
    raise FbxError(f"未知的 fbx 属性类型: {code!r}")


def _read_node_header(
    data: bytes,
    pos: int,
    is64: bool,
) -> tuple[int, int, int, str, int]:
    """读节点头, 返回 (节点结束位置, 属性个数, 属性区字节数, 名字, 属性区起点)"""
    if is64:
        end_offset, property_count, property_bytes = struct.unpack_from(
            "<QQQ", data, pos
        )
        pos += 24
    else:
        end_offset, property_count, property_bytes = struct.unpack_from(
            "<III", data, pos
        )
        pos += 12
    name_len = data[pos]
    name_start = pos + 1
    name = data[name_start : name_start + name_len].decode("utf-8", "replace")
    return end_offset, property_count, property_bytes, name, name_start + name_len


def _parse_nodes(
    data: bytes, pos: int, is64: bool
) -> list[tuple[str, list[Any] | None, list]]:
    """按层遍历节点, 只解需要的属性, 只进需要的子层"""
    null_size = NULL_RECORD_SIZES[is64]
    nodes = []
    while data[pos : pos + null_size] != b"\x00" * null_size:
        end_offset, property_count, property_bytes, name, property_pos = (
            _read_node_header(data, pos, is64)
        )
        properties = None
        if name in PROPERTY_NODE_NAMES:
            properties = []
            for _ in range(property_count):
                value, property_pos = _read_property(data, property_pos)
                properties.append(value)
        # 子节点位置以节点头里写的属性区长度为准, 属性解析有偏差也不影响往下走
        children_pos = (
            property_pos + property_bytes if properties is None else property_pos
        )
        children = (
            _parse_nodes(data, children_pos, is64) if name in CHILD_NODE_NAMES else []
        )
        nodes.append((name, properties, children))
        pos = end_offset
    return nodes


def _get_object_name(properties: list[Any]) -> str:
    return str(properties[1]).split(NAME_SEPARATOR)[0]


def _get_texture_path(children: list[tuple[str, list[Any] | None, list]]) -> str | None:
    for name, properties, _ in children:
        if name == "FileName" and properties:
            return str(properties[0])
    return None


def _get_objects(
    nodes: list[tuple[str, list[Any] | None, list]],
) -> tuple[dict[int, str], dict[int, str], dict[int, str], dict[int, str | None]]:
    """列出 fbx 对象, 返回 (模型名, 属性类型, 材质名, 贴图路径)"""
    model_names: dict[int, str] = {}
    attribute_types: dict[int, str] = {}
    material_names: dict[int, str] = {}
    texture_paths: dict[int, str | None] = {}
    for name, properties, children in nodes:
        if not properties or not isinstance(properties[0], int):
            continue
        uid = properties[0]
        if name == "Model":
            model_names[uid] = _get_object_name(properties)
        elif name in ("NodeAttribute", "Geometry"):
            # 网格节点的属性对象就是 Geometry (fbx 里 FbxMesh 本身也是节点属性)
            attribute_types[uid] = str(properties[2])
        elif name == "Material":
            material_names[uid] = _get_object_name(properties)
        elif name == "Texture":
            texture_paths[uid] = _get_texture_path(children)
    return model_names, attribute_types, material_names, texture_paths


def _get_connections(
    nodes: list[tuple[str, list[Any] | None, list]],
) -> tuple[list[tuple[int, int]], list[tuple[int, int, str | None]]]:
    """列出连接: 对象连对象, 属性连对象 (材质上的贴图)"""
    object_connections: list[tuple[int, int]] = []
    property_connections: list[tuple[int, int, str | None]] = []
    for _, properties, _ in nodes:
        if not properties or len(properties) < 3:
            continue
        if properties[0] == "OO":
            object_connections.append((properties[1], properties[2]))
        elif properties[0] == "OP":
            property_connections.append(
                (
                    properties[1],
                    properties[2],
                    properties[3] if len(properties) > 3 else None,
                )
            )
    return object_connections, property_connections


def get_fbx_scene(filepath: str | Path) -> FbxScene:
    """读 fbx 文件, 得到插件要用的场景信息"""
    filepath = Path(filepath)
    data = filepath.read_bytes()
    if not data.startswith(FBX_BINARY_MAGIC):
        raise FbxError(f"不是二进制 fbx 文件: {filepath}")
    version = struct.unpack_from("<I", data, len(FBX_BINARY_MAGIC))[0]
    if version < FBX_MIN_VERSION:
        raise FbxError(f"fbx 版本太旧 ({version}): {filepath}")
    is64 = version >= FBX_64BIT_VERSION

    try:
        top_nodes = _parse_nodes(data, len(FBX_BINARY_MAGIC) + 4, is64)
        sections = {name: children for name, _, children in top_nodes}
        model_names, attribute_types, material_names, texture_paths = _get_objects(
            sections["Objects"]
        )
        object_connections, property_connections = _get_connections(
            sections["Connections"]
        )

        root_uids: list[int]
        child_uids_map: dict[int, list[int]] = {}
        material_uids_map: dict[int, list[int]] = {}
        model_attribute_types: dict[int, str] = {}
        model_parent_uids = set()
        for child_uid, parent_uid in object_connections:
            if child_uid in model_names:
                # 模型连模型才是节点父子关系 (模型还会连到自己的 Deformer 之类)
                if parent_uid in model_names:
                    child_uids_map.setdefault(parent_uid, []).append(child_uid)
                    model_parent_uids.add(child_uid)
            elif child_uid in material_names:
                material_uids_map.setdefault(parent_uid, []).append(child_uid)
            elif child_uid in attribute_types:
                model_attribute_types.setdefault(parent_uid, attribute_types[child_uid])
        # 没有父模型的节点就是顶层节点 (父是场景根 uid 0)
        root_uids = list(
            dict.fromkeys(
                child_uid
                for child_uid, parent_uid in object_connections
                if child_uid in model_names and child_uid not in model_parent_uids
            )
        )

        material_texture_paths: dict[int, dict[str, str | None]] = {}
        for child_uid, parent_uid, property_name in property_connections:
            if property_name in TEXTURE_PROPERTY_NAMES and child_uid in texture_paths:
                material_texture_paths.setdefault(parent_uid, {}).setdefault(
                    property_name, texture_paths[child_uid]
                )

        # 深度优先的节点顺序 (同层按连接顺序)
        models: list[FbxModel] = []
        stack = list(reversed(root_uids))
        while stack:
            uid = stack.pop()
            if uid in model_attribute_types:
                models.append(
                    FbxModel(uid, model_names[uid], model_attribute_types[uid])
                )
            stack.extend(reversed(child_uids_map.get(uid, ())))

        mesh_materials_textures: dict[int, dict[str, dict[str, str | None]]] = {}
        for model in models:
            if model.type != "Mesh":
                continue
            materials_textures: dict[str, dict[str, str | None]] = {}
            for material_uid in material_uids_map.get(model.uid, ()):
                textures = dict.fromkeys(TEXTURE_PROPERTY_NAMES)
                for property_name, texture_path in material_texture_paths.get(
                    material_uid, {}
                ).items():
                    if property_name in textures:
                        textures[property_name] = texture_path
                materials_textures[material_names[material_uid]] = textures
            mesh_materials_textures[model.uid] = materials_textures
    except (KeyError, struct.error, IndexError) as error:
        raise FbxError(f"fbx 文件解析失败: {filepath} ({error})") from error

    return FbxScene(filepath, models, mesh_materials_textures)


def get_scene_frames(
    scene: FbxScene, types: tuple[str, ...] = ("Null", "LimbNode")
) -> list[str]:
    return [model.name for model in scene.models if model.type in types]


def get_scene_meshes(scene: FbxScene, types: tuple[str, ...] = ("Mesh",)) -> list[str]:
    return [model.name for model in scene.models if model.type in types]


def get_scene_meshes_materials_textures(
    scene: FbxScene,
) -> dict[str, dict[str, dict[str, str | None]]]:
    return {
        model.name: scene.mesh_materials_textures[model.uid]
        for model in scene.models
        if model.uid in scene.mesh_materials_textures
    }


def process_meshes_materials_textures(
    meshes_materials_textures: dict[str, dict[str, dict[str, str | None]]],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """网格名 / 材质名 / 漫反射贴图 / 法线贴图 (按出现顺序去重)"""
    meshes = list(meshes_materials_textures.keys())

    materials = list(
        dict.fromkeys(
            material
            for secondary_dict in meshes_materials_textures.values()
            for material in secondary_dict
        )
    )

    diffuses = list(
        dict.fromkeys(
            texture["DiffuseColor"]
            for secondary_dict in meshes_materials_textures.values()
            for texture in secondary_dict.values()
            if texture.get("DiffuseColor") is not None
        )
    )

    normal_maps = list(
        dict.fromkeys(
            texture["NormalMap"]
            for secondary_dict in meshes_materials_textures.values()
            for texture in secondary_dict.values()
            if texture.get("NormalMap") is not None
        )
    )

    return meshes, materials, diffuses, normal_maps


def get_fbx_frames(filepath: str | Path) -> list[str]:
    return get_scene_frames(get_fbx_scene(filepath))


def get_fbx_meshes(filepath: str | Path) -> list[str]:
    return get_scene_meshes(get_fbx_scene(filepath))


def get_fbx_meshes_materials_textures(
    filepath: str | Path,
) -> dict[str, dict[str, dict[str, str | None]]]:
    return get_scene_meshes_materials_textures(get_fbx_scene(filepath))
