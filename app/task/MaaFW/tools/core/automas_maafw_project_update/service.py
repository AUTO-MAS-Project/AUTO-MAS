from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from ..automas_maafw_interface.models import MaaFWInterface

from .updater import (
    DOWNLOAD_MAX_BYTES,
    MaaFWDownloadedProjectPackage,
    MaaFWProjectUpdateCandidate,
    MaaFWProjectUpdateDiscovery,
    MaaFWProjectUpdateError,
    MaaFWProjectUpdateResult,
    MaaFWUpdateProviderInfo,
    _normalise_package_source,
    apply_maafw_project_update,
    check_maafw_project_update,
    detect_maafw_project_shell_hint,
    discover_maafw_project_update,
    download_maafw_project_package,
    list_update_providers,
    release_maafw_project_package,
    update_maafw_project_if_needed,
    persist_maafw_update_plan,
    resolve_maafw_update_plan_candidate,
)
from .state import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_PLAN_ROOT,
    cancel_update,
    discard_update_artifact,
    list_recovery_operations,
    request_update_pause,
    resume_update,
    UpdateOperationStore,
    UpdatePlanStore,
)
from .contracts import project_fingerprint
from .apply import recover_update_operation


class MaaFWProjectUpdateService:
    """maafw.project_update.v1 service."""

    def list_providers(self) -> list[MaaFWUpdateProviderInfo]:
        return list_update_providers()

    @staticmethod
    def _script_id(script_id: str | None, host_context: Mapping[str, Any] | None) -> str:
        return str(
            script_id
            or (host_context or {}).get("scriptId")
            or (host_context or {}).get("script_id")
            or ""
        ).strip()

    @staticmethod
    def _public_operation_state(state: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {
            "operationId",
            "planId",
            "scriptId",
            "status",
            "createdAt",
            "updatedAt",
            "downloadedBytes",
            "totalBytes",
            "resumedFromBytes",
            "sha256",
            "etag",
            "lastModified",
            "supportsResume",
            "packageType",
            "fromVersion",
            "targetVersion",
            "recoveryRequired",
            "error",
            "rollbackError",
            "attempt",
            "cacheHit",
            "discarded",
        }
        return {key: state[key] for key in allowed if key in state}

    @staticmethod
    def _public_plan_state(state: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {
            "planId",
            "scriptId",
            "status",
            "createdAt",
            "updatedAt",
            "projectFingerprint",
            "currentVersion",
            "targetVersion",
            "source",
            "metadataSource",
            "packageSource",
            "channel",
            "artifactId",
            "packageType",
            "fromVersion",
            "toVersion",
            "size",
            "etag",
            "lastModified",
            "rangeSupported",
            "sha256",
            "operationId",
            "error",
        }
        return {key: state[key] for key in allowed if key in state}

    def pause_operation(self, operation_id: str) -> dict[str, Any]:
        return self._public_operation_state(request_update_pause(operation_id))

    def resume_operation(self, operation_id: str) -> dict[str, Any]:
        return self._public_operation_state(resume_update(operation_id))

    def cancel_operation(self, operation_id: str) -> dict[str, Any]:
        return self._public_operation_state(cancel_update(operation_id))

    def discard_operation(self, operation_id: str) -> dict[str, Any]:
        return self._public_operation_state(discard_update_artifact(operation_id))

    def operation_status(self, operation_id: str) -> dict[str, Any]:
        """Return the durable state used by a page or a restart reconciler."""

        operation = UpdateOperationStore.open(operation_id)
        try:
            state = operation.read()
        except Exception as exc:
            # A status request is also a recovery probe.  Do not surface a
            # corrupt journal as a transient 500 or let callers infer that a
            # partially-applied project is safe to run.
            state = operation.mark_recovery_required(str(exc))
        return self._public_operation_state(state)

    def active_operations(self, script_id: str | None = None) -> list[dict[str, Any]]:
        """List non-terminal operations without exposing signed URLs."""

        terminal = {"committed", "cancelled", "failed", "rolled_back"}
        result: list[dict[str, Any]] = []
        for operation in list_recovery_operations():
            try:
                state = operation.read()
            except Exception as exc:
                try:
                    operation.mark_recovery_required(str(exc))
                except Exception:
                    pass
                state = {"operationId": operation.operation_id, "status": "recovery_required"}
            if str(state.get("status") or "") not in terminal and (
                not script_id or str(state.get("scriptId") or "") == script_id
            ):
                result.append(self._public_operation_state(state))
        return result

    def status_for_script(
        self,
        script_id: str,
        operation_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the latest plan/operation state for UI restart recovery."""

        wanted = str(script_id or "").strip()
        if operation_id:
            state = self.operation_status(operation_id)
            return state if not wanted or state.get("scriptId") == wanted else None
        candidates: list[dict[str, Any]] = []
        if DEFAULT_PLAN_ROOT.is_dir():
            for directory in DEFAULT_PLAN_ROOT.iterdir():
                if not directory.is_dir() or not (directory / "plan.json").is_file():
                    continue
                try:
                    state = UpdatePlanStore.open(directory.name).read()
                except Exception:
                    continue
                if not wanted or str(state.get("scriptId") or "") == wanted:
                    candidates.append(state)
        if not candidates:
            # The one-shot compatibility path can create an operation without
            # first persisting a plan.  It still needs to be discoverable by
            # the UI's initial ``status(scriptId)`` call after a restart.
            operation_states: list[dict[str, Any]] = []
            for operation in list_recovery_operations():
                try:
                    state = operation.read()
                except Exception as exc:
                    try:
                        state = operation.mark_recovery_required(str(exc))
                    except Exception:
                        state = {
                            "operationId": operation.operation_id,
                            "status": "recovery_required",
                        }
                if not wanted or str(state.get("scriptId") or "") == wanted:
                    operation_states.append(state)
            if not operation_states:
                return None
            latest_operation = max(
                operation_states,
                key=lambda item: float(item.get("updatedAt") or 0),
            )
            return {"operation": self._public_operation_state(latest_operation)}
        latest = max(candidates, key=lambda item: float(item.get("updatedAt") or 0))
        result: dict[str, Any] = {"plan": self._public_plan_state(latest)}
        linked_operation = str(latest.get("operationId") or "").strip()
        linked_candidates: list[dict[str, Any]] = []
        for operation in list_recovery_operations():
            try:
                state = operation.read()
            except Exception as exc:
                try:
                    state = operation.mark_recovery_required(str(exc))
                except Exception:
                    continue
            if (
                str(state.get("planId") or "") == str(latest.get("planId") or "")
                and (not wanted or str(state.get("scriptId") or "") == wanted)
            ):
                linked_candidates.append(state)
        if linked_candidates:
            newest = max(
                linked_candidates,
                key=lambda item: float(item.get("updatedAt") or 0),
            )
            result["operation"] = self._public_operation_state(newest)
        elif linked_operation:
            try:
                result["operation"] = self.operation_status(linked_operation)
            except Exception:
                result["operation"] = {"operationId": linked_operation, "status": "recovery_required"}
        return result

    def recover_operation(
        self,
        operation_id: str,
        *,
        script_id: str | None = None,
        project_path: str | Path | None = None,
    ) -> dict[str, Any]:
        operation = UpdateOperationStore.open(operation_id)
        state = operation.read()
        expected_script = str(state.get("scriptId") or "").strip()
        supplied_script = str(script_id or "").strip()
        if expected_script and expected_script != supplied_script:
            raise MaaFWProjectUpdateError("update operation script context mismatch")
        if project_path is not None:
            expected_path = os.path.normcase(
                str(Path(str(state.get("projectPath") or "")).resolve(strict=False))
            )
            supplied_path = os.path.normcase(
                str(Path(project_path).resolve(strict=False))
            )
            if not expected_path or expected_path != supplied_path:
                raise MaaFWProjectUpdateError("update operation project binding changed")
        return self._public_operation_state(recover_update_operation(operation))

    def dispatch_operation_action(
        self,
        operation_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Small stable action contract for API/WS layers."""

        normalized = str(action or "").strip().lower()
        if normalized == "pause":
            return self.pause_operation(operation_id)
        if normalized == "resume":
            return self.resume_operation(operation_id)
        if normalized == "cancel":
            return self.cancel_operation(operation_id)
        if normalized == "discard":
            return self.discard_operation(operation_id)
        if normalized == "recover":
            return self.recover_operation(operation_id)
        if normalized == "status":
            return self.operation_status(operation_id)
        raise MaaFWProjectUpdateError(f"unsupported MaaFW update action: {action}")

    async def create_plan(
        self,
        interface: MaaFWInterface | dict[str, Any],
        *,
        project_path: str | Path,
        current_version: str | None = None,
        source_config: dict[str, Any] | None = None,
        mirror_cdk: str = "",
        channel: str = "stable",
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
        script_id: str | None = None,
        host_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Discover once and persist an exact, URL-free execution plan."""

        root = Path(project_path).resolve()
        effective_config = dict(source_config or {})
        if mirror_cdk and not str(effective_config.get("mirror_cdk") or "").strip():
            effective_config["mirror_cdk"] = mirror_cdk
        if channel and not str(effective_config.get("channel") or "").strip():
            effective_config["channel"] = channel
        discovery = await self.discover_update(
            interface,
            current_version=current_version,
            project_path=root,
            source_config=effective_config,
            proxy=proxy,
            send_log=send_log,
        )
        resolved_current = str(
            current_version
            if current_version is not None
            else getattr(self._coerce_interface(interface), "version", "")
            or ""
        )
        package_source = _normalise_package_source(
            effective_config.get("package_source")
            or effective_config.get("packageSource")
            or effective_config.get("source")
        )
        if discovery is None:
            return {
                "checked": True,
                "updateAvailable": False,
                "installable": False,
                "currentVersion": resolved_current,
                "metadataSource": "mirrorchyan",
                "packageSource": package_source,
            }
        if discovery.candidate is None or not discovery.installable:
            return {
                "checked": True,
                "updateAvailable": True,
                "installable": False,
                "currentVersion": resolved_current,
                "targetVersion": discovery.version,
                "source": package_source,
                "metadataSource": "mirrorchyan",
                "packageSource": package_source,
                "error": discovery.unavailable_reason or "update package is unavailable",
            }
        expected = discovery.project_fingerprint or await asyncio.to_thread(
            project_fingerprint,
            root,
        )
        plan = persist_maafw_update_plan(
            root,
            self._coerce_interface(interface),
            discovery,
            source_config=effective_config,
            expected_fingerprint=expected,
            script_id=self._script_id(script_id, host_context),
        )
        return {
            **self._public_plan_state(plan.read()),
            "checked": True,
            "updateAvailable": True,
            "installable": True,
            "metadataSource": "mirrorchyan",
            "packageSource": package_source,
        }

    async def start_plan_download(
        self,
        plan_id: str,
        *,
        expected_fingerprint: str | None = None,
        mirror_cdk: str = "",
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
        max_download_bytes: int = DOWNLOAD_MAX_BYTES,
        progress: Any = None,
        script_id: str | None = None,
        host_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = UpdatePlanStore.open(plan_id)
        state = plan.read()
        self._assert_plan_context(state, expected_fingerprint, script_id, host_context)
        candidate = await resolve_maafw_update_plan_candidate(
            plan,
            mirror_cdk=mirror_cdk,
            proxy=proxy,
        )
        downloaded = await download_maafw_project_package(
            DEFAULT_CACHE_ROOT,
            candidate,
            proxy=proxy,
            send_log=send_log,
            max_download_bytes=max_download_bytes,
            progress=progress,
            plan_id=plan.plan_id,
            expected_fingerprint=str(state.get("projectFingerprint") or ""),
            script_id=str(state.get("scriptId") or ""),
        )
        plan.update(
            "downloaded",
            operationId=downloaded.operation_id or "",
            downloadedBytes=downloaded.size,
            totalBytes=downloaded.total_bytes,
            resumedFromBytes=downloaded.resumed_from,
            sha256=downloaded.sha256,
        )
        return {
            "plan": self._public_plan_state(plan.read()),
            "package": self._downloaded_package_dict(downloaded),
            "operation": self.operation_status(downloaded.operation_id)
            if downloaded.operation_id
            else {},
        }

    async def apply_plan(
        self,
        plan_id: str,
        *,
        expected_fingerprint: str | None = None,
        mirror_cdk: str = "",
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
        progress: Any = None,
        post_validate: Any = None,
        project_lock_already_held: bool = False,
        expected_project_path: str | Path | None = None,
        script_id: str | None = None,
        host_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = UpdatePlanStore.open(plan_id)
        state = plan.read()
        self._assert_plan_context(state, expected_fingerprint, script_id, host_context)
        if expected_project_path is not None:
            planned_path = os.path.normcase(
                str(Path(str(state.get("projectPath") or "")).resolve(strict=False))
            )
            supplied_path = os.path.normcase(
                str(Path(expected_project_path).resolve(strict=False))
            )
            if not planned_path or planned_path != supplied_path:
                raise MaaFWProjectUpdateError("update plan project binding changed")
        candidate = await resolve_maafw_update_plan_candidate(
            plan,
            mirror_cdk=mirror_cdk,
            proxy=proxy,
        )
        result = await apply_maafw_project_update(
            Path(str(state.get("projectPath") or "")).resolve(),
            candidate,
            proxy=proxy,
            send_log=send_log,
            progress=progress,
            post_validate=post_validate,
            project_lock_already_held=project_lock_already_held,
            script_id=str(state.get("scriptId") or "") or None,
        )
        plan.update(
            "committed",
            operationId=str(result.get("operationId") or ""),
            finalFingerprint=str(result.get("finalFingerprint") or ""),
        )
        return {
            "plan": self._public_plan_state(plan.read()),
            "result": result,
            "operation": self.operation_status(str(result.get("operationId") or "")),
        }

    def _assert_plan_context(
        self,
        state: Mapping[str, Any],
        expected_fingerprint: str | None,
        script_id: str | None,
        host_context: Mapping[str, Any] | None,
    ) -> None:
        planned = str(state.get("projectFingerprint") or "").strip()
        supplied = str(expected_fingerprint or "").strip()
        if planned and not supplied:
            raise MaaFWProjectUpdateError("update plan fingerprint confirmation is required")
        if planned and supplied and planned != supplied:
            raise MaaFWProjectUpdateError("update plan fingerprint confirmation failed")
        expected_script = str(state.get("scriptId") or "").strip()
        supplied_script = self._script_id(script_id, host_context)
        if expected_script and not supplied_script:
            raise MaaFWProjectUpdateError("update plan script context is required")
        if expected_script and expected_script != supplied_script:
            raise MaaFWProjectUpdateError("update plan script context mismatch")

    async def discover_plan(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.create_plan(*args, **kwargs)

    async def execute_plan_action(
        self,
        plan_id: str,
        action: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        normalized = str(action or "").strip().lower()
        if normalized in {"download", "start_download"}:
            return await self.start_plan_download(plan_id, **kwargs)
        if normalized in {"apply", "apply_plan"}:
            return await self.apply_plan(plan_id, **kwargs)
        plan = UpdatePlanStore.open(plan_id)
        state = plan.read()
        operation_id = str(state.get("operationId") or "").strip()
        if normalized == "status":
            return self._public_plan_state(state)
        if not operation_id:
            raise MaaFWProjectUpdateError("update plan has no active operation")
        if normalized == "pause":
            return self.pause_operation(operation_id)
        if normalized == "resume":
            return self.resume_operation(operation_id)
        if normalized == "cancel":
            return self.cancel_operation(operation_id)
        if normalized == "discard":
            return self.discard_operation(operation_id)
        if normalized == "recover":
            return self.recover_operation(operation_id)
        raise MaaFWProjectUpdateError(f"unsupported MaaFW plan action: {action}")

    async def discover_update(
        self,
        interface: MaaFWInterface | dict[str, Any],
        *,
        current_version: str | None = None,
        project_path: str | Path | None = None,
        source_config: dict[str, Any] | None = None,
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
    ) -> MaaFWProjectUpdateDiscovery | None:
        effective_source_config = dict(source_config or {})
        if project_path is not None and not str(
            effective_source_config.get("project_shell_hint") or ""
        ).strip():
            shell_hint = await asyncio.to_thread(
                detect_maafw_project_shell_hint,
                Path(project_path).resolve(),
            )
            if shell_hint:
                effective_source_config["project_shell_hint"] = shell_hint
        return await discover_maafw_project_update(
            self._coerce_interface(interface),
            current_version=current_version,
            source_config=effective_source_config,
            proxy=proxy,
            send_log=send_log,
        )

    async def check_update(
        self,
        interface: MaaFWInterface | dict[str, Any],
        *,
        current_version: str | None = None,
        source_config: dict[str, Any] | None = None,
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
    ) -> MaaFWProjectUpdateCandidate | None:
        return await check_maafw_project_update(
            self._coerce_interface(interface),
            current_version=current_version,
            source_config=source_config,
            proxy=proxy,
            send_log=send_log,
        )

    async def apply_update(
        self,
        project_path: str | Path,
        candidate: MaaFWProjectUpdateCandidate | Mapping[str, Any],
        *,
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
        progress: Any = None,
        post_validate: Any = None,
        project_lock_already_held: bool = False,
    ) -> dict[str, Any]:
        return await apply_maafw_project_update(
            Path(project_path).resolve(),
            self._coerce_candidate(candidate),
            proxy=proxy,
            send_log=send_log,
            progress=progress,
            post_validate=post_validate,
            project_lock_already_held=project_lock_already_held,
        )

    async def download_package(
        self,
        download_root: str | Path,
        candidate: MaaFWProjectUpdateCandidate | Mapping[str, Any],
        *,
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
        max_download_bytes: int = DOWNLOAD_MAX_BYTES,
        progress: Any = None,
    ) -> dict[str, Any]:
        """Download a validated ZIP for an immutable-store consumer."""

        downloaded = await download_maafw_project_package(
            Path(download_root).resolve(),
            self._coerce_candidate(candidate),
            proxy=proxy,
            send_log=send_log,
            max_download_bytes=max_download_bytes,
            progress=progress,
        )
        return self._downloaded_package_dict(downloaded)

    async def release_download_package(
        self,
        download_root: str | Path,
        package: MaaFWDownloadedProjectPackage | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Safely release one archive previously returned by download_package."""

        downloaded = self._coerce_downloaded_package(package)
        return await release_maafw_project_package(
            Path(download_root),
            downloaded.path,
            downloaded.sha256,
        )

    async def update_if_needed(
        self,
        project_path: str | Path,
        interface: MaaFWInterface | dict[str, Any],
        *,
        mirror_cdk: str = "",
        channel: str = "stable",
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
        source_config: dict[str, Any] | None = None,
        progress: Any = None,
        post_validate: Any = None,
        project_lock_already_held: bool = False,
    ) -> MaaFWProjectUpdateResult:
        return await update_maafw_project_if_needed(
            Path(project_path).resolve(),
            self._coerce_interface(interface),
            mirror_cdk=mirror_cdk,
            channel=channel,
            proxy=proxy,
            send_log=send_log,
            source_config=source_config,
            progress=progress,
            post_validate=post_validate,
            project_lock_already_held=project_lock_already_held,
        )

    @staticmethod
    def _coerce_candidate(
        candidate: MaaFWProjectUpdateCandidate | Mapping[str, Any],
    ) -> MaaFWProjectUpdateCandidate:
        if isinstance(candidate, MaaFWProjectUpdateCandidate):
            return candidate
        if hasattr(candidate, "model_dump"):
            data = candidate.model_dump(mode="json", by_alias=True)
        elif isinstance(candidate, Mapping):
            data = dict(candidate)
        else:
            raise MaaFWProjectUpdateError(
                "MaaFW update candidate must be a JSON object or stable DTO"
            )

        source = str(data.get("source") or "").strip()
        version = str(data.get("version") or "").strip()
        if not source or not version:
            raise MaaFWProjectUpdateError(
                "MaaFW update candidate is missing source or version"
            )
        return MaaFWProjectUpdateCandidate(
            source=source,
            version=version,
            download_url=str(
                data.get("download_url") or data.get("downloadUrl") or ""
            ).strip()
            or None,
            sha256=str(data.get("sha256") or "").strip() or None,
            artifact_id=str(data.get("artifact_id") or data.get("artifactId") or "").strip() or None,
            package_type=str(data.get("package_type") or data.get("packageType") or "").strip() or None,
            from_version=str(data.get("from_version") or data.get("fromVersion") or "").strip() or None,
            to_version=str(data.get("to_version") or data.get("toVersion") or "").strip() or None,
            size=_optional_int(data.get("size")),
            etag=str(data.get("etag") or "").strip() or None,
            last_modified=str(data.get("last_modified") or data.get("lastModified") or "").strip() or None,
            range_supported=data.get("range_supported", data.get("rangeSupported")),
            plan_id=str(data.get("plan_id") or data.get("planId") or "").strip() or None,
            project_fingerprint=str(
                data.get("project_fingerprint") or data.get("projectFingerprint") or ""
            ).strip()
            or None,
        )

    @staticmethod
    def _downloaded_package_dict(
        package: MaaFWDownloadedProjectPackage,
    ) -> dict[str, Any]:
        return {
            "source": package.source,
            "version": package.version,
            "path": package.path,
            "size": package.size,
            "sha256": package.sha256,
            "artifactId": package.artifact_id,
            "resumedFrom": package.resumed_from,
            "totalBytes": package.total_bytes,
            "etag": package.etag,
            "lastModified": package.last_modified,
            "rangeSupported": package.range_supported,
            "operationId": package.operation_id,
            "planId": package.plan_id,
        }

    @staticmethod
    def _coerce_downloaded_package(
        package: MaaFWDownloadedProjectPackage | Mapping[str, Any],
    ) -> MaaFWDownloadedProjectPackage:
        if isinstance(package, MaaFWDownloadedProjectPackage):
            return package
        if hasattr(package, "model_dump"):
            data = package.model_dump(mode="json", by_alias=True)
        elif isinstance(package, Mapping):
            data = dict(package)
        else:
            raise MaaFWProjectUpdateError(
                "MaaFW downloaded package must be a JSON object or stable DTO"
            )
        path = str(data.get("path") or "").strip()
        sha256 = str(data.get("sha256") or "").strip()
        if not path or not sha256:
            raise MaaFWProjectUpdateError(
                "MaaFW downloaded package is missing path or sha256"
            )
        try:
            size = int(data.get("size") or 0)
        except (TypeError, ValueError) as exc:
            raise MaaFWProjectUpdateError(
                "MaaFW downloaded package has an invalid size"
            ) from exc
        return MaaFWDownloadedProjectPackage(
            source=str(data.get("source") or "").strip(),
            version=str(data.get("version") or "").strip(),
            path=path,
            size=size,
            sha256=sha256,
            artifact_id=str(data.get("artifact_id") or data.get("artifactId") or "").strip() or None,
            resumed_from=_optional_int(data.get("resumed_from", data.get("resumedFrom"))) or 0,
            total_bytes=_optional_int(data.get("total_bytes", data.get("totalBytes"))),
            etag=str(data.get("etag") or "").strip() or None,
            last_modified=str(data.get("last_modified") or data.get("lastModified") or "").strip() or None,
            range_supported=data.get("range_supported", data.get("rangeSupported")),
            operation_id=str(data.get("operation_id") or data.get("operationId") or "").strip() or None,
            plan_id=str(data.get("plan_id") or data.get("planId") or "").strip() or None,
        )

    @staticmethod
    def _coerce_interface(interface: MaaFWInterface | dict[str, Any]) -> MaaFWInterface:
        if isinstance(interface, MaaFWInterface):
            return interface
        if hasattr(interface, "model_dump"):
            return MaaFWInterface.model_validate(
                interface.model_dump(mode="json", by_alias=True)
            )
        return MaaFWInterface.model_validate(interface)


def _optional_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
