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

"""ok-script 项目 descriptor、配置存储与控制台运行壳。"""

from .descriptor import (
    OkProjectCapabilities,
    OkProjectCapability,
    OkProjectDescriptor,
    OkProjectDiagnostic,
    OkProjectManifest,
    OkProjectMetadataSource,
    OkTaskDescriptor,
    OkTaskManifest,
)
from .manifest import inspect_ok_project, load_manifest, save_manifest
from .parser import ProjectParser
from .runtime import OkConfigStore, OkShellRunner, OkShellRuntimeError

__all__ = [
    "OkConfigStore",
    "OkProjectCapabilities",
    "OkProjectCapability",
    "OkProjectDescriptor",
    "OkProjectDiagnostic",
    "OkProjectManifest",
    "OkProjectMetadataSource",
    "OkShellRunner",
    "OkShellRuntimeError",
    "OkTaskDescriptor",
    "OkTaskManifest",
    "ProjectParser",
    "inspect_ok_project",
    "load_manifest",
    "save_manifest",
]
