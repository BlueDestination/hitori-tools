"""mod 缩略图: 让用户用方形线框对齐范围, 沿 +Y 正交投影渲染一张 256x256 的图

对齐期间方框只画线框且不参与渲染; 回车确认后截取, Esc 取消。
渲染设置与实物模式的 平展(flat) 一致: Workbench + FLAT 光照 + 贴图颜色。
"""

import math
import tempfile
from collections.abc import Callable
from pathlib import Path

import blf
import bpy
import gpu
from bpy.types import Context, Event, Object, Operator
from gpu_extras.batch import batch_for_shader
from mathutils import Euler, Vector

from hitori_addon.menu import message_box
from hitori_addon.obj import ObjectState, create_obj, select_obj, set_mode
from hitori_addon.template import THUMB_PNG_BASENAME, THUMB_SIZE, ZIPMOD_TEMPLATE_DIR

FRAME_OBJ_NAME: str = "mod_thumb_frame"
CAMERA_OBJ_NAME: str = "mod_thumb_camera"
# 方框默认边长(米): 默认框头部特写, 用户自己移动/缩放
FRAME_SIZE: float = 0.375
# 默认方框顶端离模型最高点的距离(米)
FRAME_TOP_GAP: float = 0.01
# 方框放在模型前方多远
FRAME_MARGIN: float = 0.1
# 切换正交视图时方框占画面的比例, 留点周围环境做参考
VIEW_PADDING: float = 1.6
# 相机放在几何体前方多远; 正交相机的位置只影响裁剪, 不影响构图
CAMERA_DISTANCE: float = 1.0
TEMP_PNG_NAME: str = "hitori_mod_thumb.png"
STATUS_TEXT: str = "调整方框范围后按回车截取缩略图, 按 Esc 取消"

# 框选期间盖在 3D 视图顶部的提示(状态栏的字太小, 容易看不到)
HINT_LINES: tuple[str, ...] = (
    "调好方框范围后按 回车 截取 mod 缩略图",
    "按 Esc 取消(不会生成 zipmod)",
)
HINT_FONT_ID: int = 0
HINT_FONT_SIZE: int = 18
HINT_LINE_SPACING: int = 8
HINT_PADDING: int = 12
HINT_MARGIN_TOP: int = 60
HINT_BACKGROUND_COLOR: tuple[float, float, float, float] = (0.05, 0.05, 0.05, 0.8)
HINT_TEXT_COLOR: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)

_shader_2d = None
_draw_handler = None


def get_frame_obj() -> Object | None:
    return bpy.data.objects.get(FRAME_OBJ_NAME)


def get_thumb_img_path() -> Path:
    """模板 img 目录里的缩略图; 有它 create_zipmod 就直接用"""
    return ZIPMOD_TEMPLATE_DIR / "img" / THUMB_PNG_BASENAME


def get_visible_bounds() -> tuple[Vector, Vector] | None:
    """当前可见网格的世界坐标包围盒 (min, max), 没有可见网格时返回 None"""
    # 用户刚刚增删/移动过物体, 先刷新一遍再取包围盒
    bpy.context.view_layer.update()
    min_corner = max_corner = None
    for obj in bpy.context.view_layer.objects:
        if obj.type != "MESH" or obj.name == FRAME_OBJ_NAME or not obj.visible_get():
            continue
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            if min_corner is None:
                min_corner, max_corner = world_corner.copy(), world_corner.copy()
            else:
                min_corner = Vector(map(min, min_corner, world_corner))
                max_corner = Vector(map(max, max_corner, world_corner))
    if min_corner is None:
        return None
    return min_corner, max_corner


