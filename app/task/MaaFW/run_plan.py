#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import hashlib
import json
import os
from importlib import metadata
from pathlib import Path
from typing import Any

import json5
from pydantic import BaseModel, ConfigDict, Field

try:
    from .interface_models import (
        MaaFWAgent,
        MaaFWController,
        MaaFWInterface,
        MaaFWResource,
        MaaFWTask,
        MaaFWTaskOptionsByTask,
    )
    from .pipeline_override import MaaFWPipelineOverrideBuilder
    from .task_config import (
        MaaFWTaskPresetSnapshot,
        build_interface_preset_snapshot,
        normalize_snapshot,
        normalize_task_execution_payload,
    )
except ImportError:
    from interface_models import (  # type: ignore[no-redef]
        MaaFWAgent,
        MaaFWController,
        MaaFWInterface,
        MaaFWResource,
        MaaFWTask,
        MaaFWTaskOptionsByTask,
    )
    from pipeline_override import MaaFWPipelineOverrideBuilder  # type: ignore[no-redef]
    from task_config import (  # type: ignore[no-redef]
        MaaFWTaskPresetSnapshot,
        build_interface_preset_snapshot,
        normalize_snapshot,
        normalize_task_execution_payload,
    )


PI_INTERFACE_VERSION = "v2.5.0"
PI_CLIENT_LANGUAGE = "zh_cn"
PI_CLIENT_NAME = "AUTO-MAS"
MAAFW_DIRECT_CONTROLLER_TYPES = {"Adb", "Win32"}


class MaaFWRunPlanError(ValueError):
    """Raised when a MaaFW project cannot be converted into a runnable plan."""


class MaaFWResolvedPath(BaseModel):
    raw: str
    resolved: str
    exists: bool
    isFile: bool = False
    isDir: bool = False


class MaaFWAgentCommandPlan(BaseModel):
    childExec: str
    executable: str
    executableExists: bool | None = None
    fallbackReason: str | None = None
    # agent 运行时类型：embedded=宿主进程内注册；project_python=项目自带 Python；project_binary=项目自带可执行文件；isolated_venv=项目专属隔离 venv；external=用户自备
    runtimeKind: str | None = None
    # 隔离 venv 路径，仅 runtimeKind == "isolated_venv" 时有值
    isolatedVenvPath: str | None = None
    childArgs: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    cwd: str
    identifier: str | None = None
    embedded: bool = False


class MaaFWResourceBundlePlan(BaseModel):
    name: str
    label: str | None = None
    paths: list[MaaFWResolvedPath] = Field(default_factory=list)
    attachedPaths: list[MaaFWResolvedPath] = Field(default_factory=list)


class MaaFWTaskRunPlan(BaseModel):
    name: str
    label: str | None = None
    entry: str
    options: dict[str, Any] = Field(default_factory=dict)
    pipelineOverride: dict[str, Any] = Field(default_factory=dict)


class MaaFWSkippedTaskPlan(BaseModel):
    name: str
    label: str | None = None
    entry: str | None = None
    reason: str


class MaaFWRunPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str
    projectName: str
    projectLabel: str | None = None
    controllerName: str
    controllerType: str
    resourceName: str
    resource: MaaFWResourceBundlePlan
    agents: list[MaaFWAgentCommandPlan] = Field(default_factory=list)
    piEnv: dict[str, str] = Field(default_factory=dict)
    tasks: list[MaaFWTaskRunPlan] = Field(default_factory=list)
    skippedTasks: list[MaaFWSkippedTaskPlan] = Field(default_factory=list)


