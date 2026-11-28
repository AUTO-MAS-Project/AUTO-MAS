#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   This file is part of AUTO-MAS.
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#   Contact: DLmaster_361@163.com

"""宿主明确选择内置专项，构造当前宿主的三份能力索引。"""

from __future__ import annotations

from app.models.config import CLASS_BOOK
from app.task.registration import ScriptCapabilities, build_script_capabilities
from app.utils.common.startup_timing import startup_stage


def build_builtin_script_capabilities() -> ScriptCapabilities:
    """装配宿主当前内置的专项能力。"""
    with startup_stage("后端/专项注册导入/general.registration"):
        from app.task.general.registration import REGISTRATION as general
    with startup_stage("后端/专项注册导入/HSR.registration"):
        from app.task.HSR.registration import REGISTRATION as hsr
    with startup_stage("后端/专项注册导入/OkNte.registration"):
        from app.task.OkNte.registration import REGISTRATION as oknte
    with startup_stage("后端/专项注册导入/Okww.registration"):
        from app.task.Okww.registration import REGISTRATION as okww
    capabilities = build_script_capabilities(
        (
            okww,
            general,
            oknte,
            hsr,
        ),
        expected_types=CLASS_BOOK.values(),
    )
    return capabilities
