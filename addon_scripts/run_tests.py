from hitori_addon.const import TESTS_DIR
from hitori_addon.run import run_test_script

newest_script_path = max(TESTS_DIR.glob("*.py"), key=lambda p: p.stat().st_mtime)
newest_script_basename = newest_script_path.name
run_test_script(newest_script_basename)