def build_maafw_run_plan(
    base_dir: str | Path,
    interface_model: MaaFWInterface,
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
    selected_preset: str | None = None,
    task_snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None = None,
    task_names: list[str] | None = None,
    task_options: dict[str, Any] | None = None,
) -> MaaFWRunPlan:
    resolved_base_dir = Path(base_dir).resolve()
    controller = _select_controller(interface_model, controller_name)
    resource = _select_resource(interface_model, resource_name, controller)
    selected_task_names, selected_task_options = _select_tasks(
        interface_model,
        controller_name=controller.name,
        resource_name=resource.name,
        selected_preset=selected_preset,
        task_snapshot=task_snapshot,
        task_names=task_names,
        task_options=task_options,
    )
    task_map = {task.name: task for task in interface_model.task}
    controller_names = {controller.name}
    pipeline_builder = MaaFWPipelineOverrideBuilder(
        interface_model,
        controller_names=controller_names,
        resource_name=resource.name,
    )

    runnable_tasks: list[MaaFWTaskRunPlan] = []
    skipped_tasks: list[MaaFWSkippedTaskPlan] = []
    for task_name in selected_task_names:
        task = task_map.get(task_name)
        if task is None:
            skipped_tasks.append(
                MaaFWSkippedTaskPlan(
                    name=task_name,
                    reason="任务不存在",
                )
            )
            continue

        compatible, reason = _check_task_compatible(
            task,
            controller_names=controller_names,
            resource_name=resource.name,
        )
        if not compatible:
            skipped_tasks.append(
                MaaFWSkippedTaskPlan(
                    name=task.name,
                    label=task.label,
                    entry=task.entry,
                    reason=reason,
                )
            )
            continue

        options = selected_task_options.get(task.name, {})
        runnable_tasks.append(
            MaaFWTaskRunPlan(
                name=task.name,
                label=task.label,
                entry=task.entry,
                options=options,
                pipelineOverride=pipeline_builder.build_task_pipeline_override(
                    task.name,
                    options,
                ),
            )
        )

    if not runnable_tasks:
        raise MaaFWRunPlanError("当前 controller/resource 下没有可执行任务")

    pi_env = _build_pi_env(resolved_base_dir, interface_model, controller, resource)
    return MaaFWRunPlan(
        path=str(resolved_base_dir),
        projectName=interface_model.name,
        projectLabel=interface_model.label,
        controllerName=controller.name,
        controllerType=controller.type,
        resourceName=resource.name,
        resource=_build_resource_bundle_plan(
            resolved_base_dir,
            resource,
            controller,
        ),
        agents=_build_agent_command_plans(
            resolved_base_dir,
            interface_model.agent,
        ),
        piEnv=pi_env,
        tasks=runnable_tasks,
        skippedTasks=skipped_tasks,
    )


def _select_controller(
    interface_model: MaaFWInterface,
    controller_name: str | None,
) -> MaaFWController:
    if controller_name:
        controller = next(
            (
                item
                for item in interface_model.controller
                if item.name == controller_name
            ),
            None,
        )
        if controller is None:
            raise MaaFWRunPlanError(f"未找到 controller: {controller_name}")
        _ensure_direct_controller(controller)
        return controller

    if not interface_model.controller:
        raise MaaFWRunPlanError("interface 未声明 controller")
    controller = next(
        (
            item
            for item in interface_model.controller
            if item.type in MAAFW_DIRECT_CONTROLLER_TYPES
        ),
        None,
    )
    if controller is None:
        declared_types = ", ".join(
            f"{item.name}({item.type})" for item in interface_model.controller
        )
        raise MaaFWRunPlanError(
            "AUTO-MAS MaaFW Direct currently supports only Adb/Win32 "
            f"controllers; use the project UI for: {declared_types}"
        )
    return controller


def _ensure_direct_controller(controller: MaaFWController) -> None:
    if controller.type in MAAFW_DIRECT_CONTROLLER_TYPES:
        return

    raise MaaFWRunPlanError(
        "AUTO-MAS MaaFW Direct currently supports only Adb/Win32 "
        f"controllers; use the project UI for {controller.name}({controller.type})"
    )


def _select_resource(
    interface_model: MaaFWInterface,
    resource_name: str | None,
    controller: MaaFWController,
) -> MaaFWResource:
    if resource_name:
        resource = next(
            (
                item
                for item in interface_model.resource
                if item.name == resource_name
            ),
            None,
        )
        if resource is None:
            raise MaaFWRunPlanError(f"未找到 resource: {resource_name}")
        if resource.controller and controller.name not in resource.controller:
            raise MaaFWRunPlanError(
                f"resource {resource.name} 不支持 controller {controller.name}"
            )
        return resource

    for resource in interface_model.resource:
        if not resource.controller or controller.name in resource.controller:
            return resource

    if not interface_model.resource:
        raise MaaFWRunPlanError("interface 未声明 resource")
    raise MaaFWRunPlanError(f"没有适用于 controller {controller.name} 的 resource")


