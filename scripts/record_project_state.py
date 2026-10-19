"""记录当前 Blender 工程的状态指纹, 用于验证操作前后工程是否被改动.

用法:
  无头快照: <Blender>/blender.exe -b 工程.blend --factory-startup --python scripts/record_project_state.py -- --out 前.json
  界面快照: 在 Blender 文字编辑器中打开本文件直接运行(省略 --out 时输出到 %TEMP%)
  对比快照: <Blender>/blender.exe -b --factory-startup --python scripts/record_project_state.py -- --diff 前.json 后.json

对比模式只读两份 json, 不需要 bpy 参与, 单独运行也算差异处数并打印明细.
"""

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import bpy
import numpy as np

# 浮点位数, 用于抹掉浮点噪声
FLOAT_DIGITS = 6

# 差异明细的打印上限
DIFF_LIMIT = 200

# 明细里每个值的打印上限
VALUE_LIMIT = 200


def round_floats(values) -> list[float]:
    return [round(float(value), FLOAT_DIGITS) for value in values]


def hash_array(values: np.ndarray) -> str:
    return hashlib.sha1(np.ascontiguousarray(values, dtype="f").tobytes()).hexdigest()[
        :16
    ]


def get_mesh_state(mesh) -> dict[str, Any]:
    state: dict[str, Any] = {
        "verts": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polys": len(mesh.polygons),
        "materials": [
            material.name if material else None for material in mesh.materials
        ],
        "attributes": sorted(attribute.name for attribute in mesh.attributes),
    }

    coords = np.empty(len(mesh.vertices) * 3, dtype="f")
    mesh.vertices.foreach_get("co", coords)
    state["coords"] = hash_array(coords)

    uv_layer = mesh.uv_layers.active
    if uv_layer:
        uvs = np.empty(len(mesh.loops) * 2, dtype="f")
        uv_layer.data.foreach_get("uv", uvs)
        state["uvs"] = hash_array(uvs)

    if mesh.shape_keys:
        state["shape_keys"] = [key.name for key in mesh.shape_keys.key_blocks]

    # 顶点组权重没有foreach接口, 逐顶点读取(大网格较慢)
    weights = [
        (vertex.index, group.group, round(group.weight, 4))
        for vertex in mesh.vertices
        for group in vertex.groups
    ]
    state["weights"] = hashlib.sha1(repr(weights).encode()).hexdigest()[:16]
    return state


def get_armature_state(armature) -> dict[str, Any]:
    return {
        "pose_position": armature.pose_position,
        "bones": [
            [
                bone.name,
                bone.parent.name if bone.parent else None,
                round_floats(bone.matrix_local.to_translation()),
            ]
            for bone in armature.bones
        ],
    }


def get_material_state(material) -> dict[str, Any]:
    if not material.use_nodes or not material.node_tree:
        return {"use_nodes": material.use_nodes}

    return {
        "use_nodes": True,
        "nodes": [
            [
                node.name,
                node.type,
                node.image.name if node.type == "TEX_IMAGE" and node.image else None,
            ]
            for node in material.node_tree.nodes
        ],
    }


def get_obj_state(obj) -> dict[str, Any]:
    state: dict[str, Any] = {
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "matrix_world": round_floats(
            [value for row in obj.matrix_world for value in row]
        ),
        "hide": obj.hide_get(),
        "hide_viewport": obj.hide_viewport,
        "hide_render": obj.hide_render,
        "select": obj.select_get(),
        "collections": sorted(collection.name for collection in obj.users_collection),
        "modifiers": [[modifier.name, modifier.type] for modifier in obj.modifiers],
        "vertex_groups": [vertex_group.name for vertex_group in obj.vertex_groups],
    }

    if obj.animation_data:
        action = obj.animation_data.action
        state["action"] = action.name if action else None
        state["nla_tracks"] = [track.name for track in obj.animation_data.nla_tracks]

    if obj.type == "MESH":
        state["mesh"] = get_mesh_state(obj.data)
    elif obj.type == "ARMATURE":
        state["armature"] = get_armature_state(obj.data)
    return state


