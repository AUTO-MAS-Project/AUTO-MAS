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
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""旧 Manifest API 的兼容入口；新代码使用 descriptor 与 parser。"""

from __future__ import annotations

import json
from pathlib import Path

from .descriptor import (
    OK_ADAPTER_API_VERSION,
    OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION,
    OK_PROJECT_MANIFEST_SCHEMA_VERSION,
    PROTOCOL_FRAMEWORK_CLI,
    PROTOCOL_LEGACY_EXE,
    PROTOCOL_MAIN_SCRIPT,
    OkProjectCapabilities,
    OkProjectCapability,
    OkProjectDescriptor,
    OkProjectDiagnostic,
    OkProjectInspectError,
    OkProjectManifest,
    OkProjectMetadataSource,
    OkTaskDescriptor,
    OkTaskManifest,
)
from .parser import ProjectParser


def inspect_ok_project(
    root_path: str | Path,
    *,
    python_executable: str | Path | None = None,
) -> OkProjectDescriptor:
    """静态解析 ok-script 项目，不导入项目模块或启动进程。"""

    return ProjectParser(
        root_path,
        python_executable=python_executable,
    ).parse()


def save_manifest(descriptor: OkProjectDescriptor, path: Path) -> None:
    """以 descriptor v2 契约原子保存项目解析结果。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(descriptor.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_manifest(path: Path) -> OkProjectDescriptor:
    """读取 descriptor v2 或兼容迁移旧 Manifest v1。"""

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OkProjectInspectError(f"项目 descriptor 读取失败: {exc}") from exc
    if not isinstance(data, dict):
        raise OkProjectInspectError("项目 descriptor 顶层必须是对象")
    return OkProjectDescriptor.from_dict(data)


__all__ = [
    "OK_ADAPTER_API_VERSION",
    "OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION",
    "OK_PROJECT_MANIFEST_SCHEMA_VERSION",
    "PROTOCOL_FRAMEWORK_CLI",
    "PROTOCOL_LEGACY_EXE",
    "PROTOCOL_MAIN_SCRIPT",
    "OkProjectCapabilities",
    "OkProjectCapability",
    "OkProjectDescriptor",
    "OkProjectDiagnostic",
    "OkProjectInspectError",
    "OkProjectManifest",
    "OkProjectMetadataSource",
    "OkTaskDescriptor",
    "OkTaskManifest",
    "ProjectParser",
    "inspect_ok_project",
    "load_manifest",
    "save_manifest",
]
