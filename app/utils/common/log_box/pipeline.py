"""纯文本处理管线；来源、执行环境和交付由调用方负责。"""

from __future__ import annotations

from collections.abc import Callable

from app.utils import (
    LOG_TYPE_NORMAL,
    MultiLineAggregator,
    RegexMatcher,
    apply_patterns,
    compile_regex,
)
from app.utils import expression as _utils_expression

from .results import LogEntry

# 后处理器继续接收三元组，文本改写不丢失日志类型和采集时间。
ResultItem = tuple[str, str, float | None]
# 前置处理器逐行 map/filter：返回 None 时该行不参与后续匹配。
PreProcessor = Callable[[str], str | None]
PostProcessor = Callable[[list[ResultItem]], list[ResultItem]]


class LogPipeline:
    """每个实例独立保存规则与文本缓冲，完成后返回处理结果。"""

    def __init__(self) -> None:
        self.preprocessors: list[PreProcessor] = []
        self.postprocessors: list[PostProcessor] = []
        self.line_rules: list[RegexMatcher] = []
        self.scope_rules: list[MultiLineAggregator] = []
        self.results: list[ResultItem] = []
        self._finished: tuple[LogEntry, ...] | None = None
        self._last_timestamp: float | None = None

    def add_rule(
        self, match_regex: str, expr: str = "", log_type: str = LOG_TYPE_NORMAL
    ) -> None:
        """保留存量规则的空值、非法正则和表达式校验语义。"""
        if not match_regex.strip():
            return
        match_re = compile_regex(match_regex)
        if match_re is None:
            raise ValueError(f"匹配正则无效: {match_regex}")
        extract = _utils_expression.compile_expression(expr) if expr else None
        self.line_rules.append(
            RegexMatcher(match=match_re, extract=extract, log_type=log_type)
        )

    def feed(self, line: str, *, timestamp: float | None = None) -> None:
        """先执行前置处理；行内规则首个命中，多行规则独立累积。"""
        if self._finished is not None:
            raise RuntimeError("文本管线已完成，不能追加文本")
        self._last_timestamp = timestamp
        processed = line.strip()
        if not processed:
            return
        for pre in self.preprocessors:
            candidate = pre(processed)
            if candidate is None:
                return
            processed = candidate
        if not processed:
            return
        if self.line_rules:
            matched = apply_patterns(processed, matchers=self.line_rules)
            if matched is not None:
                self.results.append((*matched, timestamp))
        for agg in self.scope_rules:
            result = agg.apply(processed)
            if result is not None:
                self.results.append((agg.log_type, result, timestamp))

    def finish(self) -> list[LogEntry]:
        """冲刷与归并后一次性校验交付项；保留处理器的三元组接口。"""
        if self._finished is not None:
            return list(self._finished)
        for agg in self.scope_rules:
            flushed = agg.flush()
            if flushed is not None:
                self.results.append((agg.log_type, flushed, self._last_timestamp))
        for post in self.postprocessors:
            self.results = post(self.results)
        self._finished = tuple(LogEntry.from_legacy(item) for item in self.results)
        return list(self._finished)
