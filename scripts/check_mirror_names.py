"""检查骨架的左右骨骼命名能否被姿态镜像识别 (一次性统计, 不进菜单)

用法 (读取 .blend 里的全部骨架, 只统计不改数据):
    <Blender>/blender.exe -b <模型.blend> --python scripts/check_mirror_names.py
    <Blender>/blender.exe -b <模型.blend> --python scripts/check_mirror_names.py -- <骨架名关键词>

每个骨架输出:
- 命名命中率 = 找到镜像伙伴的骨骼 / 名字里带左右标记的骨骼;
- 漏配 (名字带标记但找不到伙伴, 会直接导致镜像漏骨), 并按 X=0 镜像位置猜出伙伴应该叫什么;
- 单向配对 (A 能找到 B, B 找不到 A, 说明标记优先级或名字不对称);
- 命名缺口 (名字看着像左右骨, 但左右标记不在 `MIRROR_MARKERS` 里, 加标记就能覆盖)。

加标记的顺序要求见 `hitori_addon/pose.py` 的 `MIRROR_MARKERS` (顺序即优先级: 短后缀 -> 英文单词 -> 中文)。
"""

import re
import sys
from pathlib import Path

import bpy

PROJECT_DIR = Path(__file__).absolute().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from hitori_addon.dynbone import get_bone_name_tokens
from hitori_addon.pose import MIRROR_MARKERS, find_mirror_bone

# 比 MIRROR_MARKERS 更宽的判据: 任意位置出现的独立 l / r 词, 或中文左右
SIDE_TOKENS = frozenset({"l", "r", "left", "right"})
SIDE_CHARS = ("左", "右")
# 按位置猜伙伴的容差 (骨架局部坐标)
POSITION_TOLERANCE = 1e-3
# 每个分类最多列几个名字
MAX_LIST = 12


def find_marker_offset(name: str, marker: str) -> int:
    """marker 作为独立的左右标记出现时的位置, 不是则 -1

    后缀写法 (`_R` / `.L` / ` L`) 要求标记后面不再接字母, 否则 `cf_j_root` 里的 `_r` 也会算左右标记;
    前缀写法 (`L_` / `Left` / `左`) 要求标记前面不再接字母, 否则 `XRibbonLeft` 也会算。
    """
    is_ascii_letter = marker[0].isascii() and marker[0].isalpha()
    suffix_style = not is_ascii_letter
    start = 0
    while True:
        index = name.find(marker, start)
        if index < 0:
            return -1
        start = index + 1
        after = name[index + len(marker) :][:1]
        before = name[index - 1 : index]
        if suffix_style:
            if after.isascii() and after.isalpha():
                continue
        elif before.isascii() and before.isalpha():
            continue
        return index


def has_marker(name: str) -> bool:
    return any(
        find_marker_offset(name, side) >= 0 for pair in MIRROR_MARKERS for side in pair
    )


SIDE_OPPOSITE: dict[str, str] = {
    side: other for pair in MIRROR_MARKERS for side, other in (pair, pair[::-1])
}


def get_side(name: str) -> str:
    """名字里的左右标记 (`_l` / `.R` / `左` ...), 没有返回空串"""
    for pair in MIRROR_MARKERS:
        for side in pair:
            if find_marker_offset(name, side) >= 0:
                return side
    return ""


def has_wide_side_hint(name: str) -> bool:
    """名字看着像左右骨 (比 MIRROR_MARKERS 宽)"""
    if SIDE_TOKENS & set(get_bone_name_tokens(name)):
        return True
    return any(char in name for char in SIDE_CHARS)


def has_separator(name: str) -> bool:
    return bool(re.search(r"[._\- ]", name))


def guess_partner(arm, bone):
    """按 X=0 镜像位置猜伙伴: 头尾都对得上、而且左右标记相反的那根骨骼"""
    side = get_side(bone.name)
    for other in arm.data.bones:
        if other.name == bone.name:
            continue
        other_side = get_side(other.name)
        if side and other_side and other_side != SIDE_OPPOSITE[side]:
            continue
        if abs(other.head_local.x + bone.head_local.x) > POSITION_TOLERANCE:
            continue
        if abs(other.head_local.y - bone.head_local.y) > POSITION_TOLERANCE:
            continue
        if abs(other.head_local.z - bone.head_local.z) > POSITION_TOLERANCE:
            continue
        if abs(other.tail_local.x + bone.tail_local.x) > POSITION_TOLERANCE:
            continue
        if abs(other.tail_local.y - bone.tail_local.y) > POSITION_TOLERANCE:
            continue
        if abs(other.tail_local.z - bone.tail_local.z) > POSITION_TOLERANCE:
            continue
        return other
    return None


def check_armature(arm) -> bool:
    """统计一个骨架, 返回是否有需要处理的问题"""
    bones = arm.data.bones
    paired = 0
    marker_named = 0
    unmatched = []
    one_way = []
    uncovered = []

    for bone in bones:
        partner = find_mirror_bone(arm, bone.name)
        markers = has_marker(bone.name)
        if markers:
            marker_named += 1
        if partner is not None:
            paired += 1
            back = find_mirror_bone(arm, partner.name)
            if back is None or back.name != bone.name:
                one_way.append(f"{bone.name} -> {partner.name}")
            continue
        if markers:
            unmatched.append(bone.name)
        elif has_wide_side_hint(bone.name):
            uncovered.append(bone.name)

    rate = f"{paired / marker_named:.1%}" if marker_named else "无左右命名骨骼"
    print(f"\n=== {arm.name} ===")
    print(f"骨骼 {len(bones)}, 带左右标记 {marker_named}, 找到镜像伙伴 {paired}, 命名命中率 {rate}")

    if unmatched:
        print(f"\n漏配 {len(unmatched)} 根 (带标记但找不到伙伴):")
        for name in unmatched[:MAX_LIST]:
            partner = guess_partner(arm, bones[name])
            hint = f"按位置应该是 {partner.name}" if partner else "按位置也没有对称骨骼"
            print(f"    {name}  ({hint})")
        if len(unmatched) > MAX_LIST:
            print(f"    ... 共 {len(unmatched)} 根")

    if one_way:
        print(f"\n单向配对 {len(one_way)} 对:")
        for text in one_way[:MAX_LIST]:
            print(f"    {text}")
        if len(one_way) > MAX_LIST:
            print(f"    ... 共 {len(one_way)} 对")

    if uncovered:
        print(f"\n命名缺口 {len(uncovered)} 根 (看着像左右骨, 但不在 MIRROR_MARKERS 里):")
        for name in uncovered[:MAX_LIST]:
            partner = guess_partner(arm, bones[name])
            marker = "无分隔符" if not has_separator(name) else ""
            hint = f"对称骨骼 {partner.name}" if partner else "位置也没有对称骨骼"
            print(f"    {name}  ({hint}{', ' + marker if marker else ''})")
        if len(uncovered) > MAX_LIST:
            print(f"    ... 共 {len(uncovered)} 根")

    return bool(unmatched or one_way or uncovered)


def main() -> int:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    keyword = args[0] if args else ""
    arms = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    arms = [arm for arm in arms if keyword.lower() in arm.name.lower()]
    if not arms:
        print(f"没有匹配的骨架 (关键词: {keyword or '不限'})")
        return 1

    print(f"检查 {len(arms)} 个骨架 (标记 {len(MIRROR_MARKERS)} 组)")
    problems = sum(1 for arm in arms if check_armature(arm))
    print(f"\n小结: {len(arms)} 个骨架, {problems} 个有漏配 / 单向 / 命名缺口")
    return 0


if __name__ == "__main__":
    sys.exit(main())
