"""从官模 bodytight 生成烘焙目标网格 (只保留被源网格覆盖的面) 与可选罩体 (cage)

替代"手工从全身 bodytight 里挑区域 + 重新展 UV"的步骤。
目标网格 = bodytight 的面子集 (带官方顶点组权重) + 重展 UV, 面积小则同分辨率下烘焙密度更高。
"""

import hashlib
import re
from collections.abc import Iterable, Sequence

import bpy
import numpy as np
from bpy.types import Material, Object
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

from hitori_addon.const import require_external_resources
from hitori_addon.error import ObjectError
from hitori_addon.material import set_simple_material
from hitori_addon.math import vecs_apply_mat
from hitori_addon.mesh import (
    get_coordinates_arr,
    get_face_centers_arr,
    get_vertex_normals_arr,
    selected_meshes,
)
from hitori_addon.obj import copy_obj, get_obj, reset_mode, select_obj, set_mode
from hitori_addon.sb3u import CLOTH_MESH_NAMES
from hitori_addon.template_link import BODYTIGHT_NAME, TEMPLATE_BLEND
from hitori_addon.vg import delete_empty_vgs, set_skip_transfer_group

DEFAULT_DISTANCE = 0.01
DEFAULT_CAGE_DISTANCE = 0.002
# 距离阈值对用户按 mm 输入, 内部一律用米
DEFAULT_DISTANCE_MM = DEFAULT_DISTANCE * 1000
DEFAULT_GROW = 1
# 投影判定的最大间隙: 宽松服装(松口袜等)与 bodytight 可能差几厘米, 超过这个距离视为与 bodytight 无关
MAX_PROJECTION_GAP = 0.1
# 烘焙产物上记录源物体的属性(存 ID 指针, 随 blend 保存); 存在该属性的产物直接复用
BAKE_SOURCE_PROPERTY = "hitori_bake_source"
# 生成产物时源网格的指纹, 源网格改过后产物与它对不上, 要重建
BAKE_SOURCE_HASH_PROPERTY = "hitori_bake_source_hash"
# 产物的烘焙贴图分辨率, 记在产物上(想换分辨率就删掉产物)
BAKE_SIZE_PROPERTY = "hitori_bake_size"
# 产物的生成参数 (距离阈值 / 扩圈 / 罩体), 记在产物上(想改参数就删掉产物)
BAKE_DISTANCE_PROPERTY = "hitori_bake_distance"
BAKE_GROW_PROPERTY = "hitori_bake_grow"
BAKE_CAGE_PROPERTY = "hitori_bake_cage"
BAKE_FILL_HOLES_PROPERTY = "hitori_bake_fill_holes"
DEFAULT_FILL_HOLES = True
# 源网格名带这些前后缀表示“要烘的是这件”, 去掉后是合法服装名时产物直接用它
BAKE_NAME_AFFIXES = ("_bake", "-bake", "bake_", "bake-")


def get_world_coordinates_arr(obj: Object) -> np.ndarray:
    return vecs_apply_mat(get_coordinates_arr(obj), obj.matrix_world)


def get_world_face_centers_arr(obj: Object) -> np.ndarray:
    return vecs_apply_mat(get_face_centers_arr(obj), obj.matrix_world)


def build_bvh_from_object(obj: Object) -> BVHTree:
    """用求值后的网格建 BVH(包含修改器结果)"""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        matrix = eval_obj.matrix_world
        vertices = [matrix @ vertex.co for vertex in mesh.vertices]
        polygons = [tuple(polygon.vertices) for polygon in mesh.polygons]
        return BVHTree.FromPolygons(vertices, polygons, all_triangles=False)
    finally:
        eval_obj.to_mesh_clear()


def ensure_bodytight() -> Object:
    """场景里没有 bodytight 时从 official_template.blend 追加一份(不复制骨架, 只读 rest 坐标)"""
    bodytight = get_obj(BODYTIGHT_NAME)
    if bodytight:
        return bodytight

    require_external_resources()
    with bpy.data.libraries.load(str(TEMPLATE_BLEND)) as (data_from, data_to):
        names = [name for name in data_from.objects if name == BODYTIGHT_NAME]
        data_to.objects = names
    if not data_to.objects:
        raise RuntimeError(f"{TEMPLATE_BLEND} 里没有 {BODYTIGHT_NAME}")

    for obj in data_to.objects:
        bpy.context.collection.objects.link(obj)
    return get_obj(BODYTIGHT_NAME)


