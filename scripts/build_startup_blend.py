"""从官模模板派生 startup.blend (新建文件的默认场景).

startup.blend 的内容就是"空场景 + 官模模板的界面": 8 个中文工作区 / 场景设置 (EEVEE, 24fps, 1 帧, 毫米,
Standard 色彩, Cycles GPU 烘焙) / 视口设置 (SOLID FLAT, 正交镜头) 全部跟模板一致, 所以直接从模板派生:
删掉模板里的物体 / 集合 / 网格 / 骨架 / 材质 / 文本块, 其它原样保留.

模板只读, 不会被改写; 输出是 install_resources 里入库的那份.

用法 (普通 python, 脚本自己拉起无头 Blender):
    python scripts/build_startup_blend.py
    python scripts/build_startup_blend.py --template <模板路径> --output <输出路径>
"""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).absolute().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from hitori_addon.const import BLENDER_DIR, EXTERNAL_RESOURCES_DIR

# 默认路径: 外部资源里的官模模板 -> 入库的 Blender 配置
DEFAULT_TEMPLATE: Path = EXTERNAL_RESOURCES_DIR / "kk_blend" / "official_template.blend"
DEFAULT_OUTPUT: Path = (
    PROJECT_DIR / "install_resources" / "Blender" / "3.6" / "config" / "startup.blend"
)
BLENDER_EXE: Path = BLENDER_DIR / "blender.exe"

# 要清空的数据块, 顺序有依赖 (先删物体, 否则集合 / 网格还被引用着)
DATABLOCK_NAMES: tuple[str, ...] = (
    "objects",
    "collections",
    "meshes",
    "armatures",
    "materials",
    "texts",
)

# 派生后必须为空的数据块 (漏了会让 startup.blend 白带模板数据)
EMPTY_CHECKS: tuple[str, ...] = ("objects", "collections", "meshes", "armatures", "materials", "texts")

TIMEOUT_SECONDS: int = 600


def _in_blender() -> bool:
    try:
        import bpy  # noqa: F401
    except ImportError:
        return False
    return True


def _parse_args(argv: list[str]) -> tuple[Path, Path]:
    """解析命令行 (--template / --output), 缺省用默认路径"""
    template, output = DEFAULT_TEMPLATE, DEFAULT_OUTPUT
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag not in {"--template", "--output"} or index + 1 >= len(argv):
            raise SystemExit(f"参数有误: {flag}, 用法见脚本开头的说明")
        if flag == "--template":
            template = Path(argv[index + 1])
        else:
            output = Path(argv[index + 1])
        index += 2
    return template, output


def _paths_from_worker_argv() -> tuple[Path, Path]:
    """Blender 内部: 取 "--" 之后的两个位置参数 (模板, 输出)"""
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return Path(args[0]), Path(args[1])


def _build_startup(template: Path, output: Path) -> None:
    """Blender 内: 打开模板, 清空数据块, 另存为 startup.blend"""
    import bpy

    bpy.ops.wm.open_mainfile(filepath=str(template))
    for name in DATABLOCK_NAMES:
        datablocks = getattr(bpy.data, name)
        for datablock in list(datablocks):
            datablocks.remove(datablock, do_unlink=True)

    # 剩下的数据块名数量, 中文名走 ascii() 以免控制台编码问题
    counts = {name: len(getattr(bpy.data, name)) for name in EMPTY_CHECKS}
    workspaces = [ascii(workspace.name) for workspace in bpy.data.workspaces]
    scene = bpy.data.scenes[0]
    print(
        f"[startup] counts={counts} scene={scene.name!a} "
        f"engine={scene.render.engine} fps={scene.render.fps} "
        f"frames={scene.frame_start}-{scene.frame_end} "
        f"units={scene.unit_settings.system}/{scene.unit_settings.length_unit} "
        f"view={scene.view_settings.view_transform} "
        f"cycles={scene.cycles.device}/{scene.cycles.bake_type} "
        f"props={sorted(scene.keys())}",
        flush=True,
    )
    print(f"[startup] workspaces={workspaces}", flush=True)

    leftovers = {name: count for name, count in counts.items() if count}
    if leftovers:
        raise SystemExit(f"[startup] 派生结果不为空: {leftovers}")

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=False)
    print(f"[startup] saved {output}", flush=True)


def _launch(template: Path, output: Path) -> None:
    """普通 python 侧: 用无头 Blender 跑本脚本, 再报告产物"""
    if not template.is_file():
        raise SystemExit(f"缺少模板: {template} (见 docs/external_resources.md)")
    if not BLENDER_EXE.is_file():
        raise SystemExit(f"找不到 blender: {BLENDER_EXE}")

    # --factory-startup: 不带用户的偏好和插件, 派生结果才可复现
    command = [
        str(BLENDER_EXE),
        "-b",
        "--factory-startup",
        "--python",
        str(Path(__file__).absolute()),
        "--",
        str(template),
        str(output),
    ]
    subprocess.run(command, timeout=TIMEOUT_SECONDS, check=True)
    print(f"生成完成: {output} ({output.stat().st_size:,} 字节)")


if __name__ == "__main__":
    if _in_blender():
        _build_startup(*_paths_from_worker_argv())
    else:
        _launch(*_parse_args(sys.argv[1:]))
