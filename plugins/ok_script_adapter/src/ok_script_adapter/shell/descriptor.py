#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ok-script 项目解析结果的版本化数据契约。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION = 2
OK_ADAPTER_API_VERSION = 1

PROTOCOL_FRAMEWORK_CLI = "framework-cli"
PROTOCOL_MAIN_SCRIPT = "main-script"
PROTOCOL_LEGACY_EXE = "legacy-exe"


class OkProjectInspectError(ValueError):
    """ok-script 项目无法完成只读解析或 descriptor 迁移。"""


@dataclass(frozen=True, slots=True)
class OkProjectDiagnostic:
    """项目解析期间产生的一条可展示诊断。"""

    code: str
    level: str
    message: str
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {
            "code": self.code,
            "level": self.level,
            "message": self.message,
        }
        if self.path:
            data["path"] = self.path
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OkProjectDiagnostic":
        return cls(
            code=str(data.get("code") or "DESCRIPTOR_DIAGNOSTIC"),
            level=str(data.get("level") or "warning"),
            message=str(data.get("message") or "项目描述包含未说明的诊断"),
            path=str(data.get("path") or ""),
        )


@dataclass(frozen=True, slots=True)
class OkProjectCapability:
    """单项能力的可用性与验证状态。"""

    available: bool
    verified: bool
    source: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "verified": self.verified,
            "source": self.source,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(
        cls,
        data: object,
        *,
        default: "OkProjectCapability",
    ) -> "OkProjectCapability":
        if not isinstance(data, dict):
            return default
        return cls(
            available=bool(data.get("available", default.available)),
            verified=bool(data.get("verified", default.verified)),
            source=str(data.get("source") or default.source),
            reason=str(data.get("reason") or default.reason),
        )


@dataclass(frozen=True, slots=True)
class OkProjectCapabilities:
    """配置、任务和运行等项目能力集合。"""

    config: OkProjectCapability
    task: OkProjectCapability
    game_path: OkProjectCapability
    events: OkProjectCapability
    runtime: OkProjectCapability

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "task": self.task.to_dict(),
            "gamePath": self.game_path.to_dict(),
            "events": self.events.to_dict(),
            "runtime": self.runtime.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        data: object,
        *,
        default: "OkProjectCapabilities",
    ) -> "OkProjectCapabilities":
        if not isinstance(data, dict):
            return default
        return cls(
            config=OkProjectCapability.from_dict(
                data.get("config"),
                default=default.config,
            ),
            task=OkProjectCapability.from_dict(
                data.get("task") or data.get("tasks"),
                default=default.task,
            ),
            game_path=OkProjectCapability.from_dict(
                data.get("gamePath") or data.get("game_path"),
                default=default.game_path,
            ),
            events=OkProjectCapability.from_dict(
                data.get("events"),
                default=default.events,
            ),
            runtime=OkProjectCapability.from_dict(
                data.get("runtime"),
                default=default.runtime,
            ),
        )


@dataclass(frozen=True, slots=True)
class OkProjectMetadataSource:
    """参与 descriptor 生成的一个静态元数据文件。"""

    kind: str
    path: Path
    fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "fields": list(self.fields),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        root_path: Path,
    ) -> "OkProjectMetadataSource":
        fields = data.get("fields")
        return cls(
            kind=str(data.get("kind") or "unknown"),
            path=_path_value(data.get("path"), base=root_path) or root_path,
            fields=tuple(
                str(item)
                for item in fields
                if isinstance(item, str)
            )
            if isinstance(fields, list)
            else (),
        )


@dataclass(frozen=True, slots=True)
class OkTaskDescriptor:
    """单个一次性任务的稳定 selector 与 CLI 序号。"""

    selector: str
    index: int
    module: str = ""
    class_name: str = ""
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "index": self.index,
            "module": self.module,
            "className": self.class_name,
            "label": self.label or self.selector,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OkTaskDescriptor":
        return cls(
            selector=str(data.get("selector") or ""),
            index=int(data.get("index") or 0),
            module=str(data.get("module") or ""),
            class_name=str(data.get("className") or data.get("class_name") or ""),
            label=str(data.get("label") or ""),
        )