def _nearest_distances(bvh: BVHTree, points: np.ndarray) -> np.ndarray:
    return np.array([bvh.find_nearest(point)[3] for point in points], dtype=float)


def find_covered_face_indices(
    bodytight: Object,
    src_objs: Sequence[Object],
    distance: float = DEFAULT_DISTANCE,
) -> np.ndarray:
    """bodytight 中被任一源网格覆盖的面索引

    覆盖 = 面中心到源网格表面 < distance, 或源网格的顶点/面中心最近投影落在该面上。
    只用前者时, 与 bodytight 有明显间隙的宽松服装(过膝袜等)只能选出零星的面, 生成的目标网格会破碎。
    """
    centers = get_world_face_centers_arr(bodytight)
    covered = np.zeros(len(centers), dtype=bool)
    bodytight_bvh = build_bvh_from_object(bodytight)
    for src_obj in src_objs:
        covered |= _nearest_distances(build_bvh_from_object(src_obj), centers) < distance
        points = np.vstack(
            (
                get_world_coordinates_arr(src_obj),
                get_world_face_centers_arr(src_obj),
            )
        )
        for point in points:
            _, _, face_index, gap = bodytight_bvh.find_nearest(point)
            if face_index is not None and gap <= MAX_PROJECTION_GAP:
                covered[face_index] = True
    return np.where(covered)[0]


def grow_face_selection(
    mesh, face_indices: Iterable[int], rings: int = DEFAULT_GROW
) -> np.ndarray:
    """把选区沿公共顶点向外扩 rings 圈(保守: 宁可多留一行面)"""
    selected = {int(index) for index in face_indices}
    if rings <= 0 or not selected:
        return np.array(sorted(selected), dtype=int)

    # 必须统计整张网格的相邻关系, 只统计选中的面时永远找不到未选中的邻居
    vertex_to_faces: dict[int, list[int]] = {}
    for polygon in mesh.polygons:
        for vertex_index in polygon.vertices:
            vertex_to_faces.setdefault(vertex_index, []).append(polygon.index)

    for _ in range(rings):
        neighbor_faces: set[int] = set()
        for face_index in selected:
            for vertex_index in mesh.polygons[face_index].vertices:
                neighbor_faces.update(vertex_to_faces.get(vertex_index, ()))
        new_faces = neighbor_faces - selected
        if not new_faces:
            break
        selected |= new_faces
    return np.array(sorted(selected), dtype=int)


def copy_subset_vertex_groups(
    src_obj: Object, dst_obj: Object, used_vertex_indices: Sequence[int]
) -> None:
    """按 idx -> 新顶点下标 的对应关系复制顶点组与权重(组名与顺序一并保留)"""
    src_vertices = src_obj.data.vertices
    for vg in src_obj.vertex_groups:
        dst_obj.vertex_groups.new(name=vg.name)
    for new_index, old_index in enumerate(used_vertex_indices):
        for group in src_vertices[old_index].groups:
            if group.weight:
                dst_obj.vertex_groups[group.group].add(
                    [new_index], group.weight, "REPLACE"
                )


