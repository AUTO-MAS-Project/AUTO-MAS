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

from . import (
    baah,
    backup,
    bettergi,
    hsr,
    maa,
    maaend,
    maafw,
    management,
    oknte,
    okww,
    sharing,
    users,
    webhooks,
    whimbox,
    zzzod,
)
from .users import UserUpdateIn as UserUpdateIn

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])

router.include_router(management.router)
router.include_router(users.router)
router.include_router(webhooks.router)
router.include_router(sharing.router)
router.include_router(okww.router)
router.include_router(maaend.router)
router.include_router(maa.router)
router.include_router(maafw.router)
router.include_router(hsr.router)
router.include_router(bettergi.router)
router.include_router(baah.router)
router.include_router(zzzod.router)
router.include_router(whimbox.router)
router.include_router(oknte.router)
router.include_router(backup.router)
