import bpy
from bpy.types import Image, Material, Node, Nodes, NodeSocket, Object

from hitori_addon.error import ObjectError


def get_base_color_image(material: Material) -> Image | None:
    if not material or not material.use_nodes:
        return None

    bsdf_node = get_bsdf_node(material)
    if not bsdf_node:
        return None

    for input_link in bsdf_node.inputs:
        if input_link.name == "Base Color":
            if input_link.is_linked:
                return input_link.links[0].from_node.image
            else:
                return None
    return None


def has_link_to_node_type(node: Node, from_node_type: str, to_node_type: str) -> bool:
    return any(
        link.to_node.type == to_node_type for link in node.outputs[from_node_type].links
    )


def get_bsdf_node(material: Material) -> Node | None:
    if not material or not material.use_nodes:
        return None

    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node

    return None


def arrange_nodes_layout(nodes: Nodes, spacing: int = 300, x: int = 0, y: int = 0):
    """把节点排成一行 (输出节点在最右), 同位置有多个节点时向下错开, 避免视觉重合"""
    used_locations: set[tuple[int, int]] = set()
    for node in nodes:
        if node.type == "OUTPUT_MATERIAL":
            location = spacing, y
        else:
            location = x, y
            x -= spacing

        while location in used_locations:
            location = location[0], location[1] - spacing
        used_locations.add(location)
        node.location = location


def find_upstream_texture_node(socket: NodeSocket, max_depth: int = 2) -> Node | None:
    """沿连线往上游找带图的贴图节点 (最多 max_depth 层, 中间可隔着 Normal Map / Math 等)"""
    sockets = [socket]
    for _ in range(max_depth):
        next_sockets = []
        for item in sockets:
            for link in item.links:
                node = link.from_node
                if node.type == "TEX_IMAGE" and node.image:
                    return node
                next_sockets.extend(node.inputs)
        sockets = next_sockets
    return None


def get_input_texture_node(material: Material, input_name: str) -> Node | None:
    """取 BSDF 某个输入口上游的贴图节点"""
    bsdf_node = get_bsdf_node(material)
    if not bsdf_node:
        return None
    return find_upstream_texture_node(bsdf_node.inputs[input_name])


def get_input_image(material: Material, input_name: str) -> Image | None:
    """取 BSDF 某个输入口上游的贴图"""
    texture_node = get_input_texture_node(material, input_name)
    return texture_node.image if texture_node else None


def get_normal_strength(material: Material) -> float:
    """取接到 BSDF Normal 的法线贴图强度 (没有就 1.0)"""
    bsdf_node = get_bsdf_node(material)
    if bsdf_node:
        for link in bsdf_node.inputs["Normal"].links:
            node = link.from_node
            if node.type == "NORMAL_MAP":
                return node.inputs["Strength"].default_value
    return 1.0


