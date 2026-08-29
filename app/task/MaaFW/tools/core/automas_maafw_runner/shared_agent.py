from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


PROJECT_MANIFEST_NAME = ".auto_mas_maafw_project.json"
SHARED_RUNTIME_KIND = "shared_runtime"
_BARE_PYTHON_COMMANDS = frozenset(
    {
        "py",
        "py.exe",
        "python",
        "python.exe",
        "python3",
        "python3.exe",
        "pythonw",
        "pythonw.exe",
    }
)
_PYTHON_OPTIONS_WITH_VALUE = frozenset(
    {
        "--check-hash-based-pycs",
        "-W",
        "-X",
    }
)


class MaaFWSharedAgentRouteError(RuntimeError):
    """Raised when authoritative managed-Python metadata is inconsistent."""


def route_managed_python_agents_to_shared_runtime(
    project_path: str | Path,
    plans: Iterable[Any],
    *,
    python_executable: str | Path | None = None,
    dependencies_complete: bool | None = None,
    managed_python_agent_indexes: Iterable[int] | None = None,
) -> list[Any]:
    """Route managed isolated Python agents through the current worker.

    Reuse is opt-in because the runtime selector alone cannot prove that it
    contains every transitive Agent dependency. Managed execution passes the
    authoritative Project Store metadata through ``dependencies_complete`` and
    ``managed_python_agent_indexes``. Ordinary and legacy projects leave both
    values unset and retain the local manifest behaviour. An ``external`` plan
    is accepted only when Store identified that exact index as a stripped
    managed-Python Agent and its invocation has a safe project-local script.
    """

    project = Path(project_path).resolve()
    if dependencies_complete is None:
        (
            shared_dependencies_complete,
            trusted_agent_indexes,
        ) = _shared_agent_route_metadata(project)
    else:
        shared_dependencies_complete = dependencies_complete is True
        trusted_agent_indexes = _normalize_agent_indexes(
            managed_python_agent_indexes
        )
    if not shared_dependencies_complete:
        if trusted_agent_indexes:
            raise MaaFWSharedAgentRouteError(
                "Managed Python Agent dependencies are not complete; refusing "
                "to fall back to a system Python"
            )
        return []

    plan_list = list(plans)
    _validate_managed_python_plans(
        project,
        plan_list,
        trusted_agent_indexes,
    )
    shared_python = str(Path(python_executable or sys.executable).resolve())
    routed: list[Any] = []
    for index, plan in enumerate(plan_list):
        if bool(getattr(plan, "embedded", False)):
            continue

        runtime_kind = getattr(plan, "runtimeKind", None)
        if runtime_kind == "isolated_venv":
            pass
        elif runtime_kind == "external":
            if index not in trusted_agent_indexes:
                continue
            if not _is_bare_python_command(getattr(plan, "childExec", None)):
                continue
            if _safe_python_entrypoint(
                project,
                getattr(plan, "childArgs", None),
            ) is None:
                continue
        else:
            continue

        command = list(getattr(plan, "command", None) or [])
        if command:
            command[0] = shared_python
        else:
            command = [shared_python, *list(getattr(plan, "childArgs", None) or [])]
        plan.command = command
        plan.executable = shared_python
        plan.executableExists = Path(shared_python).is_file()
        plan.runtimeKind = SHARED_RUNTIME_KIND
        plan.isolatedVenvPath = None
        shared_reason = "managed project reuses the shared MaaFW runtime"
        previous_reason = str(getattr(plan, "fallbackReason", None) or "").strip()
        plan.fallbackReason = (
            f"{previous_reason}; {shared_reason}"
            if previous_reason
            else shared_reason
        )
        routed.append(plan)
    return routed


def _shared_agent_route_metadata(project_path: Path) -> tuple[bool, frozenset[int]]:
    manifest_path = project_path / PROJECT_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return False, frozenset()
    if not isinstance(payload, dict):
        return False, frozenset()
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        return False, frozenset()
    dependencies_complete = runtime.get("sharedAgentDependenciesComplete") is True
    return (
        dependencies_complete,
        _managed_python_agent_indexes(runtime.get("agent")),
    )


