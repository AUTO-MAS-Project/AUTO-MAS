"""mas_script：顶层别名模块（仓库根）

脚本子进程宿主通过 ``from mas_script import log_box, LogType``
使用 log_box 日志采集能力；MAS 进程宿主（专项适配器）直接
``from app.log_box import log_box``。
"""

from app.log_box import LogBox, LogCollect, LogType, log_box

__all__ = ["log_box", "LogBox", "LogCollect", "LogType"]
