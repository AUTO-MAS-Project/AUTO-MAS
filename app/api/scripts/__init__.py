#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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
"""按专项聚合脚本路由，统一保留脚本管理前缀与标签。"""

from fastapi import APIRouter

from app.task.BAAH.api import router as baah_router
from app.task.BetterGI.api import router as bettergi_router
from app.task.HSR.api import router as hsr_router
from app.task.MAA.api import router as maa_router
from app.task.MaaEnd.api import router as maaend_router
from app.task.MaaFW.api import router as maafw_router
from app.task.MSS.api import router as mss_router
from app.task.OkNte.api import router as oknte_router
from app.task.Okww.api import router as okww_router
from app.task.Whimbox.api import router as whimbox_router
from app.task.ZzzOd.api import router as zzzod_router

from . import backup, management, sharing, users, webhooks
from .users import UserUpdateIn as UserUpdateIn

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])

router.include_router(management.router)
router.include_router(users.router)
router.include_router(webhooks.router)
router.include_router(sharing.router)
router.include_router(okww_router)
router.include_router(maaend_router)
router.include_router(maa_router)
router.include_router(maafw_router)
router.include_router(mss_router)
router.include_router(hsr_router)
router.include_router(bettergi_router)
router.include_router(baah_router)
router.include_router(zzzod_router)
router.include_router(whimbox_router)
router.include_router(oknte_router)
router.include_router(backup.router)