def set_simple_material(
    material: Material,
    image: Image | None = None,
    keep_alpha: bool = True,
    keep_normal: bool = True,
) -> Node | None:
    """把材质重置成 贴图 -> Principled BSDF -> 材质输出

    image 为 None 时沿用原来的基础色贴图; 返回新建的基础色贴图节点 (没有基础色贴图则不建, 返回 None)。
    keep_alpha / keep_normal 决定是否沿用原来接在 Alpha / Normal 上的贴图 (以及法线强度);
    只要颜色的流程 (如烘焙) 可以传 False, 避免节点树里留着用不到的引用。
    其余节点与连线全部丢弃, 被丢弃且没人用的贴图数据块会一并删掉。
    """
    material.use_nodes = True
    node_tree = material.node_tree
    nodes = node_tree.nodes

    base_image = image if image is not None else get_source_image(material)
    # 必须在清节点前把要沿用的贴图取出来, 清了之后旧节点上的 image 就不可靠了
    alpha_image = get_input_image(material, "Alpha") if keep_alpha else None
    normal_image = get_input_image(material, "Normal") if keep_normal else None
    normal_strength = get_normal_strength(material)

    # 先记下旧贴图: 清节点后它们会变成孤儿数据块, 名字还占着, 同名新贴图会被加 .001
    old_image_names = {
        node.image.name for node in nodes if node.type == "TEX_IMAGE" and node.image
    }
    nodes.clear()

    bsdf_node = nodes.new("ShaderNodeBsdfPrincipled")
    output_node = nodes.new("ShaderNodeOutputMaterial")
    node_tree.links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])

    texture_node = None
    if base_image is not None:
        texture_node = nodes.new("ShaderNodeTexImage")
        texture_node.image = base_image
        node_tree.links.new(
            texture_node.outputs["Color"], bsdf_node.inputs["Base Color"]
        )

    alpha_node = None
    if alpha_image is not None:
        if alpha_image == base_image and texture_node is not None:
            alpha_output = texture_node.outputs["Alpha"]
        else:
            alpha_node = nodes.new("ShaderNodeTexImage")
            alpha_node.image = alpha_image
            alpha_output = alpha_node.outputs["Alpha"]
        node_tree.links.new(alpha_output, bsdf_node.inputs["Alpha"])

    normal_texture_node = None
    normal_map_node = None
    if normal_image is not None:
        normal_texture_node = nodes.new("ShaderNodeTexImage")
        normal_texture_node.image = normal_image
        normal_map_node = nodes.new("ShaderNodeNormalMap")
        normal_map_node.inputs["Strength"].default_value = normal_strength
        node_tree.links.new(
            normal_texture_node.outputs["Color"], normal_map_node.inputs["Color"]
        )
        node_tree.links.new(normal_map_node.outputs["Normal"], bsdf_node.inputs["Normal"])

    arrange_nodes_layout(nodes)
    # 额外的 alpha / 法线链错开摆放, 否则连线会横穿基础色贴图
    if alpha_node is not None:
        alpha_node.location = (-300, -300)
    if normal_map_node is not None:
        normal_texture_node.location = (-900, 300)
        normal_map_node.location = (-600, 300)

    # 新节点树建好后再删孤儿, 否则沿用的贴图也会被当成没用到
    for name in old_image_names:
        old_image = bpy.data.images.get(name)
        if old_image is None or old_image == image:
            continue
        if old_image.users == 0 and not old_image.use_fake_user:
            bpy.data.images.remove(old_image)

    return texture_node


def get_texture_node(material: Material) -> Node | None:
    """取材质里连到基础色的贴图节点"""
    if not material or not material.use_nodes:
        return None

    bsdf_node = get_bsdf_node(material)
    if not bsdf_node:
        return None

    base_color_input = bsdf_node.inputs["Base Color"]
    if not base_color_input.is_linked:
        return None

    node = base_color_input.links[0].from_node
    return node if node.type == "TEX_IMAGE" else None


def create_texture_node(material: Material, bsdf_node: Node) -> Node:
    """材质里没有贴图节点时新建一个, 连到基础色"""
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.location = (bsdf_node.location[0] - 340, bsdf_node.location[1])
    material.node_tree.links.new(node.outputs["Color"], bsdf_node.inputs["Base Color"])
    return node


def get_texture_material_and_node(
    obj: Object, label: str
) -> tuple[Material, Node]:
    """取物体上带贴图节点的材质; 贴图节点丢了就新建一个"""
    for slot in obj.material_slots:
        node = get_texture_node(slot.material)
        if node:
            return slot.material, node

    for slot in obj.material_slots:
        bsdf_node = get_bsdf_node(slot.material) if slot.material else None
        if bsdf_node:
            return slot.material, create_texture_node(slot.material, bsdf_node)

    raise ObjectError([obj], f"{label} 上没有可用的材质")


def get_source_image(material: Material) -> Image | None:
    """取材质里当基础色用的贴图, 取不到再退回第一个不是法线的贴图节点"""
    if not material or not material.use_nodes:
        return None

    try:
        image = get_base_color_image(material)
    except AttributeError:
        image = None

    if image:
        return image

    for node in material.node_tree.nodes:
        if (
            node.type == "TEX_IMAGE"
            and node.image
            and not has_link_to_node_type(node, "Color", "NORMAL_MAP")
        ):
            return node.image

    return None


def ensure_alpha_clip(material: Material, texture_node: Node) -> None:
    """贴图带透明通道时, 保证材质用 alpha 裁剪(否则透明处会显示成不透明/黑色)"""
    bsdf_node = get_bsdf_node(material)
    if bsdf_node:
        alpha_input = bsdf_node.inputs["Alpha"]
        if not alpha_input.is_linked:
            material.node_tree.links.new(texture_node.outputs["Alpha"], alpha_input)

    if material.blend_method == "OPAQUE":
        material.blend_method = "CLIP"
        if hasattr(material, "shadow_method"):
            material.shadow_method = "CLIP"
