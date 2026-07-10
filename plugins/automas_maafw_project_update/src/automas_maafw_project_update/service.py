from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from automas_maafw_interface.models import MaaFWInterface

from .updater import (
    MaaFWProjectUpdateCandidate,
    MaaFWProjectUpdateResult,
    MaaFWUpdateProviderInfo,
    apply_maafw_project_update,
    check_maafw_project_update,
    list_update_providers,
    update_maafw_project_if_needed,
)


class MaaFWProjectUpdateService:
    """maafw.project_update.v1 service."""

    def list_providers(self) -> list[MaaFWUpdateProviderInfo]:
        return list_update_providers()

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
        candidate: MaaFWProjectUpdateCandidate,
        *,
        proxy: httpx.Proxy | None = None,
        send_log: Any = None,
    ) -> None:
        await apply_maafw_project_update(
            Path(project_path).resolve(),
            candidate,
            proxy=proxy,
            send_log=send_log,
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
    ) -> MaaFWProjectUpdateResult:
        return await update_maafw_project_if_needed(
            Path(project_path).resolve(),
            self._coerce_interface(interface),
            mirror_cdk=mirror_cdk,
            channel=channel,
            proxy=proxy,
            send_log=send_log,
            source_config=source_config,
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
