"""log_box：日志采集推送能力（与专项解耦的通用组件）

log_box 只对日志本身负责：调用方提供「日志源 + 规则 + 处理器」，box 在内部
完成采集 → 前置处理 → 规则匹配提取 → 后置处理 → 结果推送。结果落点由宿主
决定：MAS 进程宿主注入 sink 直接写 push_log；脚本子进程宿主走 @@LOGBOX@@
标记回传。

顶层入口：``from mas_script import log_box, Rule, LogType``。
"""

from .collect import LogCollect
from .factory import LogBox, log_box
from .logtype import LogType
from .rule import Rule

__all__ = ["log_box", "LogBox", "LogCollect", "Rule", "LogType"]
