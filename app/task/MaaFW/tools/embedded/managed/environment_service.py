from __future__ import annotations

import asyncio
import inspect
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.embedded.runtime_route import (
    MaaFWRuntimeRouteError,
    managed_execution_route,
)

from .services import (
    ManagedServiceError,
    ManagedServiceGateway,
)


MANAGED_ENVIRONMENT_SERVICE = "maafw.managed.environment.v1"
_MANAGED_SCRIPT_TYPE = "MaaFWManaged"
_MANAGED_BINDING_KEYS = (
    "projectId",
    "version",
    "storeId",
    "runRootId",
    "runtimeId",
    "poolId",
)


class MaaFWManagedEnvironmentService:
    """Resolve and prewarm the authoritative environment for one script."""

    def __init__(
        self,
        *,
        config: Any,
        gateway_provider: Callable[[], Any],
        runner_provider: Callable[[], Any],
        reserve_project_path: Callable[[str | Path], Awaitable[Any]],
        release_project_path: Callable[[Any], Awaitable[None]],
        import_paths_provider: Callable[[], Sequence[str | Path]] | None = None,
        before_run_update_provider: Callable[
            [str, Mapping[str, Any], Callable[[str], None] | None],
            Awaitable[Mapping[str, Any]],
        ]
        | None = None,
        garbage_collector_provider: Callable[[], Awaitable[Mapping[str, Any]]]
        | None = None,
        operation_runner: Callable[[Callable[[], Awaitable[Any]]], Awaitable[Any]]
        | None = None,
    ) -> None:
        self._config = config
        self._gateway_provider = gateway_provider
        self._runner_provider = runner_provider
        self._reserve_project_path = reserve_project_path
        self._release_project_path = release_project_path
        self._import_paths_provider = import_paths_provider or (lambda: ())
        self._before_run_update_provider = before_run_update_provider
        self._garbage_collector_provider = garbage_collector_provider
        self._operation_runner = operation_runner

    async def update_script_before_run(
        self,
        script_id: str,
        payload: Mapping[str, Any],
        *,
        send_log: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Run the Managed version transaction before adapter locks are held."""

        normalized_script_id = str(script_id or "").strip()
        if not normalized_script_id:
            raise ManagedServiceError("运行前更新 MaaFW 资源需要 scriptId")
        if self._before_run_update_provider is None:
            raise ManagedServiceError("MaaFW Managed 服务未提供运行前更新能力")

        async def operation() -> dict[str, Any]:
            result = await self._before_run_update_provider(
                normalized_script_id,
                dict(payload),
                send_log,
            )
            if not isinstance(result, Mapping):
                raise ManagedServiceError("MaaFW 运行前更新结果必须是 JSON object")
            return dict(result)

        if self._operation_runner is None:
            return await operation()
        result = await self._operation_runner(operation)
        if not isinstance(result, Mapping):
            raise ManagedServiceError("MaaFW 运行前更新结果必须是 JSON object")
        return dict(result)

    async def collect_unreferenced_resources(self) -> dict[str, Any]:
        """Reconcile script references and immediately collect unowned data."""

        if self._garbage_collector_provider is None:
            raise ManagedServiceError("MaaFW Managed 服务未提供资源回收能力")

        async def operation() -> dict[str, Any]:
            result = await self._garbage_collector_provider()
            if not isinstance(result, Mapping):
                raise ManagedServiceError("MaaFW 资源回收结果必须是 JSON object")
            return dict(result)

        if self._operation_runner is None:
            return await operation()
        result = await self._operation_runner(operation)
        if not isinstance(result, Mapping):
            raise ManagedServiceError("MaaFW 资源回收结果必须是 JSON object")
        return dict(result)

    async def prepare_script_environment(
        self,
        script_id: str,
        requested_path: str | Path | None,
        *,
        send_log: Callable[[str], None] | None = None,
        progress: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        normalized_script_id = str(script_id or "").strip()
        if not normalized_script_id:
            raise ManagedServiceError("准备 MaaFW 环境需要 scriptId")

        async def operation() -> dict[str, Any] | None:
            return await self._prepare_script_environment(
                normalized_script_id,
                requested_path,
                send_log=send_log,
                progress=progress,
            )

        if self._operation_runner is None:
            return await operation()
        return await self._operation_runner(operation)

    async def _prepare_script_environment(
        self,
        script_id: str,
        requested_path: str | Path | None,
        *,
        send_log: Callable[[str], None] | None,
        progress: Callable[[Mapping[str, Any]], None] | None,
    ) -> dict[str, Any] | None:
        # Do not make ordinary MaaFW scripts depend on Managed services.  The
        # type is re-read while both authoritative transactions are held, so
        # this early read is only a cheap routing decision, never a TOCTOU
        # authorization decision.
        record = await self._read_unique_script(script_id)
        if _record_field(record, "type") != _MANAGED_SCRIPT_TYPE:
            return None

        gateway = self._require_gateway()
        runner = self._require_runner()
        async with gateway.resource_transaction():
            async with self._config.script_config_transaction(
                script_id,
                owner=f"maafw-managed-environment:{script_id}",
            ):
                record = await self._read_unique_script(script_id)
                if _record_field(record, "type") != _MANAGED_SCRIPT_TYPE:
                    return None
                config = _record_config(record, f"脚本 {script_id}")
                managed = _mapping(config.get("Managed"))
                managed_runtime = _mapping(config.get("ManagedRuntime"))
                self._reject_blocking_upgrade(managed)
                expected_binding = _build_managed_binding_identity(
                    managed,
                    managed_runtime,
                )
                project_id = _required_text(
                    expected_binding,
                    "projectId",
                    "权威 projectId",
                )
                version = _required_text(
                    expected_binding,
                    "version",
                    "权威 version",
                )

                project_reference = f"maafw-script:{script_id}"
                resolution = await gateway.resolve_execution(
                    {
                        "projectId": project_id,
                        "version": version,
                        "channel": managed.get("Channel"),
                        "runtimeConstraint": managed.get("RuntimeConstraint"),
                        "projectReference": project_reference,
                        "scriptId": script_id,
                        "expectedStoreId": managed.get("StoreId"),
                        "expectedProjectManifest": managed.get("ProjectManifest"),
                        # Prewarming is a two-phase operation: resolve/ensure
                        # the runtime first, but do not publish Store/Pool
                        # references until Runner preparation succeeds.
                        "deferRuntimeBinding": True,
                    }
                )
                resolution = _required_mapping(
                    resolution,
                    "Managed Gateway resolution",
                )
                if resolution.get("bindingPersistenceDeferred") is not True:
                    raise ManagedServiceError(
                        "Managed Gateway 未确认延迟持久化 runtime binding；"
                        "拒绝在环境准备前写入资源引用"
                    )
                project = _required_mapping(
                    resolution.get("project"),
                    "Managed Gateway project DTO",
                )
                runtime = _required_mapping(
                    resolution.get("runtime"),
                    "Managed Gateway runtime DTO",
                )
                project_path = _required_text(
                    resolution,
                    "projectPath",
                    "权威 checkout 路径",
                )
                checkout = _required_mapping(
                    resolution.get("checkout"),
                    "Managed Gateway checkout DTO",
                )
                _required_text(
                    checkout,
                    "runRootId",
                    "checkout RunRoot 身份",
                )
                _required_text(
                    checkout,
                    "payloadHash",
                    "checkout Store payload 哈希",
                )
                resolved_identity = (
                    _required_text(project, "projectId", "项目 ID"),
                    _required_text(project, "version", "项目版本"),
                )
                if resolved_identity != (project_id, version):
                    raise ManagedServiceError(
                        "Managed Gateway 返回的 projectId/version 与脚本权威绑定不一致"
                    )
                _required_text(project, "storeId", "Project Store ID")
                _required_mapping(
                    project.get("manifest"),
                    "Project Store manifest",
                )
                _validate_runtime_selector(runtime)

                reservation = await self._reserve_project_path(project_path)
                if reservation is None:
                    raise ManagedServiceError(
                        "MaaFW 项目正在运行、准备或更新，暂不能准备环境"
                    )
                try:
                    return await self._prepare_resolved_environment(
                        gateway=gateway,
                        runner=runner,
                        script_id=script_id,
                        requested_path=requested_path,
                        send_log=send_log,
                        progress=progress,
                        project_reference=project_reference,
                        resolution=resolution,
                        project=project,
                        runtime=runtime,
                        project_path=project_path,
                        expected_binding=expected_binding,
                    )
                finally:
                    await self._release_project_path(reservation)

    async def _prepare_resolved_environment(
        self,
        *,
        gateway: Any,
        runner: Any,
        script_id: str,
        requested_path: str | Path | None,
        send_log: Callable[[str], None] | None,
        progress: Callable[[Mapping[str, Any]], None] | None,
        project_reference: str,
        resolution: dict[str, Any],
        project: Mapping[str, Any],
        runtime: Mapping[str, Any],
        project_path: str,
        expected_binding: Mapping[str, str],
    ) -> dict[str, Any]:
        resolved_project_id = _required_text(project, "projectId", "项目 ID")
        resolved_version = _required_text(project, "version", "项目版本")
        resolved_store_id = _required_text(project, "storeId", "Project Store ID")
        checkout = _required_mapping(
            resolution.get("checkout"),
            "Managed Gateway checkout DTO",
        )
        _required_text(
            checkout,
            "runRootId",
            "checkout RunRoot 身份",
        )
        storage = _required_runtime_storage(await gateway.runtime_storage_info())
        # Load the authoritative checkout interface before any binding write.
        # A missing/stale interface service therefore fails closed without
        # mutating Project Store references or the script record.
        interface = await gateway.load_interface(project_path)
        route_project = _project_with_runtime_binding(project, runtime)
        try:
            route = managed_execution_route(
                managed_execution=True,
                project=route_project,
                runtime_binding=runtime,
                expected_pool_id=storage["poolId"],
            )
        except MaaFWRuntimeRouteError as exc:
            raise ManagedServiceError(str(exc)) from exc
        if route is None:
            raise ManagedServiceError("MaaFW Managed 环境未生成可信 runtime route")

        _log_requested_path_mismatch(
            requested_path,
            project_path,
            send_log,
        )
        import_paths = await ManagedServiceGateway.invoke(
            self._import_paths_provider,
            (),
            {},
            "读取 MaaFW 插件导入路径",
        )
        prepare_result = await ManagedServiceGateway.invoke(
            runner.prepare_project_environment,
            (project_path, interface),
            {
                "runtime_pool_root": storage["root"],
                "runtime_requirements": route.runtime_requirements,
                "runtime_requirement": route.maafw_requirement,
                "runtime_id": route.runtime_id,
                "runtime_pool_id": storage["poolId"],
                "runtime_python_constraint": route.python_constraint,
                "import_paths": list(import_paths),
                "send_log": send_log,
                "managed_shared_agent_dependencies_complete": (
                    route.shared_agent_dependencies_complete
                ),
                "managed_python_agent_indexes": (route.managed_python_agent_indexes),
                "progress": progress,
            },
            "准备 MaaFW 项目环境",
        )
        if not isinstance(prepare_result, Mapping):
            raise ManagedServiceError("maafw.runner.v1 环境准备结果必须是 JSON object")
        # Runner preparation is the long-running part of this transaction.
        # Re-read the script binding before touching Project Store so a stale
        # result can never bind or persist after a version/runtime switch.
        await self._assert_managed_binding(script_id, expected_binding)
        binding_commit = _required_mapping(
            await gateway.bind_project_runtime_reversible(
                resolved_project_id,
                resolved_version,
                runtime,
                project_reference=project_reference,
            ),
            "Managed Gateway reversible runtime binding",
        )
        rollback_receipt = _required_mapping(
            binding_commit.get("rollback"),
            "Managed Gateway runtime binding rollback receipt",
        )
        try:
            bound_project = _required_mapping(
                binding_commit.get("project"),
                "Project Store runtime binding",
            )
            bound_identity = (
                _required_text(bound_project, "projectId", "项目 ID"),
                _required_text(bound_project, "version", "项目版本"),
                _required_text(bound_project, "storeId", "Project Store ID"),
            )
            if bound_identity != (
                resolved_project_id,
                resolved_version,
                resolved_store_id,
            ):
                raise ManagedServiceError(
                    "Project Store runtime binding 返回的 projectId/version/storeId "
                    "与本次准备身份不一致"
                )
            # Revalidate the authoritative response after the resource commit.
            # A broken Store/Gateway contract must never be promoted to script
            # ready state.  The host config write is the second phase; any
            # failure below compensates the Store binding and both Store/Pool
            # reference deltas while both authoritative transactions are held.
            managed_execution_route(
                managed_execution=True,
                project=bound_project,
                runtime_binding=runtime,
                expected_pool_id=storage["poolId"],
            )
            # The script config write is the final authority update.  Keep the
            # check immediately before it even though the transaction normally
            # serializes public config writers; this also protects alternate
            # callers that mutate the in-memory record during preparation.
            await self._assert_managed_binding(script_id, expected_binding)
            resolution["project"] = bound_project
            await self._persist_resolution(
                script_id,
                resolution,
                bound_project,
                runtime,
                project_path,
            )
        except MaaFWRuntimeRouteError as exc:
            persistence_error = ManagedServiceError(str(exc))
            await self._compensate_runtime_binding(
                gateway,
                rollback_receipt,
                persistence_error,
            )
            raise persistence_error from exc
        except BaseException as exc:
            await self._compensate_runtime_binding(
                gateway,
                rollback_receipt,
                exc,
            )
            raise
        return {
            "projectPath": project_path,
            "prepareResult": dict(prepare_result),
            "bindingIdentity": _build_resolved_binding_identity(
                bound_project,
                checkout,
                runtime,
            ),
        }

    async def _assert_managed_binding(
        self,
        script_id: str,
        expected_binding: Mapping[str, str],
    ) -> None:
        current_binding = await self._read_managed_binding_identity(script_id)
        normalized_expected = {
            key: str(expected_binding.get(key) or "").strip()
            for key in _MANAGED_BINDING_KEYS
        }
        if current_binding != normalized_expected:
            raise ManagedServiceError(
                "MaaFW Managed 脚本绑定在环境准备期间发生变化；"
                "拒绝写入旧的 projectId/version/storeId/runRootId/runtimeId/poolId"
            )

    async def _read_managed_binding_identity(
        self,
        script_id: str,
    ) -> dict[str, str]:
        record = await self._read_unique_script(script_id)
        if _record_field(record, "type") != _MANAGED_SCRIPT_TYPE:
            raise ManagedServiceError(
                f"脚本 {script_id} 已不是 MaaFWManaged，拒绝写入环境结果"
            )
        config = _record_config(record, f"脚本 {script_id}")
        return _build_managed_binding_identity(
            _mapping(config.get("Managed")),
            _mapping(config.get("ManagedRuntime")),
        )

    async def _read_unique_script(self, script_id: str) -> Any:
        try:
            records = await self._config.get_script_records(script_id)
        except Exception as exc:
            raise ManagedServiceError(f"无法读取脚本 {script_id}：{exc}") from exc
        if not isinstance(records, Sequence) or isinstance(
            records,
            (str, bytes, bytearray),
        ):
            raise ManagedServiceError("宿主 get_script_records 返回值不是数组")
        if len(records) != 1:
            raise ManagedServiceError(f"scriptId {script_id} 不是唯一脚本")
        return records[0]

    def _require_gateway(self) -> Any:
        try:
            gateway = self._gateway_provider()
        except ManagedServiceError:
            raise
        except Exception as exc:
            raise ManagedServiceError(f"无法获取 MaaFW Managed Gateway：{exc}") from exc
        for name in (
            "resource_transaction",
            "resolve_execution",
            "bind_project_runtime_reversible",
            "rollback_project_runtime_binding",
            "runtime_storage_info",
            "load_interface",
        ):
            if not callable(getattr(gateway, name, None)):
                raise ManagedServiceError(f"MaaFW Managed Gateway 缺少 {name}()")
        return gateway

    def _require_runner(self) -> Any:
        try:
            runner = self._runner_provider()
        except Exception as exc:
            raise ManagedServiceError(f"无法获取 maafw.runner.v1：{exc}") from exc
        if runner is None:
            raise ManagedServiceError("缺少服务 maafw.runner.v1")
        if not callable(getattr(runner, "prepare_project_environment", None)):
            raise ManagedServiceError(
                "maafw.runner.v1 未提供 prepare_project_environment()"
            )
        return runner

    @staticmethod
    async def _compensate_runtime_binding(
        gateway: Any,
        rollback_receipt: Mapping[str, Any],
        original_error: BaseException,
    ) -> None:
        """Finish compensation despite caller cancellation and preserve cause."""

        try:
            rollback = gateway.rollback_project_runtime_binding(rollback_receipt)
            if not inspect.isawaitable(rollback):
                raise ManagedServiceError(
                    "rollback_project_runtime_binding() 必须返回 awaitable"
                )
            rollback_task = asyncio.create_task(rollback)
        except BaseException as rollback_exc:
            original_error.add_note(
                "MaaFW runtime binding 补偿未启动；"
                f"{type(rollback_exc).__name__}: {rollback_exc}"
            )
            return
        cancellation_requested = False
        while not rollback_task.done():
            try:
                await asyncio.shield(rollback_task)
            except asyncio.CancelledError:
                cancellation_requested = True
            except Exception:
                # Inspect the authoritative result once the task is terminal.
                pass
        try:
            rollback_task.result()
        except BaseException as rollback_exc:
            original_error.add_note(
                "MaaFW runtime binding 补偿未完成；"
                f"{type(rollback_exc).__name__}: {rollback_exc}"
            )
        if cancellation_requested and not isinstance(
            original_error,
            asyncio.CancelledError,
        ):
            original_error.add_note(
                "请求在补偿期间被取消；补偿已等待至终态后再返回原始失败"
            )

    @staticmethod
    def _reject_blocking_upgrade(managed: Mapping[str, Any]) -> None:
        pending = _mapping(managed.get("PendingUpgrade"))
        state = str(pending.get("state") or "").strip()
        if state in ManagedServiceGateway.UPGRADE_BLOCKING_STATES:
            raise ManagedServiceError(
                f"资源升级事务处于 {state}，恢复完成前拒绝准备环境"
            )

    async def _persist_resolution(
        self,
        script_id: str,
        resolution: Mapping[str, Any],
        project: Mapping[str, Any],
        runtime: Mapping[str, Any],
        project_path: str,
    ) -> None:
        project_id = _required_text(project, "projectId", "项目 ID")
        version = _required_text(project, "version", "项目版本")
        runtime_id = _required_text(runtime, "runtimeId", "运行时 ID")
        store_id = _required_text(project, "storeId", "Project Store ID")
        checkout = _required_mapping(
            resolution.get("checkout"),
            "Managed Gateway checkout DTO",
        )
        update = {
            "Info": {
                "Path": project_path,
                "ProjectLabel": f"{project_id}@{version}",
            },
            "Managed": {
                "ImportProjectId": "",
                "ProjectId": project_id,
                "StoreId": store_id,
                "RunRootId": _required_text(
                    checkout,
                    "runRootId",
                    "checkout RunRoot 身份",
                ),
                "Version": version,
                "RuntimeConstraint": str(resolution.get("runtimeConstraint") or ""),
                "Status": f"共享运行时已就绪 · {runtime_id}",
                "ProjectManifest": dict(
                    _required_mapping(
                        project.get("manifest"),
                        "Project Store manifest",
                    )
                ),
            },
            "ManagedRuntime": {
                "RuntimeId": runtime_id,
                "PoolId": _required_text(
                    runtime,
                    "poolId",
                    "Runtime Pool ID",
                ),
                "PythonExecutable": _required_text(
                    runtime,
                    "pythonExecutable",
                    "运行时 Python",
                ),
                "VenvPath": _required_text(
                    runtime,
                    "venvPath",
                    "运行时 venv",
                ),
                "RuntimeBinding": dict(runtime),
            },
        }
        try:
            result = self._config.update_script(script_id, update)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            raise ManagedServiceError(
                f"无法持久化脚本 {script_id} 的 MaaFW Managed 绑定：{exc}"
            ) from exc


def _build_managed_binding_identity(
    managed: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, str]:
    manifest_value = managed.get("ProjectManifest")
    if manifest_value is not None and not isinstance(manifest_value, Mapping):
        raise ManagedServiceError("ProjectManifest 必须是 JSON object")
    manifest = dict(manifest_value) if isinstance(manifest_value, Mapping) else {}
    project_id = _optional_identity_text(
        manifest.get("projectId"),
        "ProjectManifest.projectId",
    ) or _optional_identity_text(managed.get("ProjectId"), "Managed.ProjectId")
    version = _optional_identity_text(
        manifest.get("version"),
        "ProjectManifest.version",
    ) or _optional_identity_text(managed.get("Version"), "Managed.Version")
    return {
        "projectId": project_id,
        "version": version,
        "storeId": _optional_identity_text(
            managed.get("StoreId"),
            "Managed.StoreId",
        ),
        "runRootId": _optional_identity_text(
            managed.get("RunRootId"),
            "Managed.RunRootId",
        ),
        "runtimeId": _optional_identity_text(
            runtime.get("RuntimeId"),
            "ManagedRuntime.RuntimeId",
        ),
        "poolId": _optional_identity_text(
            runtime.get("PoolId"),
            "ManagedRuntime.PoolId",
        ),
    }


def _build_resolved_binding_identity(
    project: Mapping[str, Any],
    checkout: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "projectId": _required_text(project, "projectId", "项目 ID"),
        "version": _required_text(project, "version", "项目版本"),
        "storeId": _required_text(project, "storeId", "Project Store ID"),
        "runRootId": _required_text(
            checkout,
            "runRootId",
            "checkout RunRoot 身份",
        ),
        "runtimeId": _required_text(runtime, "runtimeId", "运行时 ID"),
        "poolId": _required_text(runtime, "poolId", "Runtime Pool ID"),
    }


def _required_runtime_storage(value: Any) -> dict[str, str]:
    storage = _required_mapping(value, "Runtime Pool storage_info")
    if storage.get("available") is False:
        raise ManagedServiceError(
            str(storage.get("reason") or "Runtime Pool storage_info 不可用")
        )
    root = _required_text(storage, "root", "Runtime Pool root")
    pool_id = _required_text(storage, "poolId", "Runtime Pool ID")
    if "rootIdentity" in storage:
        root_identity = storage["rootIdentity"]
        if not isinstance(root_identity, Mapping):
            raise ManagedServiceError(
                "Runtime Pool storage_info 的 rootIdentity 必须是 JSON object"
            )
        if "poolId" in root_identity:
            identity_pool_id = root_identity["poolId"]
            if not isinstance(identity_pool_id, str):
                raise ManagedServiceError(
                    "Runtime Pool rootIdentity.poolId必须是字符串"
                )
            identity_pool_id = identity_pool_id.strip()
        else:
            raise ManagedServiceError("Runtime Pool rootIdentity 缺少 poolId")
        if not identity_pool_id:
            raise ManagedServiceError("Runtime Pool rootIdentity.poolId不能为空")
        if identity_pool_id != pool_id:
            raise ManagedServiceError(
                "Runtime Pool storage_info 的 poolId 与 rootIdentity 不一致"
            )
    root_path = Path(root)
    if not root_path.is_absolute():
        raise ManagedServiceError("Runtime Pool storage_info 的 root 必须是绝对路径")
    return {"root": str(root_path.resolve()), "poolId": pool_id}


def _validate_runtime_selector(runtime: Mapping[str, Any]) -> None:
    _required_text(runtime, "runtimeId", "运行时 ID")
    _required_text(runtime, "poolId", "Runtime Pool ID")
    _required_text(runtime, "pythonExecutable", "运行时 Python")
    _required_text(runtime, "venvPath", "运行时 venv")
    maafw_requirement = _required_text(
        runtime,
        "maafwRequirement",
        "MaaFW requirement",
    )
    requirements = runtime.get("selectorRequirements")
    if requirements is None:
        requirements = runtime.get("packages")
    if not isinstance(requirements, Sequence) or isinstance(
        requirements,
        (str, bytes, bytearray),
    ):
        raise ManagedServiceError(
            "MaaFW Managed runtime DTO 缺少 selectorRequirements/packages"
        )
    normalized: list[str] = []
    for item in requirements:
        if not isinstance(item, str) or not item.strip():
            raise ManagedServiceError(
                "MaaFW Managed runtime requirements 必须是非空字符串数组"
            )
        normalized.append(item.strip())
    if not normalized:
        raise ManagedServiceError("MaaFW Managed runtime requirements 不能为空")
    if maafw_requirement not in normalized:
        raise ManagedServiceError(
            "MaaFW Managed runtime DTO 的 selectorRequirements 与 "
            "maafwRequirement 不一致"
        )


def _project_with_runtime_binding(
    project: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a trusted route view without publishing the binding early."""

    projected = dict(project)
    manifest = _required_mapping(
        project.get("manifest"),
        "Project Store manifest",
    )
    manifest_runtime_value = manifest.get("runtime")
    if manifest_runtime_value is not None and not isinstance(
        manifest_runtime_value,
        Mapping,
    ):
        raise ManagedServiceError("Project Store manifest runtime 必须是 JSON object")
    manifest_runtime = (
        dict(manifest_runtime_value)
        if isinstance(manifest_runtime_value, Mapping)
        else {}
    )
    manifest_runtime["binding"] = dict(runtime)
    manifest["runtime"] = manifest_runtime
    projected["manifest"] = manifest
    return projected


def _log_requested_path_mismatch(
    requested_path: str | Path | None,
    resolved_path: str,
    send_log: Callable[[str], None] | None,
) -> None:
    requested = str(requested_path or "").strip()
    if not requested or send_log is None:
        return
    try:
        matches = os.path.normcase(str(Path(requested).resolve())) == os.path.normcase(
            str(Path(resolved_path).resolve())
        )
    except (OSError, ValueError):
        matches = False
    if matches:
        return
    try:
        send_log(
            "[MaaFW Managed] 页面项目路径已过期；"
            f"改用 Project Store 权威 checkout: {resolved_path}"
        )
    except Exception:
        # Logging is observational and must not abort the authoritative bind.
        return


def _record_field(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def _record_config(record: Any, label: str) -> dict[str, Any]:
    config = _record_field(record, "config")
    if not isinstance(config, Mapping):
        raise ManagedServiceError(f"{label}配置不是 JSON object")
    return dict(config)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _required_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ManagedServiceError(f"{label} 必须是 JSON object")
    return dict(value)


def _required_text(value: Mapping[str, Any], key: str, label: str) -> str:
    raw = value.get(key)
    if raw is not None and not isinstance(raw, str):
        raise ManagedServiceError(f"{label}必须是字符串")
    normalized = raw.strip() if isinstance(raw, str) else ""
    if not normalized:
        raise ManagedServiceError(f"{label}不能为空")
    return normalized


def _optional_identity_text(value: Any, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ManagedServiceError(f"{label}必须是字符串")
    return value.strip()


__all__ = [
    "MANAGED_ENVIRONMENT_SERVICE",
    "MaaFWManagedEnvironmentService",
]