def create_frame() -> Object:
    """在模型正前方建一个方形线框平面并选中, 用作框选标尺

    顶点按方框自身中心对称, 对象的缩放/旋转保持为单位值, 只用 location 定位。
    """
    frame = create_obj(FRAME_OBJ_NAME, "MESH")
    half = FRAME_SIZE / 2
    frame.data.from_pydata(
        [(-half, 0, -half), (half, 0, -half), (half, 0, half), (-half, 0, half)],
        [(0, 1), (1, 2), (2, 3), (3, 0)],
        [(0, 1, 2, 3)],
    )
    frame.data.update()

    bounds = get_visible_bounds()
    if bounds is None:
        frame.location = (0, 0, 0)
    else:
        min_corner, max_corner = bounds
        # 默认画头部: 水平居中, 顶端贴着模型最高点往下留一点空隙
        frame.location = (
            (min_corner.x + max_corner.x) / 2,
            min_corner.y - FRAME_MARGIN,
            max_corner.z - FRAME_TOP_GAP - half,
        )

    frame.display_type = "WIRE"
    frame.show_in_front = True
    # 只当标尺, 不进渲染
    frame.hide_render = True
    return frame


def get_frame_corners(frame: Object) -> list[Vector]:
    """方框顶点的世界坐标; 直接用顶点算, 不依赖 dimensions / bound_box"""
    # 刚设过 location 或用户刚编辑过顶点时 matrix_world 还没刷新
    bpy.context.view_layer.update()
    return [frame.matrix_world @ vertex.co for vertex in frame.data.vertices]


def get_frame_size(frame: Object) -> float:
    """方框在世界坐标里的边长(x / z 取大的那个)"""
    corners = get_frame_corners(frame)
    return max(
        max(corner.x for corner in corners) - min(corner.x for corner in corners),
        max(corner.z for corner in corners) - min(corner.z for corner in corners),
        0.001,
    )


def get_frame_center(frame: Object) -> Vector:
    """方框的世界坐标中心(原点不在中心也能用)"""
    corners = get_frame_corners(frame)
    return Vector(
        [
            (min(corner[i] for corner in corners) + max(corner[i] for corner in corners))
            / 2
            for i in range(3)
        ]
    )


def delete_frame(frame: Object) -> None:
    mesh = frame.data
    bpy.data.objects.remove(frame, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def find_view3d_override() -> dict | None:
    """当前窗口里的第一个 3D 视图, 用于取视图数据"""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is not None:
                return {
                    "window": window,
                    "screen": window.screen,
                    "area": area,
                    "region": region,
                }
    return None


def enter_front_ortho_view() -> bool:
    """把 3D 视图切到前正交视图, 并对准方框"""
    override = find_view3d_override()
    if override is None:
        return False

    # 直接改视图数据, 不用 view3d 系列操作符(后台模式没有它们)
    region_3d = override["area"].spaces.active.region_3d
    region_3d.view_perspective = "ORTHO"
    # 前视图 = 绕 X 轴转 90 度, 沿 +Y 看
    region_3d.view_rotation = Euler((math.pi / 2, 0, 0)).to_quaternion()

    frame = get_frame_obj()
    if frame is not None:
        region_3d.view_location = get_frame_center(frame)
        # 正交模式下 view_distance 就是缩放
        region_3d.view_distance = get_frame_size(frame) * VIEW_PADDING
        return True

    bounds = get_visible_bounds()
    if bounds is not None:
        min_corner, max_corner = bounds
        region_3d.view_location = (min_corner + max_corner) / 2
        region_3d.view_distance = max(
            max_corner.x - min_corner.x, max_corner.z - min_corner.z, 0.001
        )
    return True


def get_2d_shader():
    """画纯色矩形用的 2D shader(不同版本名字不一样)"""
    global _shader_2d
    if _shader_2d is None:
        for shader_name in ("2D_UNIFORM_COLOR", "UNIFORM_COLOR"):
            try:
                _shader_2d = gpu.shader.from_builtin(shader_name)
                break
            except ValueError:
                continue
    return _shader_2d


def draw_hint() -> None:
    """在 3D 视图顶部画一块提示, 截图期间一直显示"""
    region = bpy.context.region
    if region is None:
        return

    blf.size(HINT_FONT_ID, HINT_FONT_SIZE)
    line_widths = [blf.dimensions(HINT_FONT_ID, line)[0] for line in HINT_LINES]
    line_height = HINT_FONT_SIZE + HINT_LINE_SPACING
    block_width = max(line_widths) + HINT_PADDING * 2
    block_height = (
        line_height * len(HINT_LINES) - HINT_LINE_SPACING + HINT_PADDING * 2
    )
    left = (region.width - block_width) / 2
    top = region.height - HINT_MARGIN_TOP
    bottom = top - block_height

    shader = get_2d_shader()
    if shader is not None:
        gpu.state.blend_set("ALPHA")
        vertices = (
            (left, bottom),
            (left + block_width, bottom),
            (left + block_width, top),
            (left, top),
        )
        batch = batch_for_shader(
            shader, "TRIS", {"pos": vertices}, indices=((0, 1, 2), (0, 2, 3))
        )
        shader.bind()
        shader.uniform_float("color", HINT_BACKGROUND_COLOR)
        batch.draw(shader)
        gpu.state.blend_set("NONE")

    blf.color(HINT_FONT_ID, *HINT_TEXT_COLOR)
    text_baseline = top - HINT_PADDING - HINT_FONT_SIZE
    for line, line_width in zip(HINT_LINES, line_widths):
        blf.position(HINT_FONT_ID, (region.width - line_width) / 2, text_baseline, 0)
        blf.draw(HINT_FONT_ID, line)
        text_baseline -= line_height


def start_hint() -> None:
    global _draw_handler
    stop_hint()
    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_hint, (), "WINDOW", "POST_PIXEL"
    )


