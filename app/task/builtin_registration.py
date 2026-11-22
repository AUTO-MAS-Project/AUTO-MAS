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

from typing import TYPE_CHECKING

from app.models.config import CLASS_BOOK
from app.task.registration import ScriptCapabilities, build_script_capabilities
from app.utils.common.startup_timing import startup_stage

if TYPE_CHECKING:
    from app.task.MaaEnd.api_service import MaaEndConfigService
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
    with startup_stage("后端/专项注册导入/MaaEnd.registration"):
        from app.task.MaaEnd.registration import registration as maaend_registration
    with startup_stage("后端/专项注册导入/MaaFW.registration"):
        from app.task.MaaFW.registration import REGISTRATION as maafw
        from app.task.MaaFW.registration import register_owner as register_maafw_owner
    with startup_stage("后端/专项注册导入/M9A.registration"):
        from app.task.M9A.registration import REGISTRATION as m9a
        from app.task.M9A.registration import register_owner as register_m9a_owner
    with startup_stage("后端/专项注册导入/MSS.registration"):
        from app.task.MSS.registration import REGISTRATION as mss
        from app.task.MSS.registration import register_owner as register_mss_owner
    with startup_stage("后端/专项注册导入/OkNte.registration"):
        from app.task.OkNte.registration import REGISTRATION as oknte
    with startup_stage("后端/专项注册导入/Okww.registration"):
        from app.task.Okww.registration import REGISTRATION as okww
    with startup_stage("后端/专项注册导入/ZzzOd.registration"):
        from app.task.ZzzOd.registration import registration as zzzod_registration

    capabilities = build_script_capabilities(
        (
            maaend_registration(maaend=maaend),
            bettergi,
            zzzod_registration(zzzod=zzzod),
            maafw,
            m9a,
            mss,
            okww,
            general,
            oknte,
            hsr,
            baah,
        ),
        expected_types=CLASS_BOOK.values(),
    )
    # 三种 MFW 托管的属主登记给项目更新一侧（共享目录的清理与 /maafw/* 端点按它认托管）。
    # 删托管时的视图清理由三种类型各自的配置回调声明，只删本属主的视图。
    register_maafw_owner()
    register_m9a_owner()
    register_mss_owner()
    return capabilities
