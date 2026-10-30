"""采集会话：管理日志来源与宿主交付，文本处理交给独立管线。

log_box 只对日志本身负责：接收「日志源 + 规则 + 处理器」，在内部完成
采集日志 → 前置处理（open）→ 规则匹配/提取 → 后置处理（postprocess/close）
→ 结果推送。结果落点由宿主决定：MAS 进程宿主注入 sink 直接写 push_log；
脚本子进程宿主（无 sink）走 @@LOGBOX@@ 标记回传，由 MAS 侧 check_log 嗅探。
"""

from __future__ import annotations

import atexit
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

from app.utils import LOG_TYPE_NORMAL

from .logtype import LogType
from .markers import emit, render_flush, render_push
from .pipeline import LogPipeline, PostProcessor, PreProcessor
from .results import LogEntry
from .sources import LogSource, resolve_sources

PathLike = Union[str, Path]

# sink：MAS 进程宿主注入的 push_log 写入回调（接收日志类型、文本与采集时间戳）
_Sink = Callable[[str, str, float | None], None]


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
        rotated_name: Optional[str] = None,
    ):
        self.paths = resolve_sources(paths)
        self.sources = [
            LogSource(item, start_from_end=start_from_end, rotated_name=rotated_name)
            for item in self.paths
        ]
        # sink：MAS 进程宿主注入；缺省时走 @@LOGBOX@@ 标记回传（脚本宿主）
        self.sink = sink
        # 每个会话独占规则与处理器状态，重试或不同账号之间不共享缓冲。
        self._pipeline = LogPipeline()
        self._opened = False
        self._closed = False
        # 脚本子进程宿主：脚本正常退出时自动冲刷残留并完成推送（幂等兜底）
        if sink is None:
            atexit.register(self._finalize)

    # ---------- 生命周期 ----------

    def open(
        self, processor: Optional[PreProcessor] = None
    ) -> Union["LogCollect", Callable[[PreProcessor], PreProcessor]]:
        """启动采集（幂等）；processor 非 None 时直接登记前置处理器并返回 self。

        也可作为装饰器使用：``@col.open()`` 会把被装饰函数登记为前置处理器，
        作用于逐行日志（返回新文本；返回 None 丢弃该行），按序执行。
        此时（processor 为 None）返回注册器函数而非 LogCollect 实例。
        """
        self._open_sources()
        if processor is None:

            def _register(fn: PreProcessor) -> PreProcessor:
                self._pipeline.preprocessors.append(fn)
                return fn

            return _register  # type: ignore[return-value]
        self._pipeline.preprocessors.append(processor)
        return self

    def _open_sources(self) -> None:
        """为各日志源记录起始位置（幂等）；未显式调用 open() 时由收尾读取兜底"""
        if not self._opened:
            for source in self.sources:
                source.open()
            self._opened = True

    def close(self, processor: Optional[PostProcessor] = None) -> "LogCollect":
        """结束采集会话并完成推送（幂等）

        - ``col.close()``：立即结束——冲刷多行残留、应用后置处理器并推送最终结果集。
        - ``col.close(processor)``：登记后置处理器并立即结束。
        """
        if processor is not None:
            self._pipeline.postprocessors.append(processor)
        self._finalize()
        return self

    def _finalize(self) -> None:
        """内部结束：采集剩余日志、冲刷残留、后置处理并推送。幂等。"""
        results = self._finish()
        if results is not None:
            self._deliver(results)

    def _finish(self, processor: PostProcessor | None = None) -> list[LogEntry] | None:
        """冻结结果，与宿主交付分离；托管会话可在线程中读取与解析。"""
        if self._closed:
            return None
        self._closed = True
        if processor is not None:
            self._pipeline.postprocessors.append(processor)
        self._capture()
        return self._pipeline.finish()

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
        self._pipeline.add_rule(match_regex, expr, log_type)

    # ---------- 调试与推送 ----------

    def _capture(self) -> None:
        """从各日志源采集剩余新行，执行前置处理与规则匹配，累积结果

        未显式调用 open() 时自动启动日志源（记录起始位置），保证 close() 收尾
        读取自洽。
        """
        self._open_sources()
        for source in self.sources:
            for line in source.read_new():
                self._pipeline.feed(line)

    def _deliver(self, results: list[LogEntry]) -> None:
        """把结果写入 sink（MAS 进程宿主）或渲染为 @@LOGBOX@@ 标记（脚本宿主）"""
        if self.sink is not None:
            for entry in results:
                self.sink(entry.log_type, entry.text, entry.timestamp)
            return
        for entry in results:
            emit(render_push(entry.text, entry.log_type))
        emit(render_flush())
