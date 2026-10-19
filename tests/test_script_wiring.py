"""脚本接线一致性: `addon_scripts/*.py` 要么有菜单按钮, 要么被别的脚本按名字调用。

菜单按钮和 `run_addon_script` / `run_child_scripts` 的脚本名都是字符串, 改名后两边不会一起报错,
所以这里用 ast 把两边的字符串收集起来对一遍 (不执行任何脚本)。
"""

import ast
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).absolute().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

ADDON_SCRIPTS_DIR = PROJECT_DIR / "addon_scripts"
# 菜单外的脚本目录 (如 import_external_model 按路径加载的 scripts/view_model.py), 不算悬空引用
OTHER_SCRIPT_DIRS = (PROJECT_DIR / "scripts",)
# 菜单按钮, 以及可能按名字拉起脚本的包
REFERRER_DIRS = (
    PROJECT_DIR / "hitori_addon_ui",
    PROJECT_DIR / "hitori_addon",
    ADDON_SCRIPTS_DIR,
)


def get_script_names():
    """addon_scripts 下的所有脚本"""
    return {path.name for path in ADDON_SCRIPTS_DIR.glob("*.py")}


def iter_docstring_nodes(tree: ast.AST):
    """所有 module / class / function 的 docstring 节点 (docstring 里的示例代码不算调用)"""
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            yield first.value


def iter_script_refs():
    """{脚本名: 引用它的文件}, 只认代码里的完整脚本名 (跳过 docstring 与通配符)"""
    refs = {}
    for referrer_dir in REFERRER_DIRS:
        for path in referrer_dir.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {id(node) for node in iter_docstring_nodes(tree)}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or id(node) in docstrings:
                    continue
                value = node.value
                if not isinstance(value, str) or not value.endswith(".py"):
                    continue
                # 通配符 / 后缀名 (如 "*.py"、".py") 不是脚本名
                if value.startswith(".") or any(char in value for char in "*/\\"):
                    continue
                # 脚本里自报名字不算被引用
                if path.name == value:
                    continue
                refs.setdefault(value, set()).add(path.name)
    return refs


def get_unwired_scripts():
    """没有菜单按钮、也没被别的脚本调用的脚本"""
    return get_script_names() - set(iter_script_refs())


def get_known_script_names():
    """addon_scripts 与其它脚本目录里存在的脚本"""
    names = get_script_names()
    for script_dir in OTHER_SCRIPT_DIRS:
        names |= {path.name for path in script_dir.glob("*.py")}
    return names


def get_dangling_refs():
    """引用了但实际不存在的脚本 (改名后漏改)"""
    known = get_known_script_names()
    return {name: refs for name, refs in iter_script_refs().items() if name not in known}


def test_every_script_is_wired():
    """每个脚本都要能在菜单或别的脚本里找到入口"""
    unwired = get_unwired_scripts()
    assert not unwired, f"这些脚本没有菜单按钮, 也没有被别的脚本调用: {sorted(unwired)}"


def test_no_dangling_script_ref():
    """菜单/脚本引用的脚本必须存在"""
    dangling = get_dangling_refs()
    assert not dangling, f"引用了不存在的脚本: {dangling}"


if __name__ == "__main__":
    print(f"脚本 {len(get_script_names())} 个")
    print(f"被引用 {len(iter_script_refs())} 个")
    test_every_script_is_wired()
    test_no_dangling_script_ref()
    print("OK: 接线一致")