def copy_subset_shading(
    src_obj: Object, dst_mesh, face_indices: Sequence[int]
) -> None:
    """复制平滑着色标志与自定义拆边法线

    官模靠自定义法线做平滑, 不复制的话取子网格后所有面都是平面的, 材质模式下棱角分明。
    目标网格顶点存的是世界坐标, 而拆边法线存在局部空间, 所以要按源物体的变换转过去。
    """
    src_mesh = src_obj.data
    smooth_flags = np.empty(len(src_mesh.polygons), dtype=bool)
    src_mesh.polygons.foreach_get("use_smooth", smooth_flags)
    dst_mesh.polygons.foreach_set("use_smooth", smooth_flags[list(face_indices)])
    dst_mesh.update()

    if not src_mesh.has_custom_normals:
        return

    src_mesh.calc_normals_split()
    loop_normals = np.empty((len(src_mesh.loops), 3), "f")
    src_mesh.loops.foreach_get("normal", loop_normals.ravel())
    new_loop_normals = np.empty((len(dst_mesh.loops), 3), "f")
    for new_face_index, old_face_index in enumerate(face_indices):
        new_polygon = dst_mesh.polygons[new_face_index]
        old_polygon = src_mesh.polygons[old_face_index]
        new_loop_normals[
            new_polygon.loop_start : new_polygon.loop_start + new_polygon.loop_total
        ] = loop_normals[
            old_polygon.loop_start : old_polygon.loop_start + old_polygon.loop_total
        ]

    # 法线用逆转置矩阵变换(纯旋转时等于原矩阵), 再归一化
    normal_matrix = src_obj.matrix_world.to_3x3().inverted_safe().transposed()
    new_loop_normals = np.array(new_loop_normals, dtype=float) @ np.asarray(
        normal_matrix
    ).T
    lengths = np.linalg.norm(new_loop_normals, axis=1, keepdims=True)
    new_loop_normals /= np.where(lengths == 0, 1, lengths)

    dst_mesh.use_auto_smooth = src_mesh.use_auto_smooth
    dst_mesh.auto_smooth_angle = src_mesh.auto_smooth_angle
    dst_mesh.normals_split_custom_set(new_loop_normals.tolist())
    dst_mesh.update()


def copy_subset_edge_seams(
    src_mesh, dst_mesh, used_vertex_indices: Sequence[int]
) -> None:
    """复制缝合边标志(展 UV 时要靠它切缝)"""
    if len(src_mesh.edges) == 0 or len(dst_mesh.edges) == 0:
        return

    src_edge_vertices = np.empty(len(src_mesh.edges) * 2, dtype=np.int32)
    src_mesh.edges.foreach_get("vertices", src_edge_vertices)
    src_edge_vertices = src_edge_vertices.reshape(-1, 2).astype(np.int64)
    src_edge_vertices.sort(axis=1)
    src_seams = np.empty(len(src_mesh.edges), dtype=bool)
    src_mesh.edges.foreach_get("use_seam", src_seams)

    dst_edge_vertices = np.empty(len(dst_mesh.edges) * 2, dtype=np.int32)
    dst_mesh.edges.foreach_get("vertices", dst_edge_vertices)
    dst_edge_vertices = dst_edge_vertices.reshape(-1, 2).astype(np.int64)

    # 两条边的顶点对编码成一个整数, 就不用逐边做 tuple 排序和集合查询
    key_scale = int(max(src_edge_vertices.max(), dst_edge_vertices.max())) + 1
    seam_keys = (
        src_edge_vertices[src_seams, 0] * key_scale + src_edge_vertices[src_seams, 1]
    )
    mapped_vertices = np.asarray(used_vertex_indices, dtype=np.int64)[
        dst_edge_vertices
    ]
    dst_keys = mapped_vertices.min(axis=1) * key_scale + mapped_vertices.max(axis=1)

    dst_seams = np.isin(dst_keys, seam_keys)
    dst_mesh.edges.foreach_set("use_seam", dst_seams)
    dst_mesh.update()


def set_parent_keep_world(obj: Object, parent: Object | None) -> None:
    """挂到指定父级下并保持当前世界矩阵(网格存的是世界坐标, 必须留在单位阵)"""
    if parent is None:
        return
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.matrix_world = Matrix.Identity(4)


def make_target_material(name: str) -> Material:
    """目标网格的新材质: 只有基础 BSDF 与材质输出(自动缩裹烘焙时会被换成贴图材质)"""
    material = bpy.data.materials.new(name)
    set_simple_material(material)
    return material