def _select_tasks(
    interface_model: MaaFWInterface,
    *,
    controller_name: str,
    resource_name: str,
    selected_preset: str | None,
    task_snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
    task_names: list[str] | None,
    task_options: dict[str, Any] | None,
) -> tuple[list[str], MaaFWTaskOptionsByTask]:
    if task_names is not None:
        return normalize_task_execution_payload(
            task_names,
            task_options,
            interface_model,
            controller_name=controller_name,
            resource_name=resource_name,
        )

    snapshot = _resolve_snapshot(
        interface_model,
        selected_preset=selected_preset,
        task_snapshot=task_snapshot,
    )
    selected_names = [
        task_name
        for task_name in snapshot.taskOrder
        if snapshot.taskChecked.get(task_name, False)
    ]
    return normalize_task_execution_payload(
        selected_names,
        snapshot.taskOptions,
        interface_model,
        controller_name=controller_name,
        resource_name=resource_name,
    )


def _resolve_snapshot(
    interface_model: MaaFWInterface,
    *,
    selected_preset: str | None,
    task_snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
) -> MaaFWTaskPresetSnapshot:
    if task_snapshot is not None:
        return normalize_snapshot(task_snapshot, interface_model)

    if selected_preset:
        preset = next(
            (
                item
                for item in interface_model.preset
                if item.name == selected_preset
            ),
            None,
        )
        if preset is None:
            raise MaaFWRunPlanError(f"未找到 preset: {selected_preset}")
        return normalize_snapshot(
            build_interface_preset_snapshot(interface_model, preset),
            interface_model,
        )

    if interface_model.preset:
        return normalize_snapshot(
            build_interface_preset_snapshot(interface_model, interface_model.preset[0]),
            interface_model,
        )

    return normalize_snapshot(
        {
            "taskOrder": [task.name for task in interface_model.task],
            "taskChecked": {
                task.name: bool(task.default_check)
                for task in interface_model.task
            },
            "taskOptions": {},
        },
        interface_model,
    )


def _check_task_compatible(
    task: MaaFWTask,
    *,
    controller_names: set[str],
    resource_name: str,
) -> tuple[bool, str]:
    if task.controller and not controller_names.intersection(task.controller):
        return False, f"当前控制器不受支持，支持: {', '.join(task.controller)}"

    if task.resource and resource_name not in task.resource:
        return False, f"当前资源不受支持，支持: {', '.join(task.resource)}"

    return True, ""


def _build_resource_bundle_plan(
    base_dir: Path,
    resource: MaaFWResource,
    controller: MaaFWController,
) -> MaaFWResourceBundlePlan:
    return MaaFWResourceBundlePlan(
        name=resource.name,
        label=resource.label,
        paths=[
            _resolve_project_path(base_dir, item)
            for item in resource.path
        ],
        attachedPaths=[
            _resolve_project_path(base_dir, item)
            for item in controller.attach_resource_path or []
        ],
    )


def _build_agent_command_plans(
    base_dir: Path,
    raw_agent: MaaFWAgent | list[MaaFWAgent] | None,
) -> list[MaaFWAgentCommandPlan]:
    agent_configs = _get_agent_configs(raw_agent)
    return [
        _build_agent_command_plan(base_dir, agent_config)
        for agent_config in agent_configs
    ]


def build_maafw_agent_command_plans(
    base_dir: str | Path,
    raw_agent: MaaFWAgent | list[MaaFWAgent] | None,
) -> list[MaaFWAgentCommandPlan]:
    """Build agent command plans without requiring task/resource selection."""

    return _build_agent_command_plans(Path(base_dir).resolve(), raw_agent)


def _get_agent_configs(
    raw_agent: MaaFWAgent | list[MaaFWAgent] | None,
) -> list[MaaFWAgent]:
    if raw_agent is None:
        return []
    if isinstance(raw_agent, list):
        return raw_agent
    return [raw_agent]


