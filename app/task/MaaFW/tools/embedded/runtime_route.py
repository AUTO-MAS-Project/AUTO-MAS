from __future__ import annotations

from collections.abc import Mapping
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
            raise MaaFWRuntimeRouteError("MaaFW Runtime Pool rootIdentity 缺少 poolId")
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


def _required_runtime_pool_text(
    value: Mapping[str, Any],
    key: str,
    label: str,
) -> str:
    raw = value.get(key)
    if raw is not None and not isinstance(raw, str):
        raise MaaFWRuntimeRouteError(f"MaaFW Runtime Pool {label}必须是字符串")
    normalized = raw.strip() if isinstance(raw, str) else ""
    if not normalized:
        raise MaaFWRuntimeRouteError(f"MaaFW Runtime Pool storage_info 缺少{label}")
    return normalized


__all__ = [
    "MaaFWRuntimePoolRoute",
    "MaaFWRuntimeRouteError",
    "RUNTIME_POOL_SERVICE",
    "runtime_pool_route_from_service",
]
