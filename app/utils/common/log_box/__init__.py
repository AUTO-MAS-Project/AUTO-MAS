"""纯文本处理：编译规则、处理文本、返回结果；不管理来源或交付。"""

from .hooks import LogHook, apply_hooks, load_hooks, make_line_hook, validate_hook
from .pipeline import LogPipeline, PostProcessor, PreProcessor, ResultItem
from .results import Entry, LegacyEntry, LogEntry

__all__ = [
    "LogPipeline",
    "PostProcessor",
    "PreProcessor",
    "ResultItem",
    "Entry",
    "LegacyEntry",
    "LogEntry",
    "LogHook",
    "apply_hooks",
    "load_hooks",
    "make_line_hook",
    "validate_hook",
]