def _build_agent_command_plan(
    base_dir: Path,
    agent_config: MaaFWAgent,
) -> MaaFWAgentCommandPlan:
    child_args = [
        _replace_project_dir(arg, base_dir)
        for arg in agent_config.child_args or []
    ]
    embedded_requested = agent_config.embedded is True
    executable = _resolve_executable(base_dir, agent_config.child_exec)
    if (
        embedded_requested
        and executable["runtime_kind"] != "project_binary"
        and not _has_python_entry_arg(child_args)
    ):
        child_args = ["-u", str((base_dir / "agent" / "main.py").resolve())]

    fallback_reason = executable["fallback_reason"]
    if embedded_requested:
        isolation_reason = (
            "embedded agent 已切换为隔离子进程，避免污染 AUTO-MAS 主进程 Python 环境"
        )
        fallback_reason = (
            f"{isolation_reason}; {fallback_reason}"
            if fallback_reason
            else isolation_reason
        )

    command = [executable["command"]] + child_args + ["<socket_id>"]
    return MaaFWAgentCommandPlan(
        childExec=agent_config.child_exec,
        executable=executable["command"],
        executableExists=executable["exists"],
        fallbackReason=fallback_reason,
        runtimeKind=executable["runtime_kind"],
        isolatedVenvPath=executable["isolated_venv_path"],
        childArgs=child_args,
        command=command,
        cwd=str(base_dir),
        identifier=agent_config.identifier,
        embedded=False,
    )


def _has_python_entry_arg(child_args: list[str]) -> bool:
    return any(str(arg).lower().endswith(".py") for arg in child_args)


def _resolve_executable(base_dir: Path, child_exec: str) -> dict[str, Any]:
    replaced = _replace_project_dir(child_exec, base_dir)
    if not _looks_like_project_path(replaced):
        return {
            "command": replaced,
            "exists": None,
            "fallback_reason": None,
            "runtime_kind": "external",
            "isolated_venv_path": None,
        }

    resolved_path = _resolve_project_executable_path(base_dir, replaced)
    if resolved_path.exists:
        return {
            "command": resolved_path.resolved,
            "exists": True,
            "fallback_reason": None,
            "runtime_kind": _classify_existing_project_executable(resolved_path.resolved),
            "isolated_venv_path": None,
        }

    # 项目声明的解释器不存在：绝不回退到 AUTO-MAS 自身 Python，避免环境污染
    if _is_bundled_python_pattern(child_exec, base_dir):
        venv_path = _compute_isolated_venv_path(base_dir)
        venv_python = _venv_python_exe(venv_path)
        return {
            "command": str(venv_python),
            "exists": venv_python.exists(),
            "fallback_reason": (
                f"项目声明的解释器不存在: {resolved_path.resolved}，"
                f"将使用该项目专属隔离 venv: {venv_path}"
            ),
            "runtime_kind": "isolated_venv",
            "isolated_venv_path": str(venv_path),
        }

    # 非 bundled-python 模式的缺失路径，不自动创建 venv，直接标记缺失
    return {
        "command": resolved_path.resolved,
        "exists": False,
        "fallback_reason": f"声明的可执行文件不存在: {resolved_path.resolved}",
        "runtime_kind": "external",
        "isolated_venv_path": None,
    }


def _resolve_project_executable_path(base_dir: Path, raw_path: str) -> MaaFWResolvedPath:
    resolved_path = _resolve_project_path(base_dir, raw_path)
    if resolved_path.exists:
        return resolved_path

    if os.name != "nt":
        return resolved_path

    candidate = Path(resolved_path.resolved)
    if candidate.suffix:
        return resolved_path

    exe_candidate = candidate.with_suffix(".exe")
    if not _is_within_base_dir(exe_candidate.resolve(), base_dir):
        return resolved_path
    if not exe_candidate.is_file():
        return resolved_path

    return MaaFWResolvedPath(
        raw=raw_path,
        resolved=str(exe_candidate.resolve()),
        exists=True,
        isFile=True,
        isDir=False,
    )


def _classify_existing_project_executable(resolved_path: str) -> str:
    executable_path = Path(resolved_path)
    if executable_path.name.lower() in {"python", "python.exe", "pythonw", "pythonw.exe"}:
        return "project_python"
    return "project_binary"


def _is_bundled_python_pattern(child_exec: str, base_dir: Path) -> bool:
    """判断 child_exec 是否为 MaaFW 项目自带的 python/python.exe 模式。"""
    normalized = child_exec.replace("\\", "/").lower()
    if not normalized.endswith("python/python.exe"):
        return False
    return (base_dir / "agent" / "main.py").exists()


def _compute_isolated_venv_path(base_dir: Path) -> Path:
    """根据项目路径 hash 计算专属隔离 venv 路径，确保不同项目互不混用。

    venv 存放在 AUTO-MAS 工作目录的 config 下，既不污染用户 MaaFW release 目录，
    也不触碰 AUTO-MAS 自身 .venv。
    """
    key = str(base_dir.resolve())
    if os.name == "nt":
        key = key.lower()
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return Path.cwd() / "config" / "maafw_agent_venvs" / f"maafw_venv_{digest}"


