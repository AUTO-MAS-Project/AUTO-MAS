#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""宿主客户端版本号：三份账号流程建计划时传给 ``client_version``（写进 ``PI_CLIENT_VERSION``）。

以前由建计划的模块按自己的文件位置去找 ``res/version.json``，文件一挪目录就静默变成空串；
现在由宿主按 ``Config.resource_path`` 读同一个文件，读不到给空串（口径同原函数）。
"""

from __future__ import annotations

import json

from app.core import Config


def host_client_version() -> str:
    version_path = Config.resource_path / "version.json"
    try:
        data = json.loads(version_path.read_text(encoding="utf-8"))
        version = data.get("version")
        return version if isinstance(version, str) else ""
    except Exception:
        return ""
