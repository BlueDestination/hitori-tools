"""饰品动骨识别回归: 21 个 PMX 语料 (异环) 的 80 个饰品材质单元 + Mayo 工程的 3 个饰品网格

`tests/data/acc_dynbone_hierarchies.json` 存的是"剪骨架后"的层级 (只留该材质顶点有权重的骨,
父级抬到最近的保留祖先, 多根时补 `arm_<材质名>_root` 合成根), 与 `acc_export` 导出前的骨架一致;
期望值是冻结的判据输出: 改判据后这里会报差异, 逐条确认是改进还是回归再更新 fixture。
Mayo 那 3 份是发根底座语料 (`Back_root` / `Side_root` / `Front_root` / `Ahoge_root` 不该注册),
真正的 base 在 Mayo 工程的测试场景里 (仅本地, 未入库)。

需要 Blender 跑 (`hitori_addon.dynbone` 依赖 bpy):
  <Blender>/blender.exe -b --factory-startup --python tests/test_acc_dynbone_names.py
"""

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).absolute().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from hitori_addon.dynbone import find_acc_dynbone_names

FIXTURE_PATH = PROJECT_DIR / "tests" / "data" / "acc_dynbone_hierarchies.json"


def load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_corpus():
    """语料里的每个饰品单元都要复现期望的动骨名"""
    data = load_fixture()
    mismatches = []
    for unit in data["units"]:
        parents = data["hierarchies"][unit["hierarchy"]]
        actual = find_acc_dynbone_names(parents)
        if actual != unit["expected"]:
            name = f"{unit['model']}/{unit['material']}"
            mismatches.append(f"{name}: 期望 {unit['expected']} 实得 {actual}")
    assert not mismatches, "语料回归:\n" + "\n".join(mismatches)


def test_single_root_bone():
    """只有一根合成根时没有动骨"""
    assert find_acc_dynbone_names({"Head": None}) == []


def test_humanoid_ancestor_is_skipped():
    """身体骨当祖先时跳过, 取它下面的非人形骨"""
    parents = {"Root": None, "Head": "Root", "Neck": "Head", "HairB_001": "Neck"}
    assert find_acc_dynbone_names(parents) == ["HairB_001"]


def test_chain_start_only():
    """命中链起点后不再往下拆成多份"""
    parents = {
        "Root": None,
        "Hips": "Root",
        "HairB_00": "Hips",
        "HairB_01": "HairB_00",
        "HairB_02": "HairB_01",
    }
    assert find_acc_dynbone_names(parents) == ["HairB_00"]


def test_holder_children_are_roots():
    """`*_root` 锤点的权重是跟着头皮不动的底座, 注册的是它下面的子骨"""
    parents = {
        "arm_acc_root": None,
        "Hair_root": "arm_acc_root",
        "Back_root": "Hair_root",
        "Back": "Back_root",
        "Back.004": "Back",
        "Side_root": "Hair_root",
        "L_Side_1": "Side_root",
        "Ahoge_root": "Hair_root",
        "Ahoge_1": "Ahoge_root",
        "Ahoge_1.001": "Ahoge_1",
    }
    assert find_acc_dynbone_names(parents) == ["Ahoge_1", "Back", "L_Side_1"]


def test_face_bones_are_humanoid():
    """MMD 面部骨 (jaw / 歯 yachi / 嘴 zuiba / lips) 不算饰品动骨"""
    parents = {
        "Head": None,
        "Bn_m_jaw_001": "Head",
        "Bon_yachi_up": "Head",
        "Bon_zuiba_L": "Head",
        "左UpLips1": "Head",
        "Bn_l_hairA_001": "Head",
    }
    assert find_acc_dynbone_names(parents) == ["Bn_l_hairA_001"]


def test_multi_root_chain():
    """合成根下两条链各取链起点"""
    parents = {
        "arm_acc_root": None,
        "HairA_001": "arm_acc_root",
        "HairA_002": "HairA_001",
        "Tail_1": "arm_acc_root",
        "Tail_2": "Tail_1",
    }
    assert find_acc_dynbone_names(parents) == ["HairA_001", "Tail_1"]


def test_root_prefix_is_chain_start():
    """`Root_` 前缀是动骨链的根骨 (与 `*_root` 锤点相反), 照常注册"""
    parents = {
        "arm_acc_root": None,
        "Root_Skirt": "arm_acc_root",
        "Skirt_1": "Root_Skirt",
    }
    assert find_acc_dynbone_names(parents) == ["Root_Skirt"]


if __name__ == "__main__":
    data = load_fixture()
    test_corpus()
    test_single_root_bone()
    test_humanoid_ancestor_is_skipped()
    test_chain_start_only()
    test_holder_children_are_roots()
    test_face_bones_are_humanoid()
    test_multi_root_chain()
    test_root_prefix_is_chain_start()
    print(f"语料 {len({unit['model'] for unit in data['units']})} 个模型 / {len(data['units'])} 个饰品单元, "
          f"骨架层级 {len(data['hierarchies'])} 份")
    print("OK: 饰品动骨识别一致")
