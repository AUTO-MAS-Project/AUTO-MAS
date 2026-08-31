"""采集器 LogCollect：聚合多个 LogSource，执行前置/后置处理、规则匹配并推送

log_box 只对日志本身负责：接收「日志源 + 规则 + 处理器」，在内部完成
采集日志 → 前置处理（open）→ 规则匹配/提取 → 后置处理（postprocess/close）
→ 结果推送。结果落点由宿主决定：MAS 进程宿主注入 sink 直接写 push_log；
脚本子进程宿主（无 sink）走 @@LOGBOX@@ 标记回传，由 MAS 侧 check_log 嗅探。
"""

from __future__ import annotations

import atexit
import time
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

from app.utils.LogPatternExtractor import (
    LOG_TYPE_NORMAL,
    MultiLineAggregator,
    RegexMatcher,
    apply_patterns,
    compile_regex,
)
from app.utils.expression import compile_expression

from .logtype import LogType
from .markers import emit, render_flush, render_push
from .sources import LogSource, resolve_sources

# 多行聚合默认最大跨行数（与 LogPatternExtractor 保持一致）
_MULTILINE_DEFAULT_MAX_LINES = 50

PathLike = Union[str, Path]

# 前置处理器：逐行 map（返回新文本）/ filter（返回 None 丢弃该行）
_PreProcessor = Callable[[str], Optional[str]]

# 结果元组 (日志类型, 格式化文本, 采集时间戳)，时间戳为规则命中时的
# ``time.time()``，供逐条式推送为每条结果加时间前缀。
_ResultItem = tuple[str, str, float]

# 后置处理器：作用于捕捉完的最终 (日志类型, 文本, 时间戳) 结果集（去重/规整），
# 直接返回处理后的结果集，时间戳随元组一并保留，避免文本改写后丢失采集时间。
_PostProcessor = Callable[[list[_ResultItem]], list[_ResultItem]]
# sink：MAS 进程宿主注入的 push_log 写入回调（接收日志类型、文本与采集时间戳）
_Sink = Callable[[str, str, float], None]


