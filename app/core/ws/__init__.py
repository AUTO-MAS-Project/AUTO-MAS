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


"""主 WebSocket 子系统

- MainConnection: 唯一主连接的持有与收发
- Dispatcher: 按 id + type 分发前端消息
- Publisher: 业务模块统一出站接口
- protocol: 消息类别常量与信封解析
"""

from . import protocol
from .dispatcher import Dispatcher
from .manager import MainConnection
from .publisher import Publisher

__all__ = [
    "protocol",
    "MainConnection",
    "Dispatcher",
    "Publisher",
]
