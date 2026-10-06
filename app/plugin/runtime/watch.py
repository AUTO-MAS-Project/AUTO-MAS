"""源码监视：watchdog 监听 ``plugins/*/`` 代码类变更 → 防抖 → ``sources_changed`` 载荷。

只发信号，不 reload（换码仍走正式 ``Manager.reload``）。监视层只按路径映射到
``plugins/<dir>`` 工程根；plugin_name 由 ``refresh`` 内解析。

对齐旧 HMR 忽略集；不排除 ``auto_mas_core``（新系统 core 也可本地改）。
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from app.utils import get_logger

from ..signals import sources_changed
from ..types import SourceChange, SourcesChangedPayload

logger = get_logger("插件源码监视")

_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "pypi",
    "site-packages",
}
_IGNORED_SUFFIXES = (".egg-info", ".dist-info", ".data")
_CODE_SUFFIXES = {".py", ".pyi"}
_METADATA_SUFFIXES = {".toml", ".json"}


@dataclass
class _Pending:
    """防抖窗口内累计的变更；到期合并为一次信号。"""

    changes: dict[Path, bool] = field(default_factory=dict)
    deadline: float = 0.0


class _Handler(FileSystemEventHandler):
    """观察者线程回调：过滤后把路径交给 watcher 入队。"""

    def __init__(self, watcher: "SourceWatcher") -> None:
        super().__init__()
        self.watcher = watcher

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type in {"opened", "closed", "closed_no_write"}:
            return
        paths = [(Path(str(event.src_path)), event.is_directory)]
        dest_path = getattr(event, "dest_path", "")
        if dest_path:
            paths.append((Path(dest_path), event.is_directory))
        for path, is_directory in paths:
            self.watcher.enqueue(path, is_directory=is_directory)


class SourceWatcher:
    """启动后监视 ``plugins/``；多次保存合并为一次 ``sources_changed``。"""

    def __init__(
        self,
        *,
        plugins_dir: Path | None = None,
        debounce: float = 0.75,
    ) -> None:
        self.plugins_dir = (plugins_dir or (Path.cwd() / "plugins")).resolve()
        self.debounce = debounce
        self._pending = _Pending()
        self._observer: BaseObserver | None = None
        self._task: asyncio.Task[None] | None = None
        self._event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if not self.plugins_dir.is_dir():
            logger.warning(f"源码监视跳过：plugins 目录不存在 {self.plugins_dir}")
            return
        self._running = True
        self._loop = loop
        self._event = asyncio.Event()
        observer = Observer()
        observer.schedule(_Handler(self), str(self.plugins_dir), recursive=True)
        observer.start()
        self._observer = observer
        self._task = loop.create_task(self._run())
        logger.info(f"源码监视已启动: {self.plugins_dir}")

    async def stop(self) -> None:
        self._running = False
        observer = self._observer
        self._observer = None
        if observer is not None:
            await asyncio.to_thread(self._stop_observer, observer)

        task = self._task
        self._task = None
        event = self._event
        if event is not None:
            event.set()
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._loop = None
        self._event = None
        logger.info("源码监视已停止")

    @staticmethod
    def _stop_observer(observer: BaseObserver) -> None:
        observer.stop()
        observer.join(timeout=5.0)

    def enqueue(self, path: Path, *, is_directory: bool = False) -> None:
        """观察者线程入口：映射工程根后经 ``call_soon_threadsafe`` 回环入队。"""
        if not self._running:
            return
        local_dir = self._local_dir(path, is_directory=is_directory)
        if local_dir is None:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(
            self._add_pending,
            local_dir,
            not is_directory and path.suffix.lower() in _CODE_SUFFIXES,
        )

    def _local_dir(self, path: Path, *, is_directory: bool = False) -> Path | None:
        """映射到工程根 ``plugins/<dir>``；忽略目录/后缀；顶层文件无归属 → None。"""
        resolved = path.resolve()
        try:
            rel = resolved.relative_to(self.plugins_dir)
        except ValueError:
            return None
        parts = rel.parts
        if not parts:
            return None
        ignored_parts = parts if is_directory else parts[:-1]
        for part in ignored_parts:
            low = part.lower()
            if low in _IGNORED_DIRS or low.endswith(_IGNORED_SUFFIXES):
                return None
        if is_directory:
            return self.plugins_dir / parts[0]
        if len(parts) < 2:
            return None
        if resolved.suffix.lower() not in _CODE_SUFFIXES | _METADATA_SUFFIXES:
            return None
        return self.plugins_dir / parts[0]

    def _add_pending(self, local_dir: Path, code_touched: bool) -> None:
        if not self._running:
            return
        pending = self._pending
        pending.changes[local_dir] = (
            pending.changes.get(local_dir, False) or code_touched
        )
        pending.deadline = asyncio.get_running_loop().time() + self.debounce
        if self._event is not None:
            self._event.set()

    async def _run(self) -> None:
        while self._running:
            try:
                if not self._pending.changes:
                    await self._wait()
                    continue
                remaining = (
                    self._pending.deadline - asyncio.get_running_loop().time()
                )
                if remaining > 0:
                    await self._wait(timeout=remaining)
                    continue
                await self._flush()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"源码监视循环异常: {type(exc).__name__}: {exc}")

    async def _wait(self, timeout: float | None = None) -> None:
        event = self._event
        if event is None:
            await asyncio.sleep(timeout if timeout is not None else self.debounce)
            return
        try:
            if timeout is None:
                await event.wait()
            else:
                await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            event.clear()

    async def _flush(self) -> None:
        pending = self._pending
        self._pending = _Pending()
        sources_changed.send(
            self,
            payload=SourcesChangedPayload(
                changes=tuple(
                    SourceChange(
                        local_dir=str(local_dir),
                        code_touched=code_touched,
                    )
                    for local_dir, code_touched in sorted(pending.changes.items())
                ),
            ),
        )
