"""声明式文本节点处理；每个来源独立保留多行窗口。"""

import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from importlib import import_module
from typing import Protocol, cast, runtime_checkable

from app.utils.common.expression import ExpressionFunction, compile_expression
from app.utils.common.log.hooks import make_line_hook
from app.utils.common.log.monitor import strptime
from app.utils.common.log.patterns import (
    MultiLineAggregator,
    RegexMatcher,
    apply_patterns,
    flush_patterns,
    load_patterns,
)
from app.utils.common.log.results import LinePreprocessor
from app.utils.common.log.sources import LogReadLimitExceeded

from .contracts import (
    MAX_FRAME_BYTES,
    FunctionRef,
    PipelineSpec,
    ReportedRecord,
    WithdrawnRecord,
)

type ProcessorOutput = tuple[str, str] | ReportedRecord | WithdrawnRecord


class TextProcessor(Protocol):
    """单来源处理实例。可实现 open()，在 worker 就绪前初始化。

    close() 也承担部分初始化失败后的清理。
    """

    def process(self, line: str) -> Iterable[ProcessorOutput]: ...

    def close(self) -> Iterable[ProcessorOutput]: ...


@runtime_checkable
class OpenableProcessor(Protocol):
    def open(self) -> None: ...


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
        self.preprocess: LinePreprocessor | None = None
        if (ref := config.preprocess) is not None:
            implementation = getattr(import_module(ref.module), ref.attribute)
            if not callable(implementation):
                raise TypeError(f"行预处理器不可调用：{ref.name}")
            self.preprocess = cast(LinePreprocessor, implementation)
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
        if self.preprocess is not None:
            processed = self.preprocess(line)
            if not processed:
                return
            if len(processed.encode("utf-8")) >= MAX_FRAME_BYTES:
                raise LogReadLimitExceeded("预处理后的日志超出处理容量")
            line = processed
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

    def __init__(
        self, patterns: str, hooks: str, *, log_time: tuple[int, int, str] | None
    ) -> None:
        self.rules = load_patterns(patterns)
        self.hook = make_line_hook(hooks)
        self.log_time = log_time
        if len(self.rules) > 100 or any(
            isinstance(rule, MultiLineAggregator) and rule.max_lines > 100
            for rule in self.rules
        ):
            raise LogReadLimitExceeded("通用脚本规则数或多行窗口超过处理容量")

    def process(self, line: str) -> Iterator[tuple[str, str]]:
        processed = self.hook(line) if self.hook is not None else line
        if processed is None:
            return
        if len(processed.encode("utf-8")) >= MAX_FRAME_BYTES:
            raise LogReadLimitExceeded("单行日志超出处理容量")
        result = apply_patterns(processed, matchers=self.rules)
        if result is None:
            return
        node_type, text = result
        if self.log_time is not None:
            start, end, time_format = self.log_time
            try:
                timestamp = strptime(processed[start:end], time_format, datetime.now())
            except ValueError:
                pass
            else:
                # 通用脚本在两种通知排版里都保留正文的时间前缀。
                text = f"{timestamp:%H:%M} - {text}"
        yield node_type, text

    def close(self) -> list[tuple[str, str]]:
        return flush_patterns(self.rules)
