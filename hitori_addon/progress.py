from collections.abc import Iterable, Sequence

import bpy
from bpy.types import WindowManager


class Progress:
    def __init__(self, iterable: Iterable | Sequence):
        self.items: list = list(iterable)
        self.total: int = len(self.items)
        self.current: int = 0
        self.wm: WindowManager = bpy.context.window_manager

        # 启动进度条
        self.wm.progress_begin(0, self.total)

    def __next__(self):
        if self.current < self.total:
            item = self.items[self.current]
            self.current += 1
            self.wm.progress_update(self.current)
            return item
        else:
            self.wm.progress_end()
            raise StopIteration

    def __iter__(self):
        return self
