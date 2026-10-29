"""log_box：日志采集推送能力（与专项解耦的通用组件）

调用方提供「日志源 + 规则 + 处理器」，box 在内部
完成采集 → 前置处理 → 规则匹配提取 → 后置处理 → 结果推送。结果落点由宿主
决定：MAS 进程宿主注入 sink 直接写 push_log；脚本子进程宿主走 @@LOGBOX@@
标记回传。

内部由 collect 管理来源与交付，pipeline 执行文本处理，results 定义交付项与
节点状态，report 统一渲染节点报告和调度台结果。实际通知订阅、渠道发送及
任务状态仍由宿主负责；app.tools.push_log 仅保留兼容导出。

宿主可声明 LogSpec，通过 get_user_session 绑定用户；session 负责规则注册、
异常兜底和异步收尾。原有 get_collect 的同步接口继续兼容。

hooks 是采集管线入口的日志预处理层：按配置规则丢弃/改写日志行，供
LogMonitor（line_hook）与 LogCollect（open 前置处理器）共用同一份规则。

顶层入口：``from app.log_box import log_box, LogType``。
"""

from .collect import LogCollect
from .factory import LogBox, log_box
from .hooks import LogHook, apply_hooks, load_hooks, make_line_hook, validate_hook
from .logtype import LogType
from .session import (
    EntrySession,
    EntrySpec,
    LogBinding,
    LogSpec,
    SessionResult,
    TranslationSpec,
    UserLogSession,
)

__all__ = [
    "log_box",
    "LogBox",
    "LogCollect",
    "LogType",
    "LogSpec",
    "EntrySpec",
    "EntrySession",
    "SessionResult",
    "LogBinding",
    "TranslationSpec",
    "UserLogSession",
    "LogHook",
    "load_hooks",
    "apply_hooks",
    "make_line_hook",
    "validate_hook",
]
