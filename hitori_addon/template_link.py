"""与官模模板 official_template.blend 联动的固定名称

模板里改名 / 删数据块, 这里必须同步; 反过来脚本也都按这些名字去找东西.
"""

from pathlib import Path

from hitori_addon.const import EXTERNAL_RESOURCES_DIR

# 官模模板文件
TEMPLATE_BLEND: Path = EXTERNAL_RESOURCES_DIR / "kk_blend" / "official_template.blend"

# 官模骨架物体: 衣服导出 / 动态骨骼 / 对齐都按这个名字找它
ARMATURE_NAME: str = "Armature"
# 紧身衣: 烘焙 / 贴合 / 穿模检查的基准物体
BODYTIGHT_NAME: str = "bodytight"
# 头模 / 眼线 / 瞳孔模板物体
HEAD_NAME: str = "kk_head"
EYELINE_NAME: str = "kk_eyeline"
HITOMI_NAME: str = "kk_hitomi"
# 头模 / 眼线 / 瞳孔所在的集合, 追加时按整组 append
HEAD_COLLECTION_NAME: str = "kk_head_collection"
EYELINE_COLLECTION_NAME: str = "kk_eyeline_collection"
# 追加头模眼线时要 append 的集合 (bake_target_collection 里的参考件不能带进场景)
APPEND_COLLECTION_NAMES: tuple[str, ...] = (
    "kk_bodytight_collection",
    HEAD_COLLECTION_NAME,
    EYELINE_COLLECTION_NAME,
)
# 表情布局脚本要 append 的工作区
EXPRESSION_WORKSPACE_NAME: str = "表情"

# 顶点组标记 (模板里不放, 由脚本按需写在服装网格上), 名字还会随 mod 写进游戏
# skip_transfer_group: 这些顶点不从 bodytight 传递权重
# 缺失或空组 = 整片传; 非空 = 只传补集; 全 1 = 整片不传
SKIP_TRANSFER_GROUP_NAME: str = "skip_transfer_group"
