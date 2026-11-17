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


from app.utils.common.startup_timing import startup_stage

with startup_stage("后端/API 导入/community"):
    from .community import router as community_router
with startup_stage("后端/API 导入/core"):
    from .core import router as core_router
with startup_stage("后端/API 导入/dispatch"):
    from .dispatch import router as dispatch_router
with startup_stage("后端/API 导入/emulator"):
    from .emulator import router as emulator_router
with startup_stage("后端/API 导入/history"):
    from .history import router as history_router
with startup_stage("后端/API 导入/i18n"):
    from .i18n import router as i18n_router
with startup_stage("后端/API 导入/info"):
    from .info import router as info_router
with startup_stage("后端/API 导入/ocr"):
    from .ocr import router as ocr_router
with startup_stage("后端/API 导入/openclaw_qq"):
    from .openclaw_qq import router as openclaw_qq_router
with startup_stage("后端/API 导入/plan"):
    from .plan import router as plan_router
with startup_stage("后端/API 导入/queue"):
    from .queue import router as queue_router
with startup_stage("后端/API 导入/scripts"):
    from .scripts import router as scripts_router
with startup_stage("后端/API 导入/setting"):
    from .setting import router as setting_router
with startup_stage("后端/API 导入/share"):
    from .share import router as share_router
with startup_stage("后端/API 导入/update"):
    from .update import router as update_router
from .downloads import router as downloads_router
from .operations import router as operations_router
from .plugin import router as plugin_router

__all__ = [
    "plugin_router",
    "operations_router",
    "downloads_router",
    "community_router",
    "core_router",
    "info_router",
    "scripts_router",
    "plan_router",
    "emulator_router",
    "queue_router",
    "dispatch_router",
    "history_router",
    "i18n_router",
    "setting_router",
    "share_router",
    "update_router",
    "ocr_router",
    "openclaw_qq_router",
]
