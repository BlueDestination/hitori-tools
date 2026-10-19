"""骨骼姿势镜像: 把选中骨骼的姿势镜像到命名对应的镜像骨骼

按骨架局部 X=0 平面镜像 (`Upper_arm.R` <-> `Upper_arm.L` / `腕.R` <-> `腕.L` / `_R` <-> `_L` / `左` <-> `右` 等)。
左右骨骼 roll 约定不一致时 (如 mmd 左右相差 180 度) 会自动补偿扭转, 否则镜像后的扭转会翻转。
支持多骨架多骨骼, 父子可以同时选中; 找不到镜像骨骼的骨骼会弹窗列出, 正常镜像完成不弹窗。
"""

from hitori_addon.menu import format_name_list, message_box
from hitori_addon.pose import mirror_selected_pose

TITLE = "骨骼姿势镜像"

count, missing = mirror_selected_pose()
if missing:
    message_box(
        f"镜像 {count} 根骨骼\n找不到镜像骨骼 (这些没镜像):\n"
        f"{format_name_list(missing, indent='    ')}",
        title=TITLE,
    )