class LogCollect:
    """日志采集会话

    open()/close() 幂等，可安全重复调用；脚本子进程宿主在脚本正常退出时
    由 atexit 自动冲刷残留并完成推送。
    """

    def __init__(
        self,
        paths: Optional[Union[PathLike, Iterable[PathLike]]] = None,
        *,
        sink: Optional[_Sink] = None,
        start_from_end: bool = True,
    ):
        self.paths = resolve_sources(paths)
        self.sources = [
            LogSource(item, start_from_end=start_from_end) for item in self.paths
        ]
        # sink：MAS 进程宿主注入；缺省时走 @@LOGBOX@@ 标记回传（脚本宿主）
        self.sink = sink
        self._preprocessors: list[_PreProcessor] = []
        self._postprocessors: list[_PostProcessor] = []
        self._line_rules: list[RegexMatcher] = []
        self._scope_rules: list[MultiLineAggregator] = []
        self._results: list[_ResultItem] = []
        self._opened = False
        self._closed = False
        # 脚本子进程宿主：脚本正常退出时自动冲刷残留并完成推送（幂等兜底）
        if sink is None:
            atexit.register(self._finalize)

    # ---------- 生命周期 ----------

    def open(
        self, processor: Optional[_PreProcessor] = None
    ) -> Union["LogCollect", Callable[[_PreProcessor], _PreProcessor]]:
        """启动采集（幂等）；processor 非 None 时直接登记前置处理器并返回 self。

        也可作为装饰器使用：``@col.open()`` 会把被装饰函数登记为前置处理器，
        作用于逐行日志（返回新文本；返回 None 丢弃该行），按序执行。
        此时（processor 为 None）返回注册器函数而非 LogCollect 实例。
        """
        self._open_sources()
        if processor is None:

            def _register(fn: _PreProcessor) -> _PreProcessor:
                self._preprocessors.append(fn)
                return fn

            return _register  # type: ignore[return-value]
        self._preprocessors.append(processor)
        return self

    def _open_sources(self) -> None:
        """为各日志源记录起始位置（幂等）；未显式调用 open() 时由收尾读取兜底"""
        if not self._opened:
            for source in self.sources:
                source.open()
            self._opened = True

    def postprocess(self, processor: Optional[_PostProcessor] = None):
        """登记后置处理器（最终处理），作用于捕捉完的最终多行结果集。

        也可作为装饰器使用：``@col.postprocess()`` 会把被装饰函数登记为后置
        处理器。只登记、不结束会话；结束由随后调用 ``col.close()`` 或脚本
        退出（atexit）触发。
        """
        if processor is None:

            def _register(fn: _PostProcessor) -> _PostProcessor:
                self._postprocessors.append(fn)
                return fn

            return _register
        self._postprocessors.append(processor)
        return processor

    def close(self, processor: Optional[_PostProcessor] = None) -> "LogCollect":
        """结束采集会话并完成推送（幂等）

        - ``col.close()``：立即结束——冲刷多行残留、应用后置处理器并推送最终结果集。
        - ``col.close(processor)``：登记后置处理器并立即结束。
        """
        if processor is not None:
            self._postprocessors.append(processor)
        self._finalize()
        return self

    def _finalize(self) -> None:
        """内部结束：采集剩余日志、冲刷残留、后置处理并推送。幂等。"""
        if self._closed:
            return
        self._closed = True
        self._capture()
        # 冲刷多行聚合残留窗口
        for agg in self._scope_rules:
            flushed = agg.flush()
            if flushed is not None:
                self._results.append((agg.log_type, flushed, time.time()))
        # 后置处理：作用于最终结果集的文本（去重/规整等）
        self._results = self._apply_postprocessors(self._results)
        # 完成推送
        self._deliver(self._results)

    def _apply_postprocessors(
        self, results: list[_ResultItem]
    ) -> list[_ResultItem]:
        """对最终结果集应用后置处理器，时间戳随 (类型, 文本, 时间戳) 元组一并保留

        后置处理器直接接收并返回 ``list[(log_type, text, ts)]``，文本改写（如
        okww_resolve 状态解析）不会丢失日志类型与采集时间，也无需按文本回映射。
        """
        if not self._postprocessors:
            return results
        for post in self._postprocessors:
            results = post(results)
        return results

    # ---------- 规则注册 ----------

    def collect(
        self, regex: str, expr: str = "", type: str = LogType.NORMAL
    ) -> "LogCollect":
        """声明式单行规则：匹配正则 + $() 提取表达式（可多条）

        匹配正则为空时不生效（与推送日志配置语义一致）；expr 为空时返回过滤后整行。
        """
        self.add_rule(regex, expr, type)
        return self

    def add_rule(
        self, match_regex: str, expr: str, log_type: str = LOG_TYPE_NORMAL
    ) -> None:
        """把 (匹配正则, 提取表达式, 日志类型) 编译为行内规则

        匹配正则为空 → 该规则不生效（跳过）；非空但正则非法、或表达式非法
        时 fail-fast（与表达式编译语义一致，开发期尽早暴露配置错误）。
        """
        if not match_regex.strip():
            return
        match_re = compile_regex(match_regex)
        if match_re is None:
            raise ValueError(f"匹配正则无效: {match_regex}")
        extract = compile_expression(expr) if expr else None
        self._line_rules.append(
            RegexMatcher(match=match_re, extract=extract, log_type=log_type)
        )

    def collect_scope(
        self,
        start_re: str,
        end_re: str = "",
        expr: str = "",
        max_lines: int = _MULTILINE_DEFAULT_MAX_LINES,
        type: str = LogType.NORMAL,
    ) -> "LogCollect":
        """多行聚合规则：起始/结束正则划定窗口，提取表达式从窗口提取字段。

        起始正则为空时不生效；结束正则留空时窗口在遇到新起始行、达到最大
        跨行数或日志处理结束时关闭。正则非空但非法时 fail-fast。
        """
        if not start_re.strip():
            return self
        start = compile_regex(start_re)
        if start is None:
            raise ValueError(f"起始正则无效: {start_re}")
        end = compile_regex(end_re) if end_re else None
        if end_re and end is None:
            raise ValueError(f"结束正则无效: {end_re}")
        extract = compile_expression(expr) if expr else None
        self._scope_rules.append(
            MultiLineAggregator(
                start_re=start,
                end_re=end,
                extract_expr=extract,
                max_lines=max_lines,
                log_type=type,
            )
        )
        return self

    # ---------- 调试与推送 ----------

    def _capture(self) -> None:
        """从各日志源采集剩余新行，执行前置处理与规则匹配，累积结果

        未显式调用 open() 时自动启动日志源（记录起始位置），保证 close() 收尾
        读取自洽。
        """
        self._open_sources()
        for source in self.sources:
            for line in source.read_new():
                self._process_line(line)

    def _process_line(self, line: str) -> None:
        """逐行处理：前置处理（翻译/过滤）→ 规则匹配与提取（均在处理后行）

        前置处理器（open 挂载）逐行翻译/过滤，返回 None 丢弃该行；此后匹配
        与提取均作用于处理后（已翻译）的行，前置翻译对下游整体生效。
        """
        processed = line.strip()
        if not processed:
            return
        for pre in self._preprocessors:
            processed = pre(processed)
            if processed is None:
                return  # 前置过滤：丢弃该行
        if not processed:
            return
        # 行内规则：首个命中即产出（与推送日志配置语义一致）
        if self._line_rules:
            matched = apply_patterns(processed, matchers=self._line_rules)
            if matched is not None:
                self._results.append((*matched, time.time()))
        # 多行聚合规则：窗口匹配与提取均用处理后行
        for agg in self._scope_rules:
            result = agg.apply(processed)
            if result is not None:
                self._results.append((agg.log_type, result, time.time()))

    def _deliver(self, results: list[_ResultItem]) -> None:
        """把结果写入 sink（MAS 进程宿主）或渲染为 @@LOGBOX@@ 标记（脚本宿主）"""
        if self.sink is not None:
            for log_type, text, ts in results:
                self.sink(log_type, text, ts)
            return
        for log_type, text, _ in results:
            emit(render_push(text, log_type))
        emit(render_flush())
