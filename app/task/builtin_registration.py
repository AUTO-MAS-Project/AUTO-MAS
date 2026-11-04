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

from dataclasses import replace
from typing import TYPE_CHECKING

from app.models.config import CLASS_BOOK
from app.task.registration import ScriptCapabilities, build_script_capabilities
from app.utils.common.startup_timing import startup_stage

if TYPE_CHECKING:
    with startup_stage("后端/专项注册导入/MaaEnd.api_service"):
        from app.task.MaaEnd.api_service import MaaEndConfigService
    with startup_stage("后端/专项注册导入/ZzzOd.recovery"):
        from app.task.ZzzOd.recovery import ZzzOdRecovery


def build_builtin_script_capabilities(
    *, maaend: MaaEndConfigService, zzzod: ZzzOdRecovery
) -> ScriptCapabilities:
    """绑定服务只属于本次装配；模块静态声明不保存 Config 或服务实例。"""
    with startup_stage("后端/专项注册导入/BAAH.registration"):
        from app.task.BAAH.registration import REGISTRATION as baah
    with startup_stage("后端/专项注册导入/BetterGI.registration"):
        from app.task.BetterGI.registration import REGISTRATION as bettergi
    with startup_stage("后端/专项注册导入/general.registration"):
        from app.task.general.registration import REGISTRATION as general
    with startup_stage("后端/专项注册导入/HSR.registration"):
        from app.task.HSR.registration import REGISTRATION as hsr
    with startup_stage("后端/专项注册导入/MAA.registration"):
        from app.task.MAA.registration import REGISTRATION as maa
    with startup_stage("后端/专项注册导入/MaaEnd.registration"):
        from app.task.MaaEnd.registration import registration as maaend_registration
    with startup_stage("后端/专项注册导入/MaaFW.registration"):
        from app.task.MaaFW.registration import REGISTRATION as maafw
    with startup_stage("后端/专项注册导入/MaaFW.tools.embedded.script_lifecycle"):
        from app.task.MaaFW.tools.embedded.script_lifecycle import cleanup_script_files
    with startup_stage("后端/专项注册导入/OkNte.registration"):
        from app.task.OkNte.registration import REGISTRATION as oknte
    with startup_stage("后端/专项注册导入/Okww.registration"):
        from app.task.Okww.registration import REGISTRATION as okww
    with startup_stage("后端/专项注册导入/SRC.registration"):
        from app.task.SRC.registration import REGISTRATION as src
    with startup_stage("后端/专项注册导入/Whimbox.registration"):
        from app.task.Whimbox.registration import REGISTRATION as whimbox
    with startup_stage("后端/专项注册导入/ZzzOd.registration"):
        from app.task.ZzzOd.registration import registration as zzzod_registration

    capabilities = build_script_capabilities(
        (
            maaend_registration(maaend=maaend),
            bettergi,
            maa,
            src,
            zzzod_registration(zzzod=zzzod),
            maafw,
            okww,
            general,
            oknte,
            hsr,
            baah,
            whimbox,
        ),
        expected_types=CLASS_BOOK.values(),
    )
    # 所有现有脚本 UUID 都清理可能残留的 MFW 视图；家族专属的
    # 提交后对账仍只由 MaaFW handler 声明。目录和清理规则归 MFW。
    return replace(
        capabilities,
        config_handlers=tuple(
            (
                entry_type,
                replace(handler, cleanup_script_files=cleanup_script_files)
                if handler is not None
                else None,
            )
            for entry_type, handler in capabilities.config_handlers
        ),
    )
