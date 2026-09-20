from __future__ import annotations

from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    MaaFWAgent,
    MaaFWInterface,
)

from .env import prepare_agent_envs
from .models import MaaFWAgentCommandPlan, MaaFWAgentEnvPrepareResult
from .planner import build_maafw_agent_command_plans


class MaaFWAgentEnvService:
    """maafw.agent_env.v1 service."""

    def classify(self, agent: MaaFWAgent | dict[str, Any]) -> str:
        plans = self.build_command_plans(".", agent)
        return plans[0].runtimeKind or "external" if plans else "external"

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

    def prepare_env(
        self,
        project_path: str | Path,
        interface_or_agent: MaaFWInterface
        | MaaFWAgent
        | dict[str, Any]
        | list[dict[str, Any]]
        | None,
        *,
        managed_env_root: str | Path | None = None,
        send_log: Any = None,
        bootstrap_python: str | None = None,
        install_dependencies: bool = True,
        progress: Any = None,
    ) -> MaaFWAgentEnvPrepareResult:
        plans = self.build_command_plans(
            project_path,
            interface_or_agent,
            managed_env_root=managed_env_root,
        )
        return prepare_agent_envs(
            project_path,
            plans,
            send_log=send_log,
            bootstrap_python=bootstrap_python,
            install_dependencies=install_dependencies,
            progress=progress,
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