def _venv_python_exe(venv_path: Path) -> Path:
    """隔离 venv 的 Python 解释器路径。"""
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _replace_project_dir(value: str, base_dir: Path) -> str:
    return value.replace("{PROJECT_DIR}", str(base_dir))


def _looks_like_project_path(value: str) -> bool:
    if value.startswith("."):
        return True
    if "/" in value or "\\" in value:
        return True
    return Path(value).is_absolute()


def _resolve_project_path(base_dir: Path, raw_path: str) -> MaaFWResolvedPath:
    replaced = _replace_project_dir(raw_path, base_dir)
    candidate = Path(replaced)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    resolved_path = candidate.resolve()

    if not _is_within_base_dir(resolved_path, base_dir):
        raise MaaFWRunPlanError(f"路径越界，禁止访问项目目录之外的资源: {raw_path}")

    return MaaFWResolvedPath(
        raw=raw_path,
        resolved=str(resolved_path),
        exists=resolved_path.exists(),
        isFile=resolved_path.is_file(),
        isDir=resolved_path.is_dir(),
    )


def _is_within_base_dir(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _build_pi_env(
    base_dir: Path,
    interface_model: MaaFWInterface,
    controller: MaaFWController,
    resource: MaaFWResource,
) -> dict[str, str]:
    controller_payload = _resolve_i18n_payload(
        controller.model_dump(mode="json", exclude_none=True),
        base_dir,
        interface_model,
    )
    resource_payload = _resolve_i18n_payload(
        resource.model_dump(mode="json", exclude_none=True),
        base_dir,
        interface_model,
    )
    return {
        "PI_INTERFACE_VERSION": PI_INTERFACE_VERSION,
        "PI_CLIENT_NAME": PI_CLIENT_NAME,
        "PI_CLIENT_VERSION": _load_client_version(),
        "PI_CLIENT_LANGUAGE": PI_CLIENT_LANGUAGE,
        "PI_CLIENT_MAAFW_VERSION": _load_maafw_version(),
        "PI_VERSION": interface_model.version or "",
        "PI_CONTROLLER": json.dumps(
            controller_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "PI_RESOURCE": json.dumps(
            resource_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _load_client_version() -> str:
    version_path = Path.cwd() / "res" / "version.json"
    try:
        with version_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        version = data.get("version")
        return version if isinstance(version, str) else ""
    except Exception:
        return ""


def _load_maafw_version() -> str:
    try:
        return f"v{metadata.version('maafw')}"
    except Exception:
        return ""


def _resolve_i18n_payload(
    payload: Any,
    base_dir: Path,
    interface_model: MaaFWInterface,
) -> Any:
    mapping = _load_i18n_mapping(base_dir, interface_model)
    return _resolve_i18n_value(payload, mapping)


def _load_i18n_mapping(
    base_dir: Path,
    interface_model: MaaFWInterface,
) -> dict[str, Any]:
    if not interface_model.languages:
        return {}

    language_file = interface_model.languages.get(PI_CLIENT_LANGUAGE)
    if not isinstance(language_file, str) or not language_file.strip():
        return {}

    language_path = _resolve_project_path(base_dir, language_file)
    if not language_path.exists or not language_path.isFile:
        return {}

    try:
        with Path(language_path.resolved).open("r", encoding="utf-8") as file:
            data = json5.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_i18n_value(value: Any, mapping: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {
            key: _resolve_i18n_value(item, mapping)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_i18n_value(item, mapping)
            for item in value
        ]
    if isinstance(value, str) and value.startswith("$"):
        translated = _lookup_i18n_text(value, mapping)
        if translated is not None:
            return translated
    return value


def _lookup_i18n_text(key: str, mapping: dict[str, Any]) -> str | None:
    normalized_key = key[1:] if key.startswith("$") else key
    if not normalized_key:
        return None

    current: Any = mapping
    for part in normalized_key.split("."):
        if not isinstance(current, dict) or part not in current:
            current = None
            break
        current = current[part]
    if isinstance(current, str):
        return current

    flat_value = mapping.get(normalized_key)
    if isinstance(flat_value, str):
        return flat_value
    return None
