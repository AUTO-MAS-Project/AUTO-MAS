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


from .core import router as core_router
from .dispatch import router as dispatch_router
from .emulator import router as emulator_router
from .emulator2 import router as emulator2_router
from .history import router as history_router
from .info import router as info_router
from .ocr import router as ocr_router
from .openclaw_qq import router as openclaw_qq_router
from .openclaw_weixin import router as openclaw_weixin_router
from .plan import router as plan_router
from .queue import router as queue_router
from .scripts import router as scripts_router
from .setting import router as setting_router
from .tools import router as tools_router
from .update import router as update_router

# 可选补丁：米游社扫码登录（可安全删除以下 2 行及 app/api/qr_login.py）
try:
    from .qr_login import router as qr_login_router
except ImportError:
    qr_login_router = None

__all__ = [
    "core_router",
    "info_router",
    "scripts_router",
    "plan_router",
    "emulator_router",
    "emulator2_router",
    "queue_router",
    "dispatch_router",
    "history_router",
    "tools_router",
    "setting_router",
    "update_router",
    "ocr_router",
    "openclaw_qq_router",
    "openclaw_weixin_router",
    "qr_login_router",
]
