"""外部资源清单一致性: `hitori_addon/const.py` 与安装脚本里的两份清单必须同步。"""

import ast
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).absolute().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from hitori_addon.const import EXTERNAL_RESOURCES_FILE_LIST

INSTALL_SCRIPT = PROJECT_DIR / "install" / "init_addon_config.py"


def read_install_script_list():
    """从安装脚本源码取清单 (用 ast 解析, 不执行脚本)"""
    tree = ast.parse(INSTALL_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "EXTERNAL_RESOURCES_FILE_LIST"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(
        f"安装脚本里找不到 EXTERNAL_RESOURCES_FILE_LIST: {INSTALL_SCRIPT}"
    )


def test_external_resources_list_synced():
    """安装脚本跑在 Blender 自带的 python 上 (不能 import const), 所以清单写了两份, 这里断言一致"""
    assert list(read_install_script_list()) == list(EXTERNAL_RESOURCES_FILE_LIST)


if __name__ == "__main__":
    from_script = list(read_install_script_list())
    from_const = list(EXTERNAL_RESOURCES_FILE_LIST)
    print(f"安装脚本: {len(from_script)} 项 {from_script}")
    print(f"const.py: {len(from_const)} 项 {from_const}")
    test_external_resources_list_synced()
    print("OK: 两份清单一致")
