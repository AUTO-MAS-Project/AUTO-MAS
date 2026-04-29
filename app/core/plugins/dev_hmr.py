from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.utils import get_logger

from .realtime import publish_plugin_snapshot, send_plugin_system_message


logger = get_logger("PluginHMR")


IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "pypi",
}
IGNORED_DIR_SUFFIXES = (".egg-info",)

RELOAD_SUFFIXES = {".py", ".pyi", ".toml"}
RELOAD_FILENAMES = {
    "config.json",
    "schema.json",
    "plugin.json",
}
FRONTEND_DIR_NAMES = {"frontend", "ui", "web"}
FRONTEND_SUFFIXES = {".vue", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss", ".html"}
RESOURCE_SUFFIXES = {
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".ico",
    ".css",
    ".html",
    ".js",
    ".ts",
    ".vue",
}


@dataclass
class _PendingChange:
    files: set[Path] = field(default_factory=set)
    deadline: float = 0.0


class _PluginWatchHandler(FileSystemEventHandler):
    def __init__(self, hmr: "DevPluginHMR") -> None:
        super().__init__()
        self.hmr = hmr

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if event.event_type in {"opened", "closed_no_write"}:
            return

        paths = [Path(event.src_path)]
        dest_path = getattr(event, "dest_path", "")
        if dest_path:
            paths.append(Path(dest_path))

        for path in paths:
            self.hmr.enqueue_path(path)


class DevPluginHMR:
    """Development-only plugin HMR service based on watchdog file events."""

    def __init__(
        self,
        plugin_manager: Any,
        *,
        plugins_dir: Path | None = None,
        debounce_seconds: float = 0.75,
    ) -> None:
        self.plugin_manager = plugin_manager
        self.plugins_dir = (plugins_dir or (Path.cwd() / "plugins")).resolve()
        self.debounce_seconds = debounce_seconds
        self._pending: dict[str, _PendingChange] = {}
        self._task: asyncio.Task[None] | None = None
        self._observer: Observer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._changed_event: asyncio.Event | None = None
        self._running = False
        self._processing_lock = asyncio.Lock()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if not self.plugins_dir.exists():
            logger.warning(f"Plugin HMR skipped: plugins_dir not found: {self.plugins_dir}")
            return

        self._running = True
        self._loop = loop
        self._changed_event = asyncio.Event()
        self._observer = Observer()
        self._observer.schedule(
            _PluginWatchHandler(self),
            str(self.plugins_dir),
            recursive=True,
        )
        self._observer.start()
        self._task = loop.create_task(self._run())
        logger.info(f"Plugin HMR started: plugins_dir={self.plugins_dir}")

    async def stop(self) -> None:
        self._running = False
        observer = self._observer
        self._observer = None
        if observer is not None:
            await asyncio.to_thread(self._stop_observer, observer)

        task = self._task
        self._task = None
        changed_event = self._changed_event
        if changed_event is not None:
            changed_event.set()
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._loop = None
        self._changed_event = None
        logger.info("Plugin HMR stopped")

    @staticmethod
    def _stop_observer(observer: Observer) -> None:
        observer.stop()
        observer.join(timeout=5.0)

    def enqueue_path(self, path: Path) -> None:
        if not self._running or self._is_ignored(path):
            return

        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._add_pending_path, path.resolve())

    def _is_ignored(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(self.plugins_dir)
        except ValueError:
            return True

        for part in relative.parts:
            if part in IGNORED_DIR_NAMES:
                return True
            if part.endswith(IGNORED_DIR_SUFFIXES):
                return True
        return False

    def _add_pending_path(self, path: Path) -> None:
        if not self._running:
            return

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.debounce_seconds
        plugin_name = self._resolve_plugin_for_path(path)
        key = plugin_name or "__unknown__"
        pending = self._pending.setdefault(key, _PendingChange())
        pending.files.add(path)
        pending.deadline = max(pending.deadline, deadline)

        if self._changed_event is not None:
            self._changed_event.set()

    async def _run(self) -> None:
        while self._running:
            try:
                if not self._pending:
                    await self._wait_for_change()
                    continue

                await self._process_due_changes()
                if not self._pending:
                    continue

                next_deadline = min(pending.deadline for pending in self._pending.values())
                timeout = max(0.0, next_deadline - asyncio.get_running_loop().time())
                await self._wait_for_change(timeout=timeout)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"Plugin HMR loop failed: {type(exc).__name__}: {exc}")

    async def _wait_for_change(self, timeout: float | None = None) -> None:
        event = self._changed_event
        if event is None:
            await asyncio.sleep(timeout or self.debounce_seconds)
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

    async def _process_due_changes(self) -> None:
        if not self._pending:
            return

        now = asyncio.get_running_loop().time()
        due_keys = [
            key
            for key, pending in self._pending.items()
            if pending.deadline <= now
        ]
        for key in due_keys:
            pending = self._pending.pop(key, None)
            if pending is None:
                continue
            plugin_name = None if key == "__unknown__" else key
            await self._handle_change(plugin_name, sorted(pending.files))

    def _resolve_plugin_for_path(self, path: Path) -> str | None:
        resolved = path.resolve()
        discovered = getattr(self.plugin_manager.loader, "discovered_plugins", {}) or {}
        for plugin_name, source in discovered.items():
            source_path = getattr(source, "path", None)
            if source_path is None:
                continue
            try:
                source_root = Path(source_path).resolve()
                if resolved == source_root or source_root in resolved.parents:
                    return str(plugin_name)
            except OSError:
                continue

        try:
            relative = resolved.relative_to(self.plugins_dir)
        except ValueError:
            return None
        if not relative.parts:
            return None
        plugin_name = relative.parts[0]
        if plugin_name in IGNORED_DIR_NAMES:
            return None
        return plugin_name

    def _relative_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()

    def _is_reload_change(self, path: Path) -> bool:
        name = path.name.lower()
        suffix = path.suffix.lower()
        if suffix in RELOAD_SUFFIXES:
            return True
        if name in RELOAD_FILENAMES:
            return True
        return False

    def _is_frontend_change(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        try:
            relative_parts = path.resolve().relative_to(self.plugins_dir).parts
        except ValueError:
            relative_parts = path.parts
        return suffix in FRONTEND_SUFFIXES and any(
            part in FRONTEND_DIR_NAMES for part in relative_parts
        )

    def _is_resource_change(self, path: Path) -> bool:
        if self._is_reload_change(path):
            return False
        return path.suffix.lower() in RESOURCE_SUFFIXES

    async def _handle_change(self, plugin_name: str | None, files: list[Path]) -> None:
        async with self._processing_lock:
            changed_files = [self._relative_path(path) for path in files]
            action = self._choose_action(plugin_name, files)
            await self._publish_hmr(
                event="change",
                plugin=plugin_name,
                changed_files=changed_files,
                action=action,
                status="running",
                message="Plugin HMR processing changes",
            )

            try:
                if plugin_name is None:
                    discovered = await self._rediscover()
                    await publish_plugin_snapshot(
                        reason="dev_hmr.rediscover",
                        message="Plugin HMR rediscovered plugins",
                        discovered=discovered,
                    )
                elif action == "reload_plugin":
                    self.plugin_manager.invalidate_discover_cache()
                    if await self._has_configured_instances(plugin_name):
                        await self.plugin_manager.reload_plugin(plugin_name)
                    else:
                        discovered = await self.plugin_manager.discover_plugins(force=True)
                        await publish_plugin_snapshot(
                            reason="dev_hmr.discover_plugin",
                            message=f"Plugin code changed without configured instances: {plugin_name}",
                            discovered=discovered,
                        )
                elif action == "frontend_refresh":
                    discovered = await self._rediscover()
                    await publish_plugin_snapshot(
                        reason="dev_hmr.frontend_refresh",
                        message=f"Plugin frontend resources changed: {plugin_name}",
                        discovered=discovered,
                    )
                else:
                    discovered = await self._rediscover()
                    await publish_plugin_snapshot(
                        reason="dev_hmr.snapshot",
                        message=f"Plugin resources changed: {plugin_name}",
                        discovered=discovered,
                    )

                await self._publish_hmr(
                    event="change",
                    plugin=plugin_name,
                    changed_files=changed_files,
                    action=action,
                    status="success",
                    message="Plugin HMR completed",
                )
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    f"Plugin HMR failed: plugin={plugin_name}, action={action}, error={message}"
                )
                await self._publish_hmr(
                    event="change",
                    plugin=plugin_name,
                    changed_files=changed_files,
                    action=action,
                    status="error",
                    message=message,
                )
                with contextlib.suppress(Exception):
                    await publish_plugin_snapshot(
                        reason="dev_hmr.error",
                        message=message,
                    )

    def _choose_action(self, plugin_name: str | None, files: list[Path]) -> str:
        if plugin_name is None:
            return "rediscover"
        if any(self._is_reload_change(path) for path in files):
            return "reload_plugin"
        if any(self._is_frontend_change(path) for path in files):
            return "frontend_refresh"
        if any(self._is_resource_change(path) for path in files):
            return "reload_plugin" if self._has_enabled_instances(plugin_name) else "snapshot"
        return "snapshot"

    def _has_enabled_instances(self, plugin_name: str) -> bool:
        for record in getattr(self.plugin_manager.loader, "records", {}).values():
            if (
                getattr(record, "plugin_name", None) == plugin_name
                and getattr(record, "status", None) == "active"
            ):
                return True
        return False

    async def _has_configured_instances(self, plugin_name: str) -> bool:
        discovered = await self.plugin_manager.discover_plugins(force=True)
        instances = await self.plugin_manager.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        return any(getattr(item, "plugin", None) == plugin_name for item in instances)

    async def _rediscover(self) -> Dict[str, Any]:
        self.plugin_manager.invalidate_discover_cache()
        return await self.plugin_manager.discover_plugins(force=True)

    async def _publish_hmr(
        self,
        *,
        event: str,
        plugin: str | None,
        changed_files: list[str],
        action: str,
        status: str,
        message: str,
    ) -> None:
        await send_plugin_system_message(
            "Update",
            {
                "kind": "hmr",
                "event": event,
                "plugin": plugin,
                "changed_files": changed_files,
                "action": action,
                "status": status,
                "message": message,
            },
        )
