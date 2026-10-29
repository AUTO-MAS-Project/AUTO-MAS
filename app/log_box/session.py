"""声明式用户采集会话；隔离采集异常，收尾后在宿主线程交付节点。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from app.utils import get_logger
from app.utils.common.i18n import PoTranslator

from .collect import LogCollect, PathLike
from .logtype import LogType
from .pipeline import PostProcessor, PreProcessor
from .results import LogEntry

logger = get_logger("节点采集")

Rule = tuple[str, str] | tuple[str, str, str]


@dataclass(frozen=True)
class TranslationSpec:
    """日志翻译文件声明；补充词表覆盖原生词表，会话负责加载与释放。"""

    paths: tuple[PathLike, ...]
    supplements: tuple[PathLike, ...] = ()
    base: PathLike | None = None


@dataclass(frozen=True)
class LogBinding:
    """宿主收尾时固定的扩展：解析使用快照，交付回调只在宿主线程执行。"""

    postprocessor: PostProcessor | None = None
    deliver: Callable[[list[LogEntry]], None] | None = None
    read: Callable[[], list[LogEntry]] | None = None


@dataclass(frozen=True)
class LogSpec:
    """专项声明规则、翻译与处理器；脚本特有的语义保留在处理器中。

    后处理器可以自行归并节点或透出专项特有信息，box 不推断脚本成败。
    failure_text 为该专项原有报告兜底，未声明时只记录采集诊断。
    """

    rules: tuple[Rule, ...]
    postprocessor: PostProcessor | None = None
    preprocessor: PreProcessor | None = None
    error_message: str = "节点采集失败"
    failure_text: str | None = None
    translation: TranslationSpec | None = None
    bind: Callable[[], LogBinding] | None = None
    source: Literal["log", "entries"] = "log"

    def __post_init__(self) -> None:
        if self.source not in ("log", "entries"):
            raise ValueError("未知节点来源")
        if self.source == "entries" and (
            self.rules
            or self.preprocessor is not None
            or self.postprocessor is not None
            or self.translation is not None
        ):
            raise ValueError("结构化来源只交付已确认节点，不执行文本规则或翻译")


class LogUser(Protocol):
    push_log_mode: str
    push_log: list[tuple[str, str, float]]


class _ManagedSession:
    """两种来源共用的幂等收尾与取消屏障。"""

    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled
        self._close_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        """共享一次收尾；并发或重复关闭不会重复采集与交付。"""
        if not self._enabled:
            return
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._finish())
        cancelled: asyncio.CancelledError | None = None
        while not self._close_task.done():
            try:
                await asyncio.shield(self._close_task)
            except asyncio.CancelledError as error:
                cancelled = error
        self._close_task.result()
        if cancelled is not None:
            raise cancelled

    async def _finish(self) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class EntrySpec:
    """结构化结果声明；bind 在宿主固定快照和交付目标。"""

    bind: Callable[[], LogBinding]
    error_message: str = "结构化节点交付失败"


async def _read_entries(binding: LogBinding) -> list[LogEntry]:
    if binding.read is None or binding.postprocessor is not None:
        raise ValueError("结构化来源需要 read，且不能再做文本后处理")
    entries = await asyncio.to_thread(binding.read)
    if not isinstance(entries, list) or any(
        not isinstance(entry, LogEntry) for entry in entries
    ):
        raise TypeError("结构化来源必须返回 LogEntry 列表")
    return entries


class EntrySession(_ManagedSession):
    """无用户依赖的结构化会话；交付目标由宿主声明，不发送通知。"""

    def __init__(self, spec: EntrySpec, *, enabled: bool = True) -> None:
        super().__init__(enabled=enabled)
        self.spec = spec

    async def _finish(self) -> None:
        try:
            binding = self.spec.bind()
            if binding.deliver is None:
                raise ValueError("独立结构化会话需要声明交付目标")
            entries = await _read_entries(binding)
            binding.deliver(entries)
        except Exception:
            logger.opt(exception=True).warning(self.spec.error_message)


class UserLogSession(_ManagedSession):
    """绑定用户或专项路由的单事件循环会话；关闭后报告可读最终节点。

    日志来源在创建时记录偏移，不能延后到脚本启动后。读取、规则匹配与后处理
    在线程收尾；结构化来源直接读取已确认的节点。用户数据只在事件循环写入。
    关闭被取消时先等待结果交付，
    再传播取消，避免报告先于节点完成或线程晚到污染下一位用户。
    """

    def __init__(
        self,
        spec: LogSpec,
        *,
        user: LogUser,
        mode: str,
        paths: PathLike | Iterable[PathLike] | None = None,
        start_from_end: bool = True,
        rotated_name: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.spec = spec
        self.user = user
        self.user.push_log_mode = mode
        self._collector: LogCollect | None = None
        self._translator: PoTranslator | None = None
        self._failed = False
        super().__init__(enabled=enabled if enabled is not None else mode != "关闭")
        if not self._enabled or spec.source == "entries":
            return
        try:
            collector = LogCollect(
                paths,
                sink=self._append,
                start_from_end=start_from_end,
                rotated_name=rotated_name,
            )
            if spec.translation is not None:
                translation = spec.translation
                self._translator = PoTranslator()
                self._translator.load(translation.paths, base=translation.base)
                self._translator.load_supplement(translation.supplements)
                collector.open(self._translator.translate)
            if self._translator is None or spec.preprocessor is not None:
                collector.open(spec.preprocessor)
            # 在宿主线程编译规则并解析模块依赖，避免工作线程并发冷导入。
            for rule in spec.rules:
                collector.collect(*rule)
            self._collector = collector
        except Exception:
            self._failed = True
            logger.opt(exception=True).warning(spec.error_message)

    def _append(self, log_type: str, text: str, timestamp: float) -> None:
        self.user.push_log.append((log_type, text, timestamp))

    def _deliver(self, entries: list[LogEntry]) -> None:
        """所有来源都回到宿主交付，不要求结构化结果伪装成文本日志。"""
        for entry in entries:
            self._append(entry.log_type, entry.text, entry.timestamp)

    async def _finish(self) -> None:
        if not self._failed:
            try:
                # 动态账号等宿主数据先在事件循环固定，不能让工作线程读取可变任务状态。
                binding = (
                    self.spec.bind() if self.spec.bind is not None else LogBinding()
                )
                if self.spec.source == "entries":
                    entries = await _read_entries(binding)
                else:
                    if binding.read is not None:
                        raise ValueError("日志来源不能声明结构化 read")
                    assert self._collector is not None
                    postprocessor = (
                        binding.postprocessor
                        if binding.postprocessor is not None
                        else self.spec.postprocessor
                    )
                    entries = await asyncio.to_thread(
                        self._collector._finish, postprocessor
                    )
                if entries is not None:
                    # 不在线程内调用 sink：用户状态和报告组装归宿主线程。
                    deliver = (
                        binding.deliver
                        if binding.deliver is not None
                        else self._deliver
                    )
                    deliver(entries)
            except Exception:
                self._failed = True
                logger.opt(exception=True).warning(self.spec.error_message)
        if self._translator is not None:
            try:
                # 处理和交付已结束，不能让工作线程继续使用已清空的词表。
                self._translator.clear()
            except Exception:
                self._failed = True
                logger.opt(exception=True).warning(self.spec.error_message)
        if self._failed and self.spec.failure_text is not None:
            try:
                self._append(LogType.NORMAL, self.spec.failure_text, time.time())
            except Exception:
                # 连结果落点也不可用时只记诊断，不让采集故障变成脚本故障。
                logger.opt(exception=True).warning(self.spec.error_message)