@dataclass(frozen=True, slots=True)
class OkProjectDescriptor:
    """解析器输出；运行器只消费该对象，不重新解释项目源码。"""

    root_path: Path
    working_dir: Path
    resource_name: str
    display_name: str
    project_version: str
    framework_requirement: str
    python_executable: Path | None
    executable: Path | None
    main_script: Path | None
    config_source: Path | None
    config_target: str
    config_folder: str
    config_dir: Path
    log_path: Path
    gui_title: str
    tasks: tuple[OkTaskDescriptor, ...]
    protocols: tuple[str, ...]
    default_protocol: str
    metadata_sources: tuple[OkProjectMetadataSource, ...]
    capabilities: OkProjectCapabilities
    diagnostics: tuple[OkProjectDiagnostic, ...]
    fingerprint: str
    schema_version: int = OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION
    adapter_api_version: int = OK_ADAPTER_API_VERSION

    def to_dict(self) -> dict[str, Any]:
        """序列化 v2 契约，同时保留 v1 扁平字段供旧消费者读取。"""

        identity = {
            "rootPath": str(self.root_path),
            "resourceName": self.resource_name,
            "displayName": self.display_name,
            "projectVersion": self.project_version,
            "fingerprint": self.fingerprint,
        }
        runtime = {
            "workingDirectory": str(self.working_dir),
            "pythonExecutable": (
                str(self.python_executable) if self.python_executable else None
            ),
            "executable": str(self.executable) if self.executable else None,
            "mainScript": str(self.main_script) if self.main_script else None,
            "protocols": list(self.protocols),
            "defaultProtocol": self.default_protocol,
        }
        config = {
            "source": str(self.config_source) if self.config_source else None,
            "target": self.config_target,
            "folder": self.config_folder,
            "directory": str(self.config_dir),
        }
        sources = [source.to_dict() for source in self.metadata_sources]
        diagnostics = [item.to_dict() for item in self.diagnostics]

        return {
            "schemaVersion": self.schema_version,
            "adapterApiVersion": self.adapter_api_version,
            "identity": identity,
            "sources": sources,
            "runtime": runtime,
            "config": config,
            "capabilities": self.capabilities.to_dict(),
            "diagnostics": diagnostics,
            "rootPath": str(self.root_path),
            "workingDirectory": str(self.working_dir),
            "resourceName": self.resource_name,
            "displayName": self.display_name,
            "projectVersion": self.project_version,
            "frameworkRequirement": self.framework_requirement,
            "pythonExecutable": runtime["pythonExecutable"],
            "executable": runtime["executable"],
            "mainScript": runtime["mainScript"],
            "configSource": config["source"],
            "configTarget": self.config_target,
            "configFolder": self.config_folder,
            "configDirectory": str(self.config_dir),
            "logPath": str(self.log_path),
            "guiTitle": self.gui_title,
            "tasks": [task.to_dict() for task in self.tasks],
            "protocols": list(self.protocols),
            "defaultProtocol": self.default_protocol,
            "metadataSources": sources,
            "fingerprint": self.fingerprint,
        }

    def with_runtime_verification(
        self,
        *,
        verified: bool,
        reason: str = "",
    ) -> "OkProjectDescriptor":
        """叠加 provider 的真实运行验证，不改变静态协议候选。"""

        runtime_verified = bool(
            verified and self.capabilities.runtime.available
        )
        runtime = replace(
            self.capabilities.runtime,
            verified=runtime_verified,
            reason=(
                reason
                if runtime_verified
                else reason or self.capabilities.runtime.reason
            ),
        )
        return replace(
            self,
            capabilities=replace(self.capabilities, runtime=runtime),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OkProjectDescriptor":
        """读取 v2 descriptor，并把 v1 Manifest 显式迁移为 v2。"""

        schema_version = int(data.get("schemaVersion") or 1)
        if schema_version not in (1, OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION):
            raise OkProjectInspectError(
                f"不支持的项目 descriptor 版本: {schema_version}"
            )

        identity = data.get("identity")
        identity_data = identity if isinstance(identity, dict) else {}
        runtime = data.get("runtime")
        runtime_data = runtime if isinstance(runtime, dict) else {}
        config = data.get("config")
        config_data = config if isinstance(config, dict) else {}

        root_path = _path_value(
            identity_data.get("rootPath") or data.get("rootPath")
        )
        if root_path is None or not root_path.is_dir():
            raise OkProjectInspectError(f"项目目录不存在: {root_path or ''}")

        working_dir = _path_value(
            runtime_data.get("workingDirectory")
            or data.get("workingDirectory"),
            base=root_path,
        ) or root_path
        config_dir = _path_value(
            config_data.get("directory") or data.get("configDirectory"),
            base=working_dir,
        ) or (working_dir / "configs").resolve()
        log_path = _path_value(
            data.get("logPath"),
            base=working_dir,
        ) or (working_dir / "logs" / "ok-script.log").resolve()

        tasks_data = data.get("tasks")
        tasks = tuple(
            OkTaskDescriptor.from_dict(item)
            for item in tasks_data
            if isinstance(item, dict)
        ) if isinstance(tasks_data, list) else ()

        protocols_data = runtime_data.get("protocols") or data.get("protocols")
        protocols = tuple(
            str(item)
            for item in protocols_data
            if isinstance(item, str)
        ) if isinstance(protocols_data, list) else ()

        config_target = str(
            config_data.get("target")
            or data.get("configTarget")
            or "src.config:config"
        )
        config_source = _path_value(
            config_data.get("source") or data.get("configSource"),
            base=working_dir,
        )
        if schema_version == 1 and config_source is None:
            config_source = _legacy_config_source(
                root_path=root_path,
                working_dir=working_dir,
                config_target=config_target,
            )

        config_folder = str(
            config_data.get("folder") or data.get("configFolder") or ""
        ).strip()
        if not config_folder:
            config_folder = _relative_folder(config_dir, working_dir)

        default_capabilities = _default_capabilities(
            config_source=config_source,
            config_dir=config_dir,
            tasks=tasks,
            protocols=protocols,
        )
        capabilities = OkProjectCapabilities.from_dict(
            data.get("capabilities"),
            default=default_capabilities,
        )

        sources_data = data.get("sources") or data.get("metadataSources")
        metadata_sources = tuple(
            OkProjectMetadataSource.from_dict(item, root_path=root_path)
            for item in sources_data
            if isinstance(item, dict)
        ) if isinstance(sources_data, list) else ()

        diagnostics_data = data.get("diagnostics")
        diagnostics = tuple(
            OkProjectDiagnostic.from_dict(item)
            for item in diagnostics_data
            if isinstance(item, dict)
        ) if isinstance(diagnostics_data, list) else ()
        if schema_version == 1:
            diagnostics = (
                *diagnostics,
                OkProjectDiagnostic(
                    code="DESCRIPTOR_V1_MIGRATED",
                    level="info",
                    message="已将 Manifest v1 兼容迁移为项目 descriptor v2",
                ),
            )

        return cls(
            root_path=root_path,
            working_dir=working_dir,
            resource_name=str(
                identity_data.get("resourceName")
                or data.get("resourceName")
                or ""
            ),
            display_name=str(
                identity_data.get("displayName")
                or data.get("displayName")
                or ""
            ),
            project_version=str(
                identity_data.get("projectVersion")
                or data.get("projectVersion")
                or ""
            ),
            framework_requirement=str(data.get("frameworkRequirement") or ""),
            python_executable=_path_value(
                runtime_data.get("pythonExecutable")
                or data.get("pythonExecutable"),
                base=root_path,
            ),
            executable=_path_value(
                runtime_data.get("executable") or data.get("executable"),
                base=root_path,
            ),
            main_script=_path_value(
                runtime_data.get("mainScript") or data.get("mainScript"),
                base=root_path,
            ),
            config_source=config_source,
            config_target=config_target,
            config_folder=config_folder,
            config_dir=config_dir,
            log_path=log_path,
            gui_title=str(data.get("guiTitle") or ""),
            tasks=tasks,
            protocols=protocols,
            default_protocol=str(
                runtime_data.get("defaultProtocol")
                or data.get("defaultProtocol")
                or (protocols[0] if protocols else "")
            ),
            metadata_sources=metadata_sources,
            capabilities=capabilities,
            diagnostics=diagnostics,
            fingerprint=str(
                identity_data.get("fingerprint")
                or data.get("fingerprint")
                or ""
            ),
            schema_version=OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION,
            adapter_api_version=int(
                data.get("adapterApiVersion") or OK_ADAPTER_API_VERSION
            ),
        )


def _path_value(value: object, *, base: Path | None = None) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path.resolve()


def _legacy_config_source(
    *,
    root_path: Path,
    working_dir: Path,
    config_target: str,
) -> Path | None:
    module_name = config_target.split(":", 1)[0].strip()
    if not module_name:
        return None
    relative_path = Path(*module_name.split(".")).with_suffix(".py")
    for base in (working_dir, root_path):
        candidate = (base / relative_path).resolve()
        if candidate.is_file():
            return candidate
    return None


def _relative_folder(config_dir: Path, working_dir: Path) -> str:
    try:
        relative = config_dir.relative_to(working_dir).as_posix()
    except ValueError:
        relative = config_dir.name
    return relative or "configs"


def _default_capabilities(
    *,
    config_source: Path | None,
    config_dir: Path,
    tasks: tuple[OkTaskDescriptor, ...],
    protocols: tuple[str, ...],
) -> OkProjectCapabilities:
    config_source_available = (
        config_source is not None and config_source.is_file()
    )
    config_available = config_source_available or config_dir.is_dir()
    task_available = bool(tasks)
    runtime_available = bool(protocols)
    return OkProjectCapabilities(
        config=OkProjectCapability(
            available=config_available,
            verified=config_available,
            source="config.py" if config_source_available else "json-directory",
            reason="" if config_available else "未找到配置源码或 JSON 配置目录",
        ),
        task=OkProjectCapability(
            available=task_available,
            verified=task_available,
            source="config.py:onetime_tasks" if task_available else "",
            reason="" if task_available else "未从项目配置中解析到一次性任务",
        ),
        game_path=OkProjectCapability(
            available=False,
            verified=False,
            reason="游戏路径角色需要 provider 明确声明",
        ),
        events=OkProjectCapability(
            available=False,
            verified=False,
            reason="结构化事件能力需要上游或 provider 明确声明",
        ),
        runtime=OkProjectCapability(
            available=runtime_available,
            verified=False,
            source=",".join(protocols),
            reason=(
                "仅探测到运行协议候选，尚未经过 provider 或真实运行验证"
                if runtime_available
                else "未探测到可用运行协议候选"
            ),
        ),
    )


# v1 名称保留为类型别名，旧调用方无需在本阶段同步改名。
OkProjectManifest = OkProjectDescriptor
OkTaskManifest = OkTaskDescriptor
OK_PROJECT_MANIFEST_SCHEMA_VERSION = OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION
