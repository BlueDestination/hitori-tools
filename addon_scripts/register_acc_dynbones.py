"""把饰品的动骨链起点写进 u3d 并热重载 (无头子进程里跑, 当前工程不会被导出改动), 主进程等写完后弹窗列出写了哪些"""

from collections.abc import Mapping
from types import MappingProxyType

from hitori_addon.bg_export import is_child_export, run_addon_script_in_background
from hitori_addon.check import require_acc_meshes
from hitori_addon.const import ABDATA_DIR, ACC_TYPES
from hitori_addon.dynbone import find_acc_dynbone_bone_names
from hitori_addon.hotreload import update_and_refresh_mod
from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.obj import get_obj
from hitori_addon.path import get_blend_file_stem
from hitori_addon.run import run_addon_script
from hitori_addon.u3d import (
    format_root_bones_report,
    read_u3d_root_bones,
    register_u3d_dynbones,
)

TITLE = "注册饰品动骨接骨"

chara_name = get_blend_file_stem()
u3d_path = ABDATA_DIR / f"{chara_name}.unity3d"

if is_child_export():
    accs = selected_meshes()
    # 如果有非饰品网格则报错
    require_acc_meshes(accs)

    # 子进程读到的工程里可能残留上次导出留下的旧骨架(骨骼可能已经和当前骨架不一致),
    # 所以统一重新导出一次再找动骨 (导出会应用修改器 / 移动物体 / 复制骨架, 只能留在子进程里)
    run_addon_script("acc_export.py")

    acc_type_and_acc_arm_names: Mapping[str, str] = MappingProxyType(
        {acc_type: f"arm_{acc_type}" for acc_type in ACC_TYPES}
    )

    acc_arm_dynbones: dict[str, list[str]] = {}

    for acc_type, acc_arm_name in acc_type_and_acc_arm_names.items():
        acc_arm = get_obj(acc_arm_name)
        if not acc_arm:
            continue
        # 饰品没有接骨, 动骨写的是链起点本身 (官方饰品 mod 的 m_Root 就是链起点, 它的父骨不注册);
        # 导出时多根根骨已经统一成一根, 所以从骨架根骨往下找第一根非人形骨
        dynbone_names = find_acc_dynbone_bone_names(acc_arm)
        if dynbone_names:
            acc_arm_dynbones[acc_type] = dynbone_names
        else:
            print(f"{acc_type} 的饰品骨架里没有动骨 (只有身体骨), 跳过")

    reports = register_u3d_dynbones(u3d_path, acc_arm_dynbones)
    if any(not report.is_empty for report in reports.values()):
        update_and_refresh_mod(u3d_path)
else:
    # 主进程只保存工程再启动子进程, 当前工程状态不会被导出改动
    run_addon_script_in_background(__file__)
    # 写入发生在子进程里, 弹窗只能在主进程, 所以从 u3d 把刚写进去的内容读回来
    reports = read_u3d_root_bones(u3d_path, ACC_TYPES)
    for acc_type, report in reports.items():
        if not report.is_empty:
            # 导出时骨架按网格建 (`arm_<网格名>`) 且只留该网格有权重的骨, 所以来源就是这个网格
            report.mesh_names = {acc_type}
    text, is_written = format_root_bones_report("饰品", u3d_path.name, reports)
    message_box(text, title=TITLE, icon="INFO" if is_written else "ERROR")
