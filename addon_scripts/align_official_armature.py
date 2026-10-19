"""对齐官方骨架(位置 + 缩放 + 大臂水平化)

把选中骨架(不选中时用场景里全部骨架)对齐到官方骨架 `Armature`:
1. 脚部起点对齐官方脚部的 Y / Z;
2. 以脚点为锚点整体缩放, 让右大臂高度对齐官方;
3. 左右大臂水平化(两端世界 Z 相同)。
前两步只改骨架的位置与缩放属性(骨骼与旋转都不动), 第三步只改大臂的姿态数据。
X 方向不处理(两侧骨骼宽度本来就有差异), 手部宽度要在上视图自己对齐。
"""

from hitori_addon.align import align_armatures
from hitori_addon.arm import selected_arms
from hitori_addon.menu import message_box
from hitori_addon.obj import get_objs

REMINDER = "提醒: X 方向未对齐(两侧骨骼宽度本就不同), 请自己在上视图对齐手部"


def main():
    arms = selected_arms() or get_objs("ARMATURE")
    report = align_armatures(arms)
    message_box(f"{report}\n\n{REMINDER}", title="对齐官方骨架")


if __name__ == "__main__":
    main()
