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


from typing import Mapping, Optional, Union

from pydantic import BaseModel, JsonValue

from app.utils.logger import get_logger

from .manager import MainConnection
from .protocol import build_message

logger = get_logger("WS发布器")


class _WSPublisher:
    """业务模块的统一 WebSocket 出站接口。

    主连接未就绪时消息直接丢弃（记录低级别日志），不缓存、不重放。
    """

    async def send(
        self,
        id: str,
        type: str,
        data: Optional[Union[BaseModel, Mapping[str, JsonValue]]] = None,
    ) -> bool:
        """向前端发送一条统一信封消息。

        Args:
            id (str): 路由 ID，标识任务、请求或业务会话。
            type (str): 消息类别，见 app/core/ws/protocol.py。
            data (Optional[Union[BaseModel, Mapping[str, JsonValue]]]): 消息数据，
                关键消息传入对应的 WS*Data 模型。

        Returns:
            bool: 发送是否成功；未连接时返回 False。
        """
        payload = (
            data.model_dump(mode="json")
            if isinstance(data, BaseModel)
            else dict(data or {})
        )
        sent = await MainConnection.send(build_message(id=id, type=type, data=payload))
        if not sent:
            logger.debug(f"主连接未就绪，消息已丢弃: id={id}, type={type}")
        return sent


Publisher = _WSPublisher()
