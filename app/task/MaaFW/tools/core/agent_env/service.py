from __future__ import annotations

from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.interface.models import (
    MaaFWAgent,
    MaaFWInterface,
)

from .models import MaaFWAgentCommandPlan
from .planner import build_maafw_agent_command_plans


class MaaFWAgentEnvService:
    """maafw.agent_env.v1 service."""

    def build_command_plans(
        self,
        project_path: str | Path,
        interface_or_agent: MaaFWInterface
        | MaaFWAgent
        | dict[str, Any]
        | list[dict[str, Any]]
        | None,
        *,
        managed_env_root: str | Path | None = None,
    ) -> list[MaaFWAgentCommandPlan]:
        raw_agent = self._extract_agent(interface_or_agent)
        return build_maafw_agent_command_plans(
            project_path,
            raw_agent,
            managed_env_root=managed_env_root,
        )

    @staticmethod
    def _extract_agent(
        value: MaaFWInterface
        | MaaFWAgent
        | dict[str, Any]
        | list[dict[str, Any]]
        | None,
    ) -> Any:
        if isinstance(value, MaaFWInterface):
            return value.agent
        if isinstance(value, MaaFWAgent):
            return value
        if isinstance(value, dict):
            if "interface_version" in value or "interfaceVersion" in value:
                return MaaFWInterface.model_validate(value).agent
            if "agent" in value:
                return value.get("agent")
            return value
        if hasattr(value, "model_dump"):
            return MaaFWInterface.model_validate(
                value.model_dump(mode="json", by_alias=True)
            ).agent
        if hasattr(value, "agent"):
            return getattr(value, "agent")
        return value
