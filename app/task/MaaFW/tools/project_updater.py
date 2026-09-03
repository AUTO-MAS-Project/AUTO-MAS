#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright (C) 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MaaFW 项目更新的兼容导出层。

真正的实现位于核心包 ``core.automas_maafw_project_update``：Mirror 酱固定作为
版本权威，下载来源由核心包按 CDK 状态自动在 Mirror 酱 / GitHub 之间分流。
本模块仅保留同名再导出，供尚未迁移的旧导入路径使用；新代码请直接从核心包导入。
"""

from .core.automas_maafw_project_update import (
    DOWNLOAD_MAX_BYTES,
    MaaFWDownloadedProjectPackage,
    MaaFWProjectUpdateCandidate,
    MaaFWProjectUpdateDiscovery,
    MaaFWProjectUpdateError,
    MaaFWProjectUpdateResult,
    apply_maafw_project_update,
    detect_maafw_project_shell_hint,
    discover_maafw_project_update,
    download_maafw_project_package,
    update_maafw_project_if_needed,
)

__all__ = [
    "DOWNLOAD_MAX_BYTES",
    "MaaFWDownloadedProjectPackage",
    "MaaFWProjectUpdateCandidate",
    "MaaFWProjectUpdateDiscovery",
    "MaaFWProjectUpdateError",
    "MaaFWProjectUpdateResult",
    "apply_maafw_project_update",
    "detect_maafw_project_shell_hint",
    "discover_maafw_project_update",
    "download_maafw_project_package",
    "update_maafw_project_if_needed",
]
