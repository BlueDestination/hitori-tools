from dataclasses import dataclass


@dataclass
class RunState:
    # 本次按钮运行只弹出了对话框, 真正的改动在确认对话框后才发生
    dialog_opened: bool = False


RUN_STATE: RunState = RunState()
