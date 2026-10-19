from collections.abc import Iterable
from typing import Any


class ObjectError(Exception):
    def __init__(self, objs: Any, message: str):
        self.objs = objs
        self.message = message

    def __str__(self) -> str:
        objs = self.objs
        if isinstance(objs, str) or not isinstance(objs, Iterable):
            objs = [objs]
        # objs 可以是 None / 单个物体 / 物体列表, None 不算出错物体
        obj_names = [getattr(obj, "name", str(obj)) for obj in objs if obj is not None]
        if not obj_names:
            return self.message
        return f"出错物体: {obj_names}; 出错信息: {self.message}"


class UserError(RuntimeError):
    """已经弹窗告诉过用户, 不需要再让 Blender 打 traceback"""


# 用户能看懂的错误: 弹窗提示即可, 不要让 Blender 打 traceback
# NotImplementedError: 用户给的类型 / 路径不支持时主动抛出 (如 scripts/view_model.py)
REPORTED_ERROR_TYPES = (ObjectError, OSError, ValueError, NotImplementedError)