def make_subset_obj(
    bodytight: Object,
    face_indices: Sequence[int],
    name: str,
    parent: Object | None = None,
) -> Object:
    """按面索引从 bodytight 取子网格

    只保留用到的顶点, 复制 UV / 着色标志与自定义法线 / 顶点组权重, 并删掉取子网格后变空的顶点组。
    产物自带官方权重, 所以整片标记成 skip_transfer_group (不参与传权重)。
    新物体用单位矩阵, 所以坐标直接存世界坐标: bodytight 自带 -90 度 X 旋转, 存局部坐标会横躺。
    材质不继承官方材质, 新建一个同名材质(自动缩裹烘焙时会被换成贴图材质)。
    """
    src_mesh = bodytight.data
    face_indices = [int(index) for index in face_indices]
    used_vertex_indices = sorted(
        {
            vertex
            for index in face_indices
            for vertex in src_mesh.polygons[index].vertices
        }
    )
    remap = {old: new for new, old in enumerate(used_vertex_indices)}

    src_coords = get_world_coordinates_arr(bodytight)
    vertices = [tuple(src_coords[old]) for old in used_vertex_indices]
    polygons = [
        tuple(remap[vertex] for vertex in src_mesh.polygons[index].vertices)
        for index in face_indices
    ]

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], polygons)
    mesh.update()

    copy_subset_shading(bodytight, mesh, face_indices)
    copy_subset_edge_seams(src_mesh, mesh, used_vertex_indices)

    for uv_layer in src_mesh.uv_layers:
        new_uv_layer = mesh.uv_layers.new(name=uv_layer.name)
        for new_face_index, old_face_index in enumerate(face_indices):
            old_loop_start = src_mesh.polygons[old_face_index].loop_start
            new_loop_start = mesh.polygons[new_face_index].loop_start
            count = src_mesh.polygons[old_face_index].loop_total
            for offset in range(count):
                new_uv_layer.data[new_loop_start + offset].uv = uv_layer.data[
                    old_loop_start + offset
                ].uv

    mesh.materials.append(make_target_material(name))

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    copy_subset_vertex_groups(bodytight, obj, used_vertex_indices)
    delete_empty_vgs(obj)
    set_skip_transfer_group(obj, range(len(mesh.vertices)))
    set_parent_keep_world(obj, parent)
    return obj


