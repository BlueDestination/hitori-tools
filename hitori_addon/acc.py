from dataclasses import dataclass


@dataclass(frozen=True)
class KkAcc:
    """KK 饰品挂点 (游戏里的 a_n_* 节点)

    - pos: 挂点在世界原点的位置, Blender 坐标
    - rot: 挂点旋转, Unity 四元数 (x, y, z, w)
    - parent: 写进饰品 csv Parent 列的挂点名
    """

    name: str
    pos: tuple[float, float, float]
    rot: tuple[float, float, float, float]
    parent: str