def _managed_python_agent_indexes(raw_agents: Any) -> frozenset[int]:
    if raw_agents is None:
        return frozenset()
    if not isinstance(raw_agents, list):
        raise MaaFWSharedAgentRouteError(
            "Managed Store manifest runtime.agent must be an array"
        )
    indexes: set[int] = set()
    for raw_agent in raw_agents:
        if not isinstance(raw_agent, dict):
            continue
        if raw_agent.get("interpreterRoute") != "managed-python":
            continue
        index = raw_agent.get("index")
        if (
            type(index) is not int
            or index < 0
            or str(raw_agent.get("classification") or "").casefold()
            != "python"
            or str(raw_agent.get("projectedChildExec") or "").casefold()
            != "python"
        ):
            raise MaaFWSharedAgentRouteError(
                "Managed Store manifest contains an invalid managed-python "
                "Agent declaration"
            )
        indexes.add(index)
    return frozenset(indexes)


def _normalize_agent_indexes(
    raw_indexes: Iterable[int] | None,
) -> frozenset[int]:
    if raw_indexes is None:
        return frozenset()
    indexes: set[int] = set()
    for index in raw_indexes:
        if type(index) is not int or index < 0:
            raise MaaFWSharedAgentRouteError(
                "Managed Python Agent indexes must be non-negative integers"
            )
        indexes.add(index)
    return frozenset(indexes)


def _validate_managed_python_plans(
    project_path: Path,
    plans: list[Any],
    trusted_agent_indexes: frozenset[int],
) -> None:
    for index in trusted_agent_indexes:
        if index >= len(plans):
            raise MaaFWSharedAgentRouteError(
                "Managed Python Agent index is outside the current interface: "
                f"{index}"
            )
        plan = plans[index]
        if (
            bool(getattr(plan, "embedded", False))
            or getattr(plan, "runtimeKind", None) != "external"
            # Project Store canonicalizes every stripped interpreter to this
            # exact command. A different bare alias means the checkout no
            # longer matches the authoritative projection.
            or str(getattr(plan, "childExec", None) or "").casefold()
            != "python"
            or _safe_python_entrypoint(
                project_path,
                getattr(plan, "childArgs", None),
            )
            is None
        ):
            raise MaaFWSharedAgentRouteError(
                "Managed Python Agent declaration no longer matches the "
                f"trusted Store projection at index {index}"
            )


def _is_bare_python_command(raw_command: Any) -> bool:
    if not isinstance(raw_command, str):
        return False
    return raw_command.casefold() in _BARE_PYTHON_COMMANDS


def _safe_python_entrypoint(
    project_path: Path,
    raw_args: Any,
) -> Path | None:
    if not isinstance(raw_args, (list, tuple)):
        return None
    entrypoint = _python_entrypoint_arg(raw_args)
    if entrypoint is None:
        return None
    try:
        candidate = Path(entrypoint)
        if not candidate.is_absolute():
            candidate = project_path / candidate
        resolved = candidate.resolve()
        resolved.relative_to(project_path)
    except (OSError, RuntimeError, ValueError):
        return None
    if resolved.suffix.casefold() not in {".py", ".pyw"}:
        return None
    return resolved if resolved.is_file() else None


def _python_entrypoint_arg(raw_args: list[Any] | tuple[Any, ...]) -> str | None:
    consume_next = False
    after_options = False
    for raw_arg in raw_args:
        if not isinstance(raw_arg, str) or not raw_arg:
            return None
        if consume_next:
            consume_next = False
            continue
        if after_options:
            return raw_arg
        if raw_arg == "--":
            after_options = True
            continue
        if (
            raw_arg == "-"
            or raw_arg == "-c"
            or raw_arg.startswith("-c")
            or raw_arg == "-m"
            or raw_arg.startswith("-m")
        ):
            return None
        if raw_arg in _PYTHON_OPTIONS_WITH_VALUE:
            consume_next = True
            continue
        if raw_arg.startswith("-"):
            continue
        return raw_arg
    return None


__all__ = [
    "MaaFWSharedAgentRouteError",
    "PROJECT_MANIFEST_NAME",
    "SHARED_RUNTIME_KIND",
    "route_managed_python_agents_to_shared_runtime",
]
