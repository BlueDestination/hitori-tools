from collections.abc import Mapping
from types import MappingProxyType

from hitori_addon.menu import message_box
from hitori_addon.mesh import selected_meshes
from hitori_addon.vg import add_mirror_bones_map, merge_vgs

kk_bone_to_vrc_bones_map_left: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "cf_j_head": ("Head", "頭"),
        "cf_j_neck": ("Neck", "首"),
        "cf_j_spine03": ("Chest", "上半身2", "上半身3"),
        "cf_j_spine02": ("Spine", "上半身", "上半身1", "Bip001-Spine2"),
        "cf_j_spine01": (
            "Hips",
            "下半身",
            "Bip001-Spine1",
        ),
        "cf_j_waist01": ("Bip001-Spine",),
        "cf_j_waist02": ("Bip001-Pelvis",),
        "cf_j_thigh00_L": ("UpperLeg_L", "足.L", "足D.L", "Thigh_L"),
        "cf_j_leg01_L": ("LowerLeg_L", "ひざ.L", "ひざD.L", "ひざ补.L"),
        "cf_j_leg03_L": ("Foot_L", "足首.L", "足首D.L"),
        "cf_j_foot_L": ("足先EX.L", "ToeBase_L"),
        "cf_j_toes_L": ("Toe_L", "つま先.L", "つま先D.L"),
        "cf_j_shoulder_L": ("Shoulder_L", "肩.L", "Bip001-L-Clavicle"),
        "cf_j_arm00_L": (
            "UpperArm_L",
            "腕.L",
            "腕捩.L",
            "腕捩1.L",
            "腕捩2.L",
            "腕捩3.L",
            "ひじ.L",
            "Bip001-L-UpperArm",
            "Bone-L-UpperArm-Twist",
            "Bone-L-UpperArm-Twist1",
        ),
        "cf_j_forearm01_L": (
            "LowerArm_L",
            "手捩.L",
            "手捩1.L",
            "手捩2.L",
            "手捩3.L",
            "Bip001-L-Forearm",
            "Bone-L-ForeArm-Twist",
            "Bone-L-ForeArm-Twist1",
        ),
        "cf_j_hand_L": ("Hand_L", "手首.L"),
        "cf_j_bust02_L": ("Breast_L", "胸.L", "胸1.L", "胸下.L", "胸下1.L", "胸上2.L"),
        "cf_j_thumb01_L": ("親指０.L", "親指0.L"),
        "cf_j_thumb02_L": ("親指１.L", "親指1.L"),
        "cf_j_thumb03_L": ("親指２.L", "親指2.L"),
        "cf_j_index01_L": ("人指０.L", "人指0.L"),
        "cf_j_index02_L": ("人指１.L", "人指1.L"),
        "cf_j_index03_L": ("人指２.L", "人指2.L"),
        "cf_j_middle01_L": ("中指０.L", "中指0.L"),
        "cf_j_middle02_L": ("中指１.L", "中指1.L"),
        "cf_j_middle03_L": ("中指２.L", "中指2.L"),
        "cf_j_ring01_L": ("薬指０.L", "薬指0.L"),
        "cf_j_ring02_L": ("薬指１.L", "薬指1.L"),
        "cf_j_ring03_L": ("薬指２.L", "薬指2.L"),
        "cf_j_little01_L": ("小指０.L", "小指0.L"),
        "cf_j_little02_L": ("小指１.L", "小指1.L"),
        "cf_j_little03_L": ("小指２.L", "小指2.L"),
    }
)

kk_bone_to_vrc_bones_map = add_mirror_bones_map(kk_bone_to_vrc_bones_map_left)

TITLE = "合并vrc/mmd权重到kk顶点组"

objs = selected_meshes()

if not objs:
    message_box("请先选中网格", title=TITLE, icon="ERROR")
else:
    lines = ["已完成顶点组合并,原顶点组保留,只展示有合并发生的:"]
    for obj in objs:
        obj_vgs = obj.vertex_groups
        merge_lines: list[str] = []
        for kk_bone, vrc_bones in kk_bone_to_vrc_bones_map.items():
            source_names = [name for name in vrc_bones if obj_vgs.get(name)]
            # 始终覆盖已有 kk 权重; 源顶点组不删
            merge_vgs(obj, vrc_bones, kk_bone)
            if source_names and obj_vgs.get(kk_bone):
                merge_lines.append(f"{kk_bone}: {', '.join(source_names)}")
        if not merge_lines:
            continue
        lines.append(f"--- {obj.name} ---")
        lines.extend(merge_lines)
        lines.append("")

    message_box("\n".join(lines).strip(), title=TITLE)
