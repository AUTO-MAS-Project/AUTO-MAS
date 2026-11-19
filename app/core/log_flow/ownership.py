"""宿主登记单个插件实例的在途采集会话。"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from app.models.task import TaskScriptItem, TaskUserItem
from app.plugin.errors import PluginBusyError

from .contracts import PipelineSpec
from .manager import open_for_run
from .session import LogFlowSession


class FlowOwner:
    """每次启用分配新实例，关闭旧实例不影响后来启用的插件。"""

    def __init__(self, accepting: Callable[[], bool]) -> None:
        self._accepting = accepting
        self._sealed = False
        self._starting = 0
        self._started = asyncio.Event()
        self._started.set()
        self._sessions: dict[LogFlowSession, Callable[[], None] | None] = {}

    @property
    def accepting(self) -> bool:
        return not self._sealed and self._accepting()

    @property
    def has_workers(self) -> bool:
        """启动中的会话也可能已在独立进程导入共享依赖。"""
        return self._starting > 0 or bool(self._sessions)

    @asynccontextmanager
    async def open(
        self, run: TaskScriptItem | TaskUserItem, config: PipelineSpec
    ) -> AsyncIterator[LogFlowSession]:
        if not self.accepting:
            raise PluginBusyError("插件正在释放，不再创建采集会话")
        self._starting += 1
        self._started.clear()
        try:
            session = await open_for_run(run, config)
            self._sessions[session] = None
        finally:
            self._starting -= 1
            if not self._starting:
                self._started.set()
        try:
            if not self.accepting:
                raise PluginBusyError("插件正在释放，不再交付采集会话")
            yield session
        finally:
            await self._close_session(session)

    async def _close_session(self, session: LogFlowSession) -> None:
        if (detach := self._sessions.get(session)) is not None:
            self._sessions[session] = None
            detach()
        try:
            await session.close_on_exit()
        finally:
            if session.observation.summary is not None:
                self._sessions.pop(session, None)

    def attach_cleanup(
        self, session: LogFlowSession, detach: Callable[[], None]
    ) -> None:
        self._sessions[session] = detach

    async def close(self) -> None:
        self._sealed = True
        await self._started.wait()
        await asyncio.gather(
            *(self._close_session(session) for session in tuple(self._sessions))
        )
