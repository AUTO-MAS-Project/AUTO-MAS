from __future__ import annotations

from collections.abc import Callable, Iterable
from threading import RLock
from typing import Any

from pydantic import BaseModel

from app.core.script_types import ScriptRecordCapability

from .contracts import (
    HSRAdapterGroup,
    HSRCapabilitySnapshot,
    HSRController,
    HSREngine,
    HSRTaskCatalogProvider,
)


_ENGINE_ORDER: tuple[HSREngine, ...] = ("SRA", "M7A")


def resolve_configured_engines(script_config: Any) -> tuple[HSREngine, ...]:
    """按非空脚本路径推导当前配置启用的 HSR 引擎。"""

    configured: list[HSREngine] = []
    for engine in _ENGINE_ORDER:
        if isinstance(script_config, dict):
            group = script_config.get(engine)
            path = group.get("Path") if isinstance(group, dict) else None
        elif isinstance(script_config, BaseModel):
            group = getattr(script_config, engine, None)
            path = getattr(group, "Path", None)
        else:
            path = script_config.get(engine, "Path")
        if str(path or "").strip():
            configured.append(engine)
    return tuple(configured)


class HSRRegistryService:
    """按 owner 管理 HSR 适配器组并聚合动态能力。"""

    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._groups: dict[HSREngine, HSRAdapterGroup] = {}
        self._active_sessions: dict[HSREngine, set[Any]] = {}
        self._revision = 0
        self._provider: Any = None
        self._on_change = on_change
        self._lock = RLock()

    @property
    def revision(self) -> int:
        return self._revision

    def set_provider(self, provider: Any) -> None:
        """绑定 HSR ScriptType provider，并立即同步全局能力。"""

        self._provider = provider
        self._refresh_provider()

    def register_group(
        self,
        *,
        owner: str,
        task_catalog: HSRTaskCatalogProvider,
        controller: HSRController,
    ) -> HSRAdapterGroup:
        """原子注册同一引擎的任务目录与控制器。"""

        if not owner.strip():
            raise ValueError("HSR 适配器 owner 不能为空")
        if not isinstance(task_catalog, HSRTaskCatalogProvider):
            raise TypeError("HSR 任务目录未实现 HSRTaskCatalogProvider")
        if not isinstance(controller, HSRController):
            raise TypeError("HSR 控制器未实现 HSRController")

        task_engine = task_catalog.descriptor.engine
        controller_engine = controller.descriptor.engine
        if task_engine != controller_engine:
            raise ValueError(
                f"HSR 任务目录与控制器引擎不一致: {task_engine}/{controller_engine}"
            )

        with self._lock:
            existing = self._groups.get(task_engine)
            if existing is not None and existing.owner != owner:
                raise ValueError(
                    f"HSR 引擎 {task_engine} 已由 {existing.owner} 注册"
                )
            group = HSRAdapterGroup(
                owner=owner,
                task_catalog=task_catalog,
                controller=controller,
            )
            self._groups[task_engine] = group
            self._changed()
            return group

    def unregister_owner(self, owner: str) -> tuple[HSREngine, ...]:
        """注销指定插件 owner 注册的全部适配器组。"""

        with self._lock:
            removed = tuple(
                engine
                for engine, group in self._groups.items()
                if group.owner == owner
            )
            for engine in removed:
                self._groups.pop(engine, None)
            if removed:
                self._changed()
            return removed

    def candidate_engines(self) -> tuple[HSREngine, ...]:
        return tuple(engine for engine in _ENGINE_ORDER if engine in self._groups)

    def get_group(self, engine: str) -> HSRAdapterGroup:
        normalized = self._normalize_engine(engine)
        try:
            return self._groups[normalized]
        except KeyError as exc:
            raise LookupError(f"HSR {normalized} 适配器当前未生效") from exc

    def track_session(self, engine: str, session: Any) -> None:
        """记录活动会话，供适配器禁用或插件重载时统一清理。"""

        normalized = self._normalize_engine(engine)
        with self._lock:
            if normalized not in self._groups:
                raise LookupError(f"HSR {normalized} 适配器当前未生效")
            self._active_sessions.setdefault(normalized, set()).add(session)

    def release_session(self, engine: str, session: Any) -> None:
        """移除已经完成清理的活动会话。"""

        normalized = self._normalize_engine(engine)
        with self._lock:
            sessions = self._active_sessions.get(normalized)
            if sessions is None:
                return
            sessions.discard(session)
            if not sessions:
                self._active_sessions.pop(normalized, None)

    async def close_owner_sessions(self, owner: str) -> tuple[str, ...]:
        """关闭指定适配器 owner 当前仍在运行的全部会话。"""

        with self._lock:
            engines = tuple(
                engine
                for engine, group in self._groups.items()
                if group.owner == owner
            )
        return await self._close_sessions(engines)

    async def close_all_sessions(self) -> tuple[str, ...]:
        """关闭所有活动会话，供 HSR 核心插件重载时收口。"""

        with self._lock:
            engines = tuple(self._active_sessions)
        return await self._close_sessions(engines)

    def snapshot(
        self,
        *,
        script_config: Any | None = None,
    ) -> HSRCapabilitySnapshot:
        """构建全局或脚本级能力快照。"""

        candidates = self.candidate_engines()
        selected = (
            resolve_configured_engines(script_config)
            if script_config is not None
            else candidates
        )
        effective = tuple(engine for engine in selected if engine in candidates)
        warnings = tuple(
            f"已配置路径的 {engine} 适配器当前未生效"
            for engine in selected
            if engine not in candidates
        )

        modes: list[str] = []
        adapters: list[dict[str, Any]] = []
        task_map: dict[str, dict[str, Any]] = {}
        for engine in effective:
            group = self._groups[engine]
            descriptor = group.descriptor
            for mode in descriptor.supported_modes:
                if mode not in modes:
                    modes.append(mode)

            ready = None
            ready_reason = ""
            if script_config is not None:
                ready, ready_reason = group.controller.probe(script_config)
            adapter_data = descriptor.asdict()
            adapter_data.update({"ready": ready, "ready_reason": ready_reason})
            adapters.append(adapter_data)

            for task in group.task_catalog.list_tasks():
                item = task_map.setdefault(
                    task.key,
                    {
                        **task.asdict(),
                        "engines": [],
                        "strategies": {},
                    },
                )
                item["engines"].append(engine)
                item["strategies"][engine] = list(task.strategy_lines)

        available = bool(effective)
        if available:
            unavailable_reason = None
        elif not candidates:
            unavailable_reason = "请启用 SRA 或 M7A HSR 适配器"
        elif not selected:
            unavailable_reason = "请至少配置一个已加载的 HSR 引擎路径"
        else:
            unavailable_reason = "已配置路径的 HSR 引擎适配器当前未生效"
        return HSRCapabilitySnapshot(
            revision=self._revision,
            available=available,
            unavailable_reason=unavailable_reason,
            candidate_engines=candidates,
            configured_engines=selected,
            effective_engines=effective,
            supported_modes=tuple(modes),
            adapters=tuple(adapters),
            tasks=tuple(task_map.values()),
            warnings=warnings,
        )

    def resolve_record_capability(
        self,
        config_data: dict[str, Any],
    ) -> ScriptRecordCapability:
        """供 ScriptTypeProvider 解析单条 HSR 脚本能力。"""

        snapshot = self.snapshot(script_config=config_data)
        return ScriptRecordCapability(
            available=snapshot.available,
            unavailable_reason=snapshot.unavailable_reason,
            supported_modes=snapshot.supported_modes,
        )

    @staticmethod
    def _normalize_engine(value: str) -> HSREngine:
        normalized = str(value or "").strip().upper()
        if normalized not in _ENGINE_ORDER:
            raise ValueError(f"不支持的 HSR 引擎: {value}")
        return normalized  # type: ignore[return-value]

    def _changed(self) -> None:
        self._revision += 1
        self._refresh_provider()
        if self._on_change is not None:
            self._on_change()

    async def _close_sessions(
        self,
        engines: Iterable[HSREngine],
    ) -> tuple[str, ...]:
        with self._lock:
            pending = [
                (engine, session)
                for engine in engines
                for session in self._active_sessions.get(engine, set())
            ]

        errors: list[str] = []
        for engine, session in pending:
            try:
                await session.close()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{engine}: {type(exc).__name__}: {exc}")
            finally:
                self.release_session(engine, session)
        return tuple(errors)

    def _refresh_provider(self) -> None:
        if self._provider is None:
            return
        candidates = self.candidate_engines()
        self._provider.metadata["available"] = bool(candidates)
        self._provider.metadata["unavailable_reason"] = (
            None if candidates else "请启用 SRA 或 M7A HSR 适配器"
        )
        modes: list[str] = []
        for engine in candidates:
            for mode in self._groups[engine].descriptor.supported_modes:
                if mode not in modes:
                    modes.append(mode)
        self._provider.supported_modes = tuple(modes)