def get_state() -> dict[str, Any]:
    active_obj = bpy.context.object
    return {
        "filepath": bpy.data.filepath,
        "is_dirty": bpy.data.is_dirty,
        "scene": bpy.context.scene.name,
        "mode": active_obj.mode if active_obj else None,
        "active_obj": active_obj.name if active_obj else None,
        "selected_objs": sorted(obj.name for obj in bpy.context.selected_objects),
        "counts": {
            "objects": len(bpy.data.objects),
            "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials),
            "images": len(bpy.data.images),
            "collections": len(bpy.data.collections),
            "armatures": len(bpy.data.armatures),
            "actions": len(bpy.data.actions),
            "cameras": len(bpy.data.cameras),
            "lights": len(bpy.data.lights),
        },
        "collections": {
            collection.name: sorted(obj.name for obj in collection.objects)
            for collection in bpy.data.collections
        },
        "objects": {obj.name: get_obj_state(obj) for obj in bpy.data.objects},
        "images": {image.name: image.filepath for image in bpy.data.images},
        "materials": {
            material.name: get_material_state(material)
            for material in bpy.data.materials
        },
    }


def dump_state(out_path: Path) -> None:
    state = get_state()
    text = json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")

    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    print(f"工程状态: {out_path}")
    print(f"指纹: {digest}")
    print(
        f"文件: {state['filepath']}  未保存改动: {state['is_dirty']}  模式: {state['mode']}"
    )
    print(f"活动对象: {state['active_obj']}  选中: {state['selected_objs']}")
    print(
        f"数据块: 物体{state['counts']['objects']} 网格{state['counts']['meshes']} "
        f"集合{state['counts']['collections']} 材质{state['counts']['materials']} "
        f"贴图{state['counts']['images']}"
    )


def flatten_state(state: dict[str, Any]) -> dict[str, str]:
    """把嵌套 dict 压平成一层的 路径 -> 值, 便于逐项对比"""
    flat_state: dict[str, str] = {}

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                walk(child, f"{path}.{key}" if path else str(key))
        else:
            flat_state[path] = json.dumps(node, ensure_ascii=False)

    walk(state, "")
    return flat_state


def truncate(value: str) -> str:
    if len(value) <= VALUE_LIMIT:
        return value
    return value[:VALUE_LIMIT] + "..."


def diff_states(
    before: dict[str, Any], after: dict[str, Any]
) -> list[tuple[str, str, str]]:
    before_flat = flatten_state(before)
    after_flat = flatten_state(after)
    missing = "<不存在>"

    return [
        (key, before_flat.get(key, missing), after_flat.get(key, missing))
        for key in sorted(set(before_flat) | set(after_flat))
        if before_flat.get(key, missing) != after_flat.get(key, missing)
    ]


def print_diffs(diffs: list[tuple[str, str, str]]) -> None:
    for key, before, after in diffs[:DIFF_LIMIT]:
        print(f"  {key}")
        print(f"    前: {truncate(before)}")
        print(f"    后: {truncate(after)}")

    if len(diffs) > DIFF_LIMIT:
        print(f"  ...还有 {len(diffs) - DIFF_LIMIT} 处差异未打印")


def get_arg_value(argv: list[str], name: str) -> str:
    if name not in argv:
        raise SystemExit(f"缺少参数: {name}")
    index = argv.index(name)
    if index + 1 >= len(argv):
        raise SystemExit(f"参数 {name} 缺少取值")
    return argv[index + 1]


def main(argv: list[str]) -> None:
    if "--diff" in argv:
        index = argv.index("--diff")
        before_path, after_path = Path(argv[index + 1]), Path(argv[index + 2])
        before = json.loads(before_path.read_text(encoding="utf-8"))
        after = json.loads(after_path.read_text(encoding="utf-8"))

        diffs = diff_states(before, after)
        print(f"对比 {before_path} -> {after_path}")
        print(f"差异 {len(diffs)} 处")
        print_diffs(diffs)
        return

    if "--out" in argv:
        out_path = Path(get_arg_value(argv, "--out"))
    else:
        stem = Path(bpy.data.filepath).stem or "unsaved"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = (
            Path(os.environ.get("TEMP", ".")) / f"hitori_state_{stem}_{timestamp}.json"
        )

    dump_state(out_path)


if __name__ == "__main__":
    # --python 传参时取 `--` 之后的参数
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    main(args)
