from hitori_addon.bg_export import (
    is_child_export,
    run_addon_script_in_background,
    run_child_scripts,
)

# 无头子进程里才跑导出流程, 主进程只保存工程再启动子进程, 当前工程状态不会被导出改动
if is_child_export():
    run_child_scripts("legalize_texture_names.py", "acc_export.py", "fbx_to_u3d.py")
else:
    run_addon_script_in_background(__file__)