@reset_mode
def unwrap_uv(obj: Object, island_margin: float = 0.003) -> None:
    """按缝合边展开 UV 并铺满 0-1(smart_project 不认缝合边, 所以用平展 + 打包)"""
    select_obj(obj)
    set_mode("EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=island_margin)
    bpy.ops.uv.pack_islands(rotate=True, margin=island_margin)
    set_mode("OBJECT")


def make_cage(
    target: Object, name: str | None = None, distance: float = DEFAULT_CAGE_DISTANCE
) -> Object:
    """罩体 = 目标网格沿法线外扩 distance"""
    cage = copy_obj(target, name=name or f"{target.name}_cage")
    # 罩体不是烘焙产物: 清掉复制过来的产物属性, 免得产物被删后它被当成产物复用
    for key in list(cage.keys()):
        if key.startswith("hitori_bake_"):
            del cage[key]
    coords = get_coordinates_arr(cage)
    normals = get_vertex_normals_arr(cage)
    cage.data.vertices.foreach_set("co", (coords + normals * distance).ravel())
    cage.data.update()
    return cage


def get_legal_cloth_name(name: str) -> str | None:
    """名字去掉 bake 前后缀后是合法服装名就返回它, 否则 None

    `.001` 这类 Blender 重名后缀先剥掉再比; 合法名见 `CLOTH_MESH_NAMES`(不含 acc / hair)。
    `cloth_top_bake` / `bake-cloth_top` -> `cloth_top`, 而 `cloth_top` / `Shorts_bake` -> None。
    """
    stem = re.sub(r"\.\d+$", "", name)
    for affix in BAKE_NAME_AFFIXES:
        if stem.endswith(affix) and len(stem) > len(affix):
            stem = stem[: -len(affix)]
            break
        if stem.startswith(affix) and len(stem) > len(affix):
            stem = stem[len(affix) :]
            break
    else:
        return None
    stem = re.sub(r"\.\d+$", "", stem)
    return stem if stem in CLOTH_MESH_NAMES else None


def get_target_name(src_obj: Object) -> str:
    """产物名: 源网格带 bake 前后缀就用合法服装名(它就是烘焙贴图名), 否则 `<源名>_target`"""
    return get_legal_cloth_name(src_obj.name) or f"{src_obj.name}_target"


def generate_target(
    src_obj: Object,
    distance: float = DEFAULT_DISTANCE,
    grow: int = DEFAULT_GROW,
    unwrap: bool = True,
    cage: bool = False,
    cage_distance: float = DEFAULT_CAGE_DISTANCE,
    fill_holes: bool = DEFAULT_FILL_HOLES,
) -> tuple[Object, Object | None]:
    bodytight = ensure_bodytight()
    face_indices = find_covered_face_indices(bodytight, [src_obj], distance)
    if len(face_indices) == 0:
        raise ObjectError(
            src_obj,
            f"在 bodytight 上找不到与 {src_obj.name!r} 相距 {format_distance(distance)} 内的面, 请调大距离",
        )
    if fill_holes:
        face_indices = np.union1d(
            face_indices, find_interior_holes(bodytight, face_indices, [src_obj])
        )
    face_indices = grow_face_selection(bodytight.data, face_indices, grow)

    target = make_subset_obj(
        bodytight, face_indices, get_target_name(src_obj), parent=src_obj.parent
    )
    bind_bake_source(target, src_obj)
    set_target_params(target, distance, grow, cage, fill_holes)
    target[BAKE_SOURCE_HASH_PROPERTY] = get_source_signature(
        src_obj, distance, grow, cage, fill_holes
    )
    if unwrap:
        unwrap_uv(target)
    cage_obj = None
    if cage:
        # 清掉同名残留的罩体, 免得新罩体被改名成 .001
        stale = bpy.data.objects.get(f"{target.name}_cage")
        if stale is not None:
            bpy.data.objects.remove(stale, do_unlink=True)
        cage_obj = make_cage(target, distance=cage_distance)
    return target, cage_obj


def bind_bake_source(target: Object, src_obj: Object) -> None:
    """把烘焙产物绑定到源物体"""
    target[BAKE_SOURCE_PROPERTY] = src_obj


def get_group_weight_digest(obj: Object, group_names: Sequence[str]) -> dict[str, str]:
    """这几个顶点组的权重指纹(一次遍历), 用来发现用户改过顶点归属"""
    names = list(dict.fromkeys(group_names))
    names = [name for name in names if obj.vertex_groups.get(name) is not None]
    if not names:
        return {}
    columns = {obj.vertex_groups[name].index: i for i, name in enumerate(names)}
    matrix = np.zeros((len(obj.data.vertices), len(names)))
    for vertex in obj.data.vertices:
        for element in vertex.groups:
            column = columns.get(element.group)
            if column is not None:
                matrix[vertex.index, column] = element.weight
    return {
        name: hashlib.md5(np.round(matrix[:, i], 4).tobytes()).hexdigest()[:8]
        for i, name in enumerate(names)
    }


def get_shrinkwrap_signature(obj: Object) -> str:
    """缩裹修改器的参数指纹: 改过偏移 / 方式 / 顶点组归属就算源网格变了"""
    shrinkwraps = [m for m in obj.modifiers if m.type == "SHRINKWRAP"]
    digests = get_group_weight_digest(
        obj, [m.vertex_group for m in shrinkwraps if m.vertex_group]
    )
    parts = []
    for modifier in shrinkwraps:
        target = modifier.target.name if modifier.target else ""
        weights = digests.get(modifier.vertex_group, "")
        parts.append(
            f"{modifier.name}:{modifier.offset:.6g}/{modifier.wrap_method}/"
            f"{modifier.wrap_mode}/{target}/{modifier.vertex_group}:{weights}"
        )
    return "|".join(parts)


def get_source_signature(
    src_obj: Object, distance: float, grow: int, cage: bool, fill_holes: bool
) -> str:
    """源网格顶点(世界坐标) + 缩裹参数 + 生成参数的指纹

    只看基础网格, 不看求值后的结果: 摆姿势不算改网格, 不然每次换姿势都要重建产物。
    """
    coords = get_world_coordinates_arr(src_obj)
    # 量化到 1 微米, 避免浮点噪声误判
    digest = hashlib.md5(np.round(coords, 6).tobytes()).hexdigest()[:12]
    shrinkwrap = get_shrinkwrap_signature(src_obj)
    return (
        f"{digest}-{len(coords)}x{len(src_obj.data.polygons)}-"
        f"{distance:g}-{grow}-{int(cage)}-{int(fill_holes)}-{shrinkwrap}"
    )


def remove_bake_target(target: Object) -> None:
    """删掉失效的产物与它的罩体"""
    for name in (target.name, f"{target.name}_cage"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)


def find_bake_target(src_obj: Object) -> Object | None:
    """按 `hitori_bake_source` 属性找源物体对应的烘焙产物"""
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.get(BAKE_SOURCE_PROPERTY) == src_obj:
            return obj
    return None


def get_target_params(target: Object) -> tuple[float, int, bool, bool] | None:
    """产物上记的生成参数 (距离, 扩圈, 罩体, 补洞), 没记全就是 None"""
    distance = target.get(BAKE_DISTANCE_PROPERTY)
    grow = target.get(BAKE_GROW_PROPERTY)
    cage = target.get(BAKE_CAGE_PROPERTY)
    fill_holes = target.get(BAKE_FILL_HOLES_PROPERTY)
    if isinstance(distance, bool) or not isinstance(distance, int | float):
        return None
    if isinstance(grow, bool) or not isinstance(grow, int):
        return None
    if not isinstance(cage, bool) or not isinstance(fill_holes, bool):
        return None
    return float(distance), int(grow), cage, fill_holes


def set_target_params(
    target: Object, distance: float, grow: int, cage: bool, fill_holes: bool
) -> None:
    """把生成参数记到产物上: 之后复用产物都用这组参数, 想改就删掉产物"""
    target[BAKE_DISTANCE_PROPERTY] = distance
    target[BAKE_GROW_PROPERTY] = int(grow)
    target[BAKE_CAGE_PROPERTY] = bool(cage)
    target[BAKE_FILL_HOLES_PROPERTY] = bool(fill_holes)


def get_distance_property():
    """距离阈值输入框(`auto_shrinkwrap_bake.py` 用)"""
    return bpy.props.StringProperty(
        name="距离阈值(mm)",
        description="bodytight 面中心到源网格表面的最大距离; 只对新建产物生效",
        default=f"{DEFAULT_DISTANCE_MM:g}",
    )


def get_cage_property():
    """罩体开关"""
    return bpy.props.BoolProperty(
        name="生成罩体(cage)",
        description="沿法线外扩生成罩体; 只对新建产物生效",
        default=False,
    )


def get_fill_holes_property():
    """补网格内部空洞开关"""
    return bpy.props.BoolProperty(
        name="补网格内部空洞",
        description="把源网格围住、且整块离源网格都不超过 100mm 的内部空洞一起补上"
        "(如内裤裆部), 避免产物缺面与 UV 重叠; 只对新建产物生效",
        default=DEFAULT_FILL_HOLES,
    )


def parse_distance(text: str) -> float:
    """解析距离阈值(mm), 返回米"""
    try:
        value = float(text)
    except ValueError:
        raise ObjectError([], f"距离阈值必须是数字, 现在是 {text!r}") from None
    if value <= 0:
        raise ObjectError([], f"距离阈值要大于 0, 现在是 {value:g}mm")
    return value / 1000


def format_distance(distance: float) -> str:
    """米 -> 给用户看的 mm"""
    return f"{distance * 1000:g}mm"


def find_interior_holes(
    bodytight: Object,
    face_indices: Iterable[int],
    src_objs: Sequence[Object],
    max_gap: float = MAX_PROJECTION_GAP,
) -> np.ndarray:
    """被选中的面完全围住、且整块离源网格都不超过 max_gap 的内部空洞面

    源网格绕身体一圈时(如内裤裆部), 被围住的那些 bodytight 面可能比阈值远,
    只按距离挑就会在产物中间留个洞: 贴图缺一块, 展开 UV 也会在凹陷处折叠重叠。
    这类空洞整块离源网格都不远; 腿 / 躯干那种外部区域总有很远的面, 据此区分。
    与 bodytight 自身边界(脖子开口)相连的空洞不补, 否会把产物补过网格边界。
    """
    mesh = bodytight.data
    selected = np.zeros(len(mesh.polygons), dtype=bool)
    selected[[int(index) for index in face_indices]] = True
    if selected.all() or not selected.any():
        return np.array([], dtype=int)

    edge_face_count: dict[tuple[int, int], int] = {}
    for polygon in mesh.polygons:
        for key in polygon.edge_keys:
            edge_face_count[key] = edge_face_count.get(key, 0) + 1
    boundary_keys = {key for key, count in edge_face_count.items() if count == 1}

    holes = ~selected
    touches_boundary = np.zeros(len(mesh.polygons), dtype=bool)
    edge_holes: dict[tuple[int, int], list[int]] = {}
    for polygon in mesh.polygons:
        if selected[polygon.index]:
            continue
        for key in polygon.edge_keys:
            if key in boundary_keys:
                touches_boundary[polygon.index] = True
            edge_holes.setdefault(key, []).append(polygon.index)

    # 未选中的面按共享边并成连通块
    parent = np.arange(len(mesh.polygons))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return int(index)

    for faces in edge_holes.values():
        root = find(faces[0])
        for other in faces[1:]:
            other_root = find(other)
            if other_root != root:
                parent[other_root] = root

    components: dict[int, list[int]] = {}
    for polygon in mesh.polygons:
        if holes[polygon.index]:
            components.setdefault(find(polygon.index), []).append(polygon.index)

    centers = get_world_face_centers_arr(bodytight)
    bvhs = [build_bvh_from_object(src_obj) for src_obj in src_objs]
    filled: list[int] = []
    for faces in components.values():
        if any(touches_boundary[index] for index in faces):
            continue
        # 整块都得在 max_gap 内: 只要有一面超出就不算是被源网格罩住的洞
        if all(
            max(bvh.find_nearest(centers[index])[3] for bvh in bvhs) <= max_gap
            for index in faces
        ):
            filled.extend(faces)
    return np.array(sorted(filled), dtype=int)


def get_bake_sources() -> list[Object]:
    """选中的源网格(排除 bodytight 与烘焙产物)"""
    return [
        obj
        for obj in selected_meshes()
        if obj.name != BODYTIGHT_NAME and BAKE_SOURCE_PROPERTY not in obj
    ]


def need_bake_params(src_objs: Sequence[Object]) -> bool:
    """这些源网格里还有产物没记生成参数时, 才需要弹窗问一次"""
    for src_obj in src_objs:
        target = find_existing_target(src_obj)
        if target is None or get_target_params(target) is None:
            return True
    return False


def find_existing_target(src_obj: Object) -> Object | None:
    """现有产物(不生成): 先按属性找(改名也不丢), 再兼容只按名字记录的旧产物"""
    target = find_bake_target(src_obj)
    if target is None:
        target = get_obj(f"{src_obj.name}_target")
    return target


def get_or_generate_target(
    src_obj: Object,
    regenerate: bool = False,
    distance: float = DEFAULT_DISTANCE,
    grow: int = DEFAULT_GROW,
    unwrap: bool = True,
    cage: bool = False,
    cage_distance: float = DEFAULT_CAGE_DISTANCE,
    fill_holes: bool = DEFAULT_FILL_HOLES,
) -> tuple[Object, Object | None]:
    """已有该源物体的烘焙产物且源网格没改过时复用(保留手动微调), 否则重建"""
    if not regenerate:
        existing = find_existing_target(src_obj)
        if existing is not None:
            # 产物记过生成参数就以产物为准(想改参数就删掉产物)
            stored = get_target_params(existing)
            if stored is not None:
                distance, grow, cage, fill_holes = stored
            signature = get_source_signature(src_obj, distance, grow, cage, fill_holes)
            if existing.get(BAKE_SOURCE_HASH_PROPERTY) == signature:
                bind_bake_source(existing, src_obj)
                return existing, get_obj(f"{existing.name}_cage")
            # 源网格顶点或缩裹参数改过(或旧产物没指纹), 覆盖面与 UV 都对不上, 重建
            remove_bake_target(existing)
    return generate_target(
        src_obj, distance, grow, unwrap, cage, cage_distance, fill_holes
    )
