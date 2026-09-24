"""HSR API domain adapters for the old-dev host.

The HTTP layer only validates script/user ownership and shapes the shared
``OutBase`` responses.  This module keeps HSR registry snapshots and dynamic
stage/managed configuration discovery next to the HSR task tools without
exposing native editor sessions through the API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

HSREngine = Literal["M7A", "SRA"]
_HSR_ENGINES: tuple[HSREngine, ...] = ("M7A", "SRA")


def _normalize_engine(engine: str) -> HSREngine:
    normalized = str(engine or "").strip().upper()
    if normalized not in _HSR_ENGINES:
        raise ValueError(f"不支持的 HSR 引擎：{engine!r}")
    return normalized  # type: ignore[return-value]


def _configured_engines(script_config: Any) -> list[HSREngine]:
    from .native_control import resolve_configured_engines

    return list(resolve_configured_engines(script_config))


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


def _installed_version(script_config: Any, engine: HSREngine) -> str | None:
    """已安装的外部脚本版本，读不到就是 ``None``（未配置或目录不完整）。

    M7A 读版本标记文件，SRA 要起一次 ``SRA-cli.exe --version``（实测 0.09 秒、
    不弹 UAC）。这个函数在 capabilities 接口里同步调用，故不做任何网络请求。
    """

    from .native_control import resolve_script_path
    from .update.engines import get_spec, read_installed_version

    root = resolve_script_path(script_config, engine)
    if not root:
        return None
    try:
        return read_installed_version(get_spec(engine), Path(root))
    except Exception:  # noqa: BLE001 - 版本读不出不该让能力接口挂掉
        return None


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

    from app.task.HSR.task_mapping import (
        HSR_TASK_MODULES,
        describe_script_fallback,
        resolve_script_assignment,
    )

    configured = _configured_engines(script_config)
    effective = list(configured)
    adapters: list[dict[str, Any]] = []
    warnings: list[str] = []
    if "SRA" in configured:
        fallback_note = _sra_profile_fallback_note(script_config)
        if fallback_note:
            warnings.append(fallback_note)
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
                "display_name": "三月七" if engine == "M7A" else "StarRailAssistant",
                "version": _installed_version(script_config, engine),
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
            engine for engine in module.supported_scripts if engine in effective_set
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
        # 脚本级 TaskMapping 指到了没配路径的引擎时，第四级回落会静默换引擎；
        # 这里把它写进快照警告，编辑页顶部能看到。
        fallback_note = describe_script_fallback(
            module,
            resolve_script_assignment(
                module, script_config, effective_engines=tuple(effective)
            ),
        )
        if fallback_note:
            warnings.append(fallback_note)
    return {
        "revision": "old-dev",
        "available": bool(configured),
        "unavailable_reason": (
            None if configured else "请至少配置一个已加载的 HSR 引擎路径"
        ),
        "candidate_engines": list(_HSR_ENGINES),
        "configured_engines": configured,
        "effective_engines": effective,
        "adapters": adapters,
        "tasks": tasks,
        "warnings": warnings,
    }


def _sra_profile_fallback_note(script_config: Any) -> str | None:
    """脚本配置的 SRA 档案不存在时的一句提示；没有回退时为 ``None``。"""

    from .sra_runtime import resolve_sra_profile_selection

    try:
        selection = resolve_sra_profile_selection(script_config)
    except OSError:
        return None
    return selection.fallback_reason if selection.fallback else None


def build_sra_profiles(script_config: Any) -> dict[str, Any]:
    """列出 ``%APPDATA%/SRA/configs`` 下可选的 SRA 配置档案。

    ``configured`` 是脚本 ``Info.SRAProfile`` 的原值（空串＝自动），``selected``
    是本次实际生效的档案；两者不一致且 ``fallback`` 为真，说明配置的档案文件
    已不存在。``auto_id`` 供前端把「自动」选项标成「自动（Default）」。
    """

    from .sra_runtime import (
        _script_sra_profile_setting,
        list_sra_profiles,
        resolve_sra_profile_selection,
    )

    selection = resolve_sra_profile_selection(script_config)
    auto = resolve_sra_profile_selection(
        {"Info": {"SRAProfile": ""}}, config_root=selection.root
    )
    profiles = list_sra_profiles(selection.root)
    if not selection.root.is_dir():
        unavailable_reason: str | None = (
            f"未找到 SRA 配置目录 {selection.root}，请先在 SRA 中保存一次设置"
        )
    elif not profiles:
        unavailable_reason = (
            f"SRA 配置目录 {selection.root} 下没有任何配置档案，"
            "请先在 SRA 中保存一次设置"
        )
    else:
        unavailable_reason = None
    return {
        "engine": "SRA",
        "root": str(selection.root),
        "available": unavailable_reason is None,
        "unavailable_reason": unavailable_reason,
        "configured": _script_sra_profile_setting(script_config),
        "auto_id": auto.selected_id,
        "selected": selection.selected_id,
        "fallback": selection.fallback,
        "fallback_reason": selection.fallback_reason,
        "profiles": [
            {
                "id": item.stem,
                "path": str(item),
                "selected": item == selection.path,
            }
            for item in profiles
        ],
    }


def build_managed_config(
    script_config: Any,
    user_config: Any | None = None,
) -> dict[str, Any]:
    """Discover managed forms and merge script/user engine assignments.

    表单值与引擎分配按该用户的计划 owner 取：「脚本」来源（以及未指定用户）
    读脚本配置上的共享计划，「用户」来源读该用户自己的计划。直控用户没有
    MAS 计划，这里按「用户」返回其残留字段，编辑页不会渲染它们。响应里的
    ``plan_owner`` 告诉前端当前表单应保存到脚本配置还是用户配置。
    """

    from app.task.HSR.task_mapping import (
        HSR_TASK_MODULES,
        describe_script_fallback,
        resolve_script_assignment,
    )

    from .managed_config import list_managed_modules
    from .native_control import resolve_plan_owner

    plan_owner: Literal["script", "user"] = (
        "script"
        if user_config is None or resolve_plan_owner(user_config) == "script"
        else "user"
    )
    plan = script_config if plan_owner == "script" else user_config

    effective = _configured_engines(script_config)
    effective_set = set(effective)
    task_forms: dict[str, dict[str, dict[str, Any]]] = {
        module.key: {} for module in HSR_TASK_MODULES
    }
    warnings: list[str] = []
    if "SRA" in effective_set:
        fallback_note = _sra_profile_fallback_note(script_config)
        if fallback_note:
            warnings.append(fallback_note)
    for engine in effective:
        try:
            modules = list_managed_modules(engine, script_config, plan)
        except (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError) as exc:
            warnings.append(f"{engine} 动态托管字段不可用：{exc}")
            continue
        for module in modules:
            task_forms.setdefault(module.key, {})[engine] = module.asdict()

    task_mapping: dict[str, HSREngine] = {}
    for module in HSR_TASK_MODULES:
        task_engines = [
            engine for engine in module.supported_scripts if engine in effective_set
        ]
        if not task_engines:
            continue
        assignment = resolve_script_assignment(
            module,
            script_config,
            user_config=plan,
            effective_engines=tuple(effective),
        )
        task_mapping[module.key] = assignment.script
        fallback_note = describe_script_fallback(module, assignment)
        if fallback_note:
            warnings.append(fallback_note)

    tasks: list[dict[str, Any]] = []
    for module in HSR_TASK_MODULES:
        task_engines = [
            engine for engine in module.supported_scripts if engine in effective_set
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
        "plan_owner": plan_owner,
        "tasks": tasks,
        "task_mapping": task_mapping,
        "warnings": warnings,
    }


__all__ = [
    "build_capabilities",
    "build_managed_config",
    "build_sra_profiles",
    "build_stage_options",
]
