"""HSR API domain adapters for the old-dev host.

The HTTP layer only validates script/user ownership and shapes the shared
``OutBase`` responses.  This module keeps HSR registry snapshots, dynamic
stage/managed configuration discovery, and direct-config imports next to the
HSR task tools without exposing native editor sessions through the API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Literal

HSREngine = Literal["M7A", "SRA"]
_HSR_ENGINES: tuple[HSREngine, ...] = ("M7A", "SRA")


def _normalize_engine(engine: str) -> HSREngine:
    normalized = str(engine or "").strip().upper()
    if normalized not in _HSR_ENGINES:
        raise ValueError(f"不支持的 HSR 引擎：{engine!r}")
    return normalized  # type: ignore[return-value]


def _configured_engines(script_config: Any) -> list[HSREngine]:
    from .native_control import resolve_script_path

    return [
        engine
        for engine in _HSR_ENGINES
        if resolve_script_path(script_config, engine)
    ]


def build_stage_options(script_config: Any, engine: str) -> dict[str, Any]:
    """Load one engine's dynamic stage options from its native files."""

    from .stage_provider import get_hsr_stage_options

    return get_hsr_stage_options(script_config, _normalize_engine(engine))


def _inspect_engine(script_config: Any, engine: HSREngine) -> dict[str, Any]:
    """Read non-secret readiness metadata for one configured engine."""

    from .native_control import native_provider

    try:
        snapshot = native_provider(engine).inspect(script_config).asdict()
    except (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError) as exc:
        return {
            "direct_run_ready": False,
            "direct_run_reason": str(exc),
        }
    return snapshot if isinstance(snapshot, dict) else {}


def _task_strategies(module: Any, engines: list[HSREngine]) -> dict[str, list[str]]:
    strategies: dict[str, list[str]] = {}
    if "M7A" in engines:
        strategies["M7A"] = list(module.m7a_tasks)
    if "SRA" in engines and module.sra_task:
        strategies["SRA"] = [module.sra_task]
    return strategies


def build_capabilities(script_config: Any) -> dict[str, Any]:
    """Build the HSR capability snapshot consumed by the edit pages.

    ``effective_engines`` follows the configured-path contract used by the old
    host.  Adapter readiness remains diagnostic metadata; it no longer embeds
    native editor/session DTOs because editor endpoints are intentionally not
    exposed by this host.
    """

    from app.task.HSR.task_mapping import HSR_TASK_MODULES

    configured = _configured_engines(script_config)
    effective = list(configured)
    adapters: list[dict[str, Any]] = []
    warnings: list[str] = []
    for engine in _HSR_ENGINES:
        snapshot = _inspect_engine(script_config, engine)
        import_ready = snapshot.get("import_ready")
        if import_ready is None:
            import_ready = engine in configured
        direct_ready = bool(snapshot.get("direct_run_ready"))
        ready = bool(import_ready or direct_ready)
        ready_reason = None
        if not ready:
            ready_reason = (
                str(
                    snapshot.get("import_reason")
                    or snapshot.get("direct_run_reason")
                    or ""
                ).strip()
                or None
            )
        adapters.append(
            {
                "engine": engine,
                "display_name": "三月七助手" if engine == "M7A" else "StarRailAssistant",
                "version": None,
                "supported_modes": ["managed", "direct"],
                "capabilities": {
                    "native_import": bool(import_ready),
                    "direct_control": direct_ready,
                },
                "ready": ready,
                "ready_reason": ready_reason,
            }
        )

    effective_set = set(effective)
    tasks: list[dict[str, Any]] = []
    for module in HSR_TASK_MODULES:
        task_engines = [
            engine
            for engine in module.supported_scripts
            if engine in effective_set
        ]
        if not task_engines:
            continue
        tasks.append(
            {
                "key": module.key,
                "name": module.name,
                "phase": module.category,
                "description": module.description,
                "engines": task_engines,
                "strategies": _task_strategies(module, task_engines),
            }
        )
    return {
        "revision": "old-dev",
        "available": bool(configured),
        "unavailable_reason": (
            None if configured else "请至少配置一个已加载的 HSR 引擎路径"
        ),
        "candidate_engines": list(_HSR_ENGINES),
        "configured_engines": configured,
        "effective_engines": effective,
        "supported_modes": ["managed", "direct"],
        "adapters": adapters,
        "tasks": tasks,
        "warnings": warnings,
    }


def build_managed_config(
    script_config: Any,
    user_config: Any | None = None,
) -> dict[str, Any]:
    """Discover managed forms and merge script/user engine assignments."""

    from app.task.HSR.task_mapping import HSR_TASK_MODULES, get_assigned_script
    from .managed_config import list_managed_modules

    effective = _configured_engines(script_config)
    effective_set = set(effective)
    task_forms: dict[str, dict[str, dict[str, Any]]] = {
        module.key: {} for module in HSR_TASK_MODULES
    }
    warnings: list[str] = []
    for engine in effective:
        try:
            modules = list_managed_modules(engine, script_config, user_config)
        except (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError) as exc:
            warnings.append(f"{engine} 动态托管字段不可用：{exc}")
            continue
        for module in modules:
            task_forms.setdefault(module.key, {})[engine] = module.asdict()

    task_mapping: dict[str, HSREngine] = {}
    for module in HSR_TASK_MODULES:
        task_engines = [
            engine
            for engine in module.supported_scripts
            if engine in effective_set
        ]
        if not task_engines:
            continue
        task_mapping[module.key] = get_assigned_script(
            module,
            script_config,
            user_config=user_config,
            effective_engines=tuple(effective),
        )

    tasks: list[dict[str, Any]] = []
    for module in HSR_TASK_MODULES:
        task_engines = [
            engine
            for engine in module.supported_scripts
            if engine in effective_set
        ]
        if not task_engines:
            continue
        tasks.append(
            {
                "key": module.key,
                "name": module.name,
                "phase": module.category,
                "description": module.description,
                "engines": task_engines,
                "strategies": _task_strategies(module, task_engines),
                "forms": task_forms.get(module.key, {}),
            }
        )
    return {
        "revision": "old-dev",
        "tasks": tasks,
        "task_mapping": task_mapping,
        "warnings": warnings,
    }


async def import_direct_config(
    script_config: Any,
    engine: str,
    *,
    script_id: str,
    user_id: str,
    update_user: Callable[[str, str, dict[str, Any]], Awaitable[Any]],
) -> dict[str, Any]:
    """Export one native config while holding the shared external path lock.

    The raw snapshot is passed only to the config persistence layer; the
    returned API result contains source metadata and byte size, never content.
    """

    from .external_locks import acquire_external_path_locks, resolve_external_lock_paths
    from .native_control import native_provider

    normalized = _normalize_engine(engine)
    lease = await acquire_external_path_locks(
        resolve_external_lock_paths(script_config, (normalized,)),
        wait=False,
    )
    try:
        source_path, content = native_provider(normalized).export_config(script_config)
        raw_content = content if isinstance(content, str) else str(content)
        imported_at = datetime.now(timezone.utc).isoformat()
        await update_user(
            script_id,
            user_id,
            {
                "Direct": {
                    f"{normalized}Config": raw_content,
                    f"{normalized}ImportedAt": imported_at,
                    f"{normalized}Source": str(source_path),
                }
            },
        )
        return {
            "engine": normalized,
            "source": str(source_path),
            "imported_at": imported_at,
            "size": len(raw_content.encode("utf-8")),
        }
    finally:
        lease.release()


__all__ = [
    "build_capabilities",
    "build_managed_config",
    "build_stage_options",
    "import_direct_config",
]
