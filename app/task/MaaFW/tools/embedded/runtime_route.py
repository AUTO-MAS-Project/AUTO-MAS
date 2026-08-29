from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNTIME_POOL_SERVICE = "maafw.runtime_pool.v1"


class MaaFWRuntimeRouteError(RuntimeError):
    """Raised when a runner route cannot be established without fallback."""


@dataclass(frozen=True, slots=True)
class MaaFWRuntimePoolRoute:
    root: Path
    pool_id: str


@dataclass(frozen=True, slots=True)
class MaaFWManagedExecutionRoute:
    runtime_id: str
    maafw_requirement: str
    runtime_requirements: tuple[str, ...]
    python_constraint: str | None
    shared_agent_dependencies_complete: bool
    managed_python_agent_indexes: tuple[int, ...]


def runtime_pool_route_from_service(service: Any) -> MaaFWRuntimePoolRoute:
    if service is None:
        raise MaaFWRuntimeRouteError(f"缺少服务 {RUNTIME_POOL_SERVICE}")
    storage_info = getattr(service, "storage_info", None)
    if not callable(storage_info):
        raise MaaFWRuntimeRouteError(
            f"服务 {RUNTIME_POOL_SERVICE} 未提供 storage_info()"
        )
    payload = storage_info()
    if not isinstance(payload, Mapping):
        raise MaaFWRuntimeRouteError("MaaFW Runtime Pool storage_info 必须返回对象")

    raw_root = _required_runtime_pool_text(payload, "root", "root")
    pool_id = _required_runtime_pool_text(payload, "poolId", "poolId")
    if not raw_root or not pool_id:
        raise MaaFWRuntimeRouteError(
            "MaaFW Runtime Pool storage_info 缺少 root 或 poolId"
        )

    if "rootIdentity" in payload:
        root_identity = payload["rootIdentity"]
        if not isinstance(root_identity, Mapping):
            raise MaaFWRuntimeRouteError(
                "MaaFW Runtime Pool storage_info 的 rootIdentity 必须是对象"
            )
        if "poolId" in root_identity:
            identity_pool_id = root_identity["poolId"]
            if not isinstance(identity_pool_id, str):
                raise MaaFWRuntimeRouteError(
                    "MaaFW Runtime Pool rootIdentity.poolId 必须是字符串"
                )
            identity_pool_id = identity_pool_id.strip()
        else:
            raise MaaFWRuntimeRouteError(
                "MaaFW Runtime Pool rootIdentity 缺少 poolId"
            )
        if not identity_pool_id:
            raise MaaFWRuntimeRouteError(
                "MaaFW Runtime Pool rootIdentity.poolId 不能为空"
            )
        if identity_pool_id != pool_id:
            raise MaaFWRuntimeRouteError(
                "MaaFW Runtime Pool storage_info 的 poolId 与 rootIdentity 不一致"
            )
    root_path = Path(raw_root)
    if not root_path.is_absolute():
        raise MaaFWRuntimeRouteError(
            "MaaFW Runtime Pool storage_info 的 root 必须是绝对路径"
        )
    return MaaFWRuntimePoolRoute(root=root_path.resolve(), pool_id=pool_id)


