"""把外部模型导入当前 Blender 进程

复用 scripts/view_model.py 的导入逻辑, 不新开 Blender 窗口,
因此用的是当前 userpref(当前 Blender 已加载的插件), 这里是唯一的导入入口。

[Context] unreal engine 模型的导入用的很少, 暂时不测试
(`.psk` / `.psa` 需要手动启用 `io_scene_psk_psa`; `.fbx` 走 `import_fbx`)。
"""

import importlib.util
from pathlib import Path

from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from hitori_addon.const import PROJECT_DIR
from hitori_addon.importer import get_model_filter_glob
from hitori_addon.menu import register_and_invoke_menu, report_errors

VIEW_MODEL_SCRIPT: Path = PROJECT_DIR / "scripts" / "view_model.py"


def load_view_model_module():
    """按文件路径加载 view_model.py, 不污染 sys.path"""
    spec = importlib.util.spec_from_file_location(
        "hitori_view_model", VIEW_MODEL_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImportExternalModel(Operator, ImportHelper):
    bl_idname = "hitori_addon.import_external_model"
    bl_label = "导入外部模型"

    filename_ext = ""
    filter_glob: StringProperty(default=get_model_filter_glob(), options={"HIDDEN"})

    @report_errors
    def execute(self, context):
        if not VIEW_MODEL_SCRIPT.is_file():
            raise FileNotFoundError(f"找不到预览脚本:\n{VIEW_MODEL_SCRIPT}")
        load_view_model_module().load_3d_model(self.filepath)
        return {"FINISHED"}


register_and_invoke_menu(ImportExternalModel)