def stop_hint() -> None:
    global _draw_handler
    if _draw_handler is None:
        return
    try:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, "WINDOW")
    except (ValueError, RuntimeError):
        pass
    _draw_handler = None


def get_render_settings(scene) -> tuple:
    """备份截图会改到的渲染设置"""
    render = scene.render
    shading = scene.display.shading
    return (
        render.engine,
        render.filepath,
        render.resolution_x,
        render.resolution_y,
        render.resolution_percentage,
        render.film_transparent,
        render.image_settings.file_format,
        render.image_settings.color_mode,
        shading.light,
        shading.color_type,
        scene.camera,
    )


def set_render_settings(backup: tuple) -> None:
    (
        engine,
        filepath,
        resolution_x,
        resolution_y,
        resolution_percentage,
        film_transparent,
        file_format,
        color_mode,
        light,
        color_type,
        camera,
    ) = backup
    scene = bpy.context.scene
    render = scene.render
    shading = scene.display.shading

    render.engine = engine
    render.filepath = filepath
    render.resolution_x = resolution_x
    render.resolution_y = resolution_y
    render.resolution_percentage = resolution_percentage
    render.film_transparent = film_transparent
    render.image_settings.file_format = file_format
    render.image_settings.color_mode = color_mode
    shading.light = light
    shading.color_type = color_type
    scene.camera = camera


def render_thumb(frame: Object) -> bytes:
    """沿 +Y 正交投影渲染方框范围内的画面, 返回 png 字节"""
    scene = bpy.context.scene
    render = scene.render
    shading = scene.display.shading
    backup = get_render_settings(scene)
    # 会改隐藏状态, 渲染完还原
    obj_state = ObjectState()

    camera_data = bpy.data.cameras.new(CAMERA_OBJ_NAME)
    camera = bpy.data.objects.new(CAMERA_OBJ_NAME, camera_data)
    scene.collection.objects.link(camera)
    temp_png_path = Path(tempfile.gettempdir()) / TEMP_PNG_NAME

    try:
        # 与实物模式的 平展(flat) 一致
        render.engine = "BLENDER_WORKBENCH"
        shading.light = "FLAT"
        shading.color_type = "TEXTURE"
        render.film_transparent = True
        render.resolution_x = THUMB_SIZE
        render.resolution_y = THUMB_SIZE
        render.resolution_percentage = 100
        render.image_settings.file_format = "PNG"
        render.image_settings.color_mode = "RGBA"
        render.filepath = str(temp_png_path)

        # 和视口里看到的一致: 只渲染当前可见的物体
        for obj in scene.objects:
            obj.hide_render = not obj.visible_get()
        frame.hide_render = True

        # 相机要放在所有几何体前方, 否则背后的部分会被正交相机裁掉
        center = get_frame_center(frame)
        bounds = get_visible_bounds()
        front_y = bounds[0].y if bounds else center.y
        camera_data.type = "ORTHO"
        # 方框边长就是裁剪范围, 输出是正方形所以取长边
        camera_data.ortho_scale = get_frame_size(frame)
        # 沿 +Y 看, 即正视图
        camera.rotation_euler = (math.pi / 2, 0, 0)
        camera.location = (
            center.x,
            min(front_y, center.y) - CAMERA_DISTANCE,
            center.z,
        )
        camera.hide_render = True
        scene.camera = camera

        bpy.ops.render.render(write_still=True)
        return temp_png_path.read_bytes()
    finally:
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.cameras.remove(camera_data)
        temp_png_path.unlink(missing_ok=True)
        obj_state.restore()
        set_render_settings(backup)


