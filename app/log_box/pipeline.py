"""与文件和宿主无关的文本处理管线；来源与交付仍由采集会话管理。"""

from __future__ import annotations

import time
from collections.abc import Callable

from app.utils import MultiLineAggregator, RegexMatcher, apply_patterns, compile_regex
from app.utils import expression as _utils_expression

from .results import LogEntry

# 后处理器继续接收三元组，文本改写不丢失日志类型和采集时间。
ResultItem = tuple[str, str, float]
# 前置处理器逐行 map/filter：返回 None 时该行不参与后续匹配。
PreProcessor = Callable[[str], str | None]
PostProcessor = Callable[[list[ResultItem]], list[ResultItem]]


class LogPipeline:
    """每个采集会话独占处理器与结果；不读文件、不选择通知目标。"""

    def __init__(self) -> None:
        self.preprocessors: list[PreProcessor] = []
        self.postprocessors: list[PostProcessor] = []
        self.line_rules: list[RegexMatcher] = []
        self.scope_rules: list[MultiLineAggregator] = []
        self.results: list[ResultItem] = []

    def add_rule(self, match_regex: str, expr: str, log_type: str) -> None:
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

    def feed(self, line: str) -> None:
        """翻译和过滤先于匹配；行内规则首个命中，多行规则独立累积。"""
        processed = line.strip()
        if not processed:
            return
        for pre in self.preprocessors:
            processed = pre(processed)
            if processed is None:
                return
        if not processed:
            return
        if self.line_rules:
            matched = apply_patterns(processed, matchers=self.line_rules)
            if matched is not None:
                self.results.append((*matched, time.time()))
        for agg in self.scope_rules:
            result = agg.apply(processed)
            if result is not None:
                self.results.append((agg.log_type, result, time.time()))

    def finish(self) -> list[LogEntry]:
        """冲刷与归并后一次性校验交付项；保留处理器的三元组接口。"""
        for agg in self.scope_rules:
            flushed = agg.flush()
            if flushed is not None:
                self.results.append((agg.log_type, flushed, time.time()))
        for post in self.postprocessors:
            self.results = post(self.results)
        return [LogEntry.from_legacy(item) for item in self.results]
