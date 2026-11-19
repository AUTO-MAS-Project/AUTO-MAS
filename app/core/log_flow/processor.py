"""声明式文本节点处理；每个来源独立保留多行窗口。"""

import re
from collections.abc import Iterator, Mapping
from importlib import import_module
from typing import cast

from app.utils.common.expression import ExpressionFunction, compile_expression
from app.utils.common.log.patterns import (
    LOG_TYPE_NORMAL,
    MultiLineAggregator,
    RegexMatcher,
    apply_patterns,
    flush_patterns,
    load_patterns,
)
from app.utils.common.log.sources import LogReadLimitExceeded
from app.utils.common.log_box.hooks import make_line_hook
from app.utils.common.log_box.protocol import parse_marker

from .contracts import MAX_FRAME_BYTES, FunctionRef, PipelineSpec


def load_functions(refs: tuple[FunctionRef, ...]) -> dict[str, ExpressionFunction]:
    """解析宿主提供的可信工厂快照；不读取配置或初始化宿主。"""
    functions: dict[str, ExpressionFunction] = {}
    for ref in refs:
        if ref.name in functions:
            raise ValueError(f"重复的表达式函数：{ref.name}")
        implementation = getattr(import_module(ref.module), ref.attribute)
        if not callable(implementation):
            raise TypeError(f"表达式函数不可调用：{ref.name}")
        functions[ref.name] = cast(ExpressionFunction, implementation)
    return functions


class RuleNodeProcessor:
    def __init__(
        self, config: PipelineSpec, functions: Mapping[str, ExpressionFunction]
    ) -> None:
        self.rules = [
            RegexMatcher(
                match=re.compile(rule.match),
                extract=compile_expression(rule.extract, extensions=functions)
                if rule.extract
                else None,
                log_type=rule.node_type,
            )
            for rule in config.rules
        ]
        self.windows = [
            MultiLineAggregator(
                start_re=re.compile(rule.start),
                end_re=re.compile(rule.end) if rule.end else None,
                extract_expr=compile_expression(rule.extract, extensions=functions)
                if rule.extract
                else None,
                max_lines=rule.max_lines,
                log_type=rule.node_type,
            )
            for rule in config.windows
        ]

    def process(self, line: str) -> Iterator[tuple[str, str]]:
        line = line.strip()
        if not line:
            return
        if len(line.encode("utf-8")) >= MAX_FRAME_BYTES:
            raise LogReadLimitExceeded("单行日志超出处理容量")
        result = apply_patterns(line, matchers=self.rules)
        if result is not None:
            yield result
        for window in self.windows:
            if (text := window.apply(line)) is not None:
                yield window.log_type, text

    def close(self) -> list[tuple[str, str]]:
        return flush_patterns(self.windows)


class GeneralRuleProcessor:
    """复用 WebUI 规则的匹配顺序、停用项和预处理语义。"""

    def __init__(self, patterns: str, hooks: str) -> None:
        self.rules = load_patterns(patterns)
        self.hook = make_line_hook(hooks)
        if len(self.rules) > 100 or any(
            isinstance(rule, MultiLineAggregator) and rule.max_lines > 100
            for rule in self.rules
        ):
            raise LogReadLimitExceeded("通用脚本规则数或多行窗口超过处理容量")

    def process(self, line: str) -> Iterator[tuple[str, str]]:
        processed = self.hook(line) if self.hook is not None else line
        if processed is not None:
            if len(processed.encode("utf-8")) >= MAX_FRAME_BYTES:
                raise LogReadLimitExceeded("单行日志超出处理容量")
            marker = parse_marker(processed)
            if marker is not None:
                if marker.get("op") == "push" and (
                    text := str(marker.get("text") or "")
                ):
                    yield str(marker.get("type") or LOG_TYPE_NORMAL), text
                return
            result = apply_patterns(processed, matchers=self.rules)
            if result is not None:
                yield result

    def close(self) -> list[tuple[str, str]]:
        return flush_patterns(self.rules)