def write_thumb_png(png: bytes) -> Path:
    thumb_path = get_thumb_img_path()
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_path.write_bytes(png)
    return thumb_path


def register_operator(operator_class: type[Operator]) -> None:
    """重复运行脚本时先注销上次注册的同类操作符"""
    module_name, operator_name = operator_class.bl_idname.split(".", 1)
    old_class = getattr(bpy.types, f"{module_name.upper()}_OT_{operator_name}", None)
    if old_class is not None:
        bpy.utils.unregister_class(old_class)
    bpy.utils.register_class(operator_class)


# 回车确认后要接着跑的函数(比如继续初始化 mod)
_PENDING_CONFIRM: Callable[[], None] | None = None


def finish_crop(confirmed: bool) -> set[str]:
    """结束框选: 确认就截图并接着跑后续函数, 取消就删掉方框什么都不做"""
    global _PENDING_CONFIRM

    stop_hint()
    if bpy.context.workspace:
        bpy.context.workspace.status_text_set(None)

    frame = get_frame_obj()
    thumb_path = None
    error = None
    if confirmed and frame is not None:
        try:
            thumb_path = write_thumb_png(render_thumb(frame))
        except Exception as exception:  # noqa: BLE001  渲染失败要让用户看到原因
            error = exception

    if frame is not None:
        delete_frame(frame)

    confirm_func, _PENDING_CONFIRM = _PENDING_CONFIRM, None

    if error is not None:
        message_box(f"截取缩略图失败: {error}", icon="ERROR")
    elif confirmed and thumb_path is not None:
        message_box(f"mod缩略图已截取:\n{thumb_path}", title="框选截取")

    if confirmed and confirm_func is not None:
        try:
            confirm_func()
        except Exception as exception:  # noqa: BLE001  modal 里抛异常只会打印到控制台
            message_box(f"初始化 mod 失败: {exception}", icon="ERROR")

    return {"FINISHED"} if confirmed else {"CANCELLED"}


class ThumbCropConfirm(Operator):
    """框选 mod 缩略图: 回车截取, Esc 取消"""

    bl_idname: str = "wm.thumb_crop_confirm"
    bl_label: str = "截取mod缩略图"

    def invoke(self, context: Context, _event: Event) -> set[str]:
        context.window_manager.modal_handler_add(self)
        start_hint()
        if context.workspace:
            context.workspace.status_text_set(STATUS_TEXT)
        return {"RUNNING_MODAL"}

    def modal(self, _context: Context, event: Event) -> set[str]:
        if event.value != "PRESS":
            return {"PASS_THROUGH"}
        if event.type in {"RET", "NUMPAD_ENTER"}:
            return finish_crop(confirmed=True)
        if event.type in {"ESC", "RIGHTMOUSE"}:
            return finish_crop(confirmed=False)
        return {"PASS_THROUGH"}


def confirm_thumb_crop(confirm_func: Callable[[], None]) -> None:
    """建方框并切到前正交视图, 用户回车确认后截图并接着跑 confirm_func"""
    global _PENDING_CONFIRM

    set_mode("OBJECT")

    old_frame = get_frame_obj()
    if old_frame is not None:
        delete_frame(old_frame)

    frame = create_frame()
    select_obj(frame)
    if not enter_front_ortho_view():
        message_box("没有找到 3D 视图, 无法自动切换正交视图", icon="ERROR")

    _PENDING_CONFIRM = confirm_func
    register_operator(ThumbCropConfirm)
    bpy.ops.wm.thumb_crop_confirm("INVOKE_DEFAULT")