def managed_execution_route(
    *,
    managed_execution: bool,
    project: Any,
    runtime_binding: Any,
    expected_pool_id: str | None,
) -> MaaFWManagedExecutionRoute | None:
    if not managed_execution:
        if project is not None or runtime_binding is not None:
            raise MaaFWRuntimeRouteError(
                "MaaFW Managed DTO 已注入但执行标记缺失；拒绝降级为普通 MaaFW"
            )
        return None

    if not isinstance(project, Mapping) or not isinstance(runtime_binding, Mapping):
        raise MaaFWRuntimeRouteError("MaaFW Managed 执行缺少可信 project/runtime DTO")

    runtime_id = _required_text(runtime_binding, "runtimeId", "运行时 ID")
    maafw_requirement = _required_text(
        runtime_binding,
        "maafwRequirement",
        "MaaFW requirement",
    )
    binding_pool_id = _required_text(runtime_binding, "poolId", "Runtime Pool ID")
    if expected_pool_id is not None and not isinstance(expected_pool_id, str):
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed 宿主 Runtime Pool ID 必须是字符串"
        )
    normalized_expected_pool_id = (
        expected_pool_id.strip() if isinstance(expected_pool_id, str) else ""
    )
    if not normalized_expected_pool_id:
        raise MaaFWRuntimeRouteError("MaaFW Managed 执行缺少宿主 Runtime Pool ID")
    if binding_pool_id != normalized_expected_pool_id:
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed 运行时来自不同 Runtime Pool："
            f"binding={binding_pool_id}, host={normalized_expected_pool_id}"
        )

    runtime_requirements = _runtime_requirements(runtime_binding)
    if maafw_requirement not in runtime_requirements:
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed runtime DTO 的 selectorRequirements 与 "
            "maafwRequirement 不一致"
        )

    manifest = project.get("manifest")
    if not isinstance(manifest, Mapping):
        raise MaaFWRuntimeRouteError("MaaFW Managed project DTO 缺少 Store manifest")
    manifest_runtime = manifest.get("runtime")
    if not isinstance(manifest_runtime, Mapping):
        raise MaaFWRuntimeRouteError("MaaFW Managed Store manifest 缺少 runtime")
    manifest_binding = manifest_runtime.get("binding")
    if not isinstance(manifest_binding, Mapping):
        raise MaaFWRuntimeRouteError("MaaFW Managed Store manifest 尚未绑定 runtime")

    manifest_runtime_id = _required_text(
        manifest_binding,
        "runtimeId",
        "Store manifest 运行时 ID",
    )
    if manifest_runtime_id != runtime_id:
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed Store manifest 与 runtime DTO 的 runtimeId 不一致："
            f"manifest={manifest_runtime_id}, runtime={runtime_id}"
        )

    manifest_requirement = _required_text(
        manifest_binding,
        "maafwRequirement",
        "Store manifest MaaFW requirement",
    )
    if manifest_requirement != maafw_requirement:
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed Store manifest 与 runtime DTO 的 "
            "maafwRequirement 不一致"
        )
    manifest_pool_id = _required_text(
        manifest_binding,
        "poolId",
        "Store manifest Runtime Pool ID",
    )
    if manifest_pool_id != binding_pool_id:
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed Store manifest 与 runtime DTO 的 poolId 不一致"
        )
    manifest_requirements = _runtime_requirements(manifest_binding)
    if manifest_requirements != runtime_requirements:
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed Store manifest 与 runtime DTO 的完整 selector 不一致"
        )

    python_constraint: str | None = None
    python_runtime = manifest_runtime.get("python")
    if python_runtime is not None:
        if not isinstance(python_runtime, Mapping):
            raise MaaFWRuntimeRouteError(
                "MaaFW Managed Store manifest runtime.python 必须是对象"
            )
        implementation = str(
            python_runtime.get("implementation") or ""
        ).strip().casefold()
        python_constraint = str(
            python_runtime.get("constraint")
            or python_runtime.get("requires")
            or ""
        ).strip()
        if implementation != "cpython" or not python_constraint:
            raise MaaFWRuntimeRouteError(
                "MaaFW Managed Store manifest runtime.python 缺少受支持的约束"
            )

    shared_agent_dependencies_complete = (
        manifest_runtime.get("sharedAgentDependenciesComplete") is True
    )
    managed_python_agent_indexes = _managed_python_agent_indexes(
        manifest_runtime.get("agent")
    )
    if managed_python_agent_indexes and not shared_agent_dependencies_complete:
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed Store 已将 Python Agent 路由到共享解释器，"
            "但无法证明根 requirements 覆盖全部 Agent 依赖；拒绝降级到系统 Python"
        )

    return MaaFWManagedExecutionRoute(
        runtime_id=runtime_id,
        maafw_requirement=maafw_requirement,
        runtime_requirements=runtime_requirements,
        python_constraint=python_constraint,
        shared_agent_dependencies_complete=shared_agent_dependencies_complete,
        managed_python_agent_indexes=managed_python_agent_indexes,
    )


def _required_text(value: Mapping[str, Any], key: str, label: str) -> str:
    raw = value.get(key)
    if raw is not None and not isinstance(raw, str):
        raise MaaFWRuntimeRouteError(f"MaaFW Managed {label}必须是字符串")
    normalized = raw.strip() if isinstance(raw, str) else ""
    if not normalized:
        raise MaaFWRuntimeRouteError(f"MaaFW Managed 执行缺少{label}")
    return normalized


def _required_runtime_pool_text(
    value: Mapping[str, Any],
    key: str,
    label: str,
) -> str:
    raw = value.get(key)
    if raw is not None and not isinstance(raw, str):
        raise MaaFWRuntimeRouteError(
            f"MaaFW Runtime Pool {label}必须是字符串"
        )
    normalized = raw.strip() if isinstance(raw, str) else ""
    if not normalized:
        raise MaaFWRuntimeRouteError(
            f"MaaFW Runtime Pool storage_info 缺少{label}"
        )
    return normalized


def _runtime_requirements(value: Mapping[str, Any]) -> tuple[str, ...]:
    raw_requirements = value.get("selectorRequirements")
    if raw_requirements is None:
        raw_requirements = value.get("packages")
    if not isinstance(raw_requirements, Sequence) or isinstance(
        raw_requirements,
        (str, bytes, bytearray),
    ):
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed runtime DTO 缺少 selectorRequirements/packages"
        )
    requirements: list[str] = []
    for item in raw_requirements:
        if not isinstance(item, str) or not item.strip():
            raise MaaFWRuntimeRouteError(
                "MaaFW Managed runtime requirements 必须是非空字符串数组"
            )
        requirements.append(item.strip())
    if not requirements:
        raise MaaFWRuntimeRouteError("MaaFW Managed runtime requirements 不能为空")
    return tuple(requirements)


def _managed_python_agent_indexes(raw_agents: Any) -> tuple[int, ...]:
    if raw_agents is None:
        return ()
    if not isinstance(raw_agents, Sequence) or isinstance(
        raw_agents,
        (str, bytes, bytearray),
    ):
        raise MaaFWRuntimeRouteError(
            "MaaFW Managed Store manifest runtime.agent 必须是数组"
        )
    indexes: set[int] = set()
    for raw_agent in raw_agents:
        if not isinstance(raw_agent, Mapping):
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
            raise MaaFWRuntimeRouteError(
                "MaaFW Managed Store manifest 的 managed-python Agent 声明无效"
            )
        indexes.add(index)
    return tuple(sorted(indexes))


__all__ = [
    "MaaFWManagedExecutionRoute",
    "MaaFWRuntimePoolRoute",
    "MaaFWRuntimeRouteError",
    "RUNTIME_POOL_SERVICE",
    "managed_execution_route",
    "runtime_pool_route_from_service",
]
