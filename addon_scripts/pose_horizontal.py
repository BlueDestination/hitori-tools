"""骨骼姿势水平化: 把选中的姿态骨骼转到水平 (世界前视图的 X 轴)

支持多骨架多骨骼, 但同一棵骨骼树上不能同时选父子 (父级转动会带偏子级, 会报错)。
只改骨骼姿态, 不动网格 / 权重 / 其他数据, 结果一眼可见, 所以成功时不弹窗。
"""

from hitori_addon.pose import level_selected_pose_bones

level_selected_pose_bones()
