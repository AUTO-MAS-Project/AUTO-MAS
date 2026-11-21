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


import asyncio
from collections.abc import Callable
from typing import Mapping, Optional, Union
from uuid import UUID

from pydantic import BaseModel, JsonValue

from app.core.ws.protocol import CONFIG_UI_CHANGED, ID_CONFIG, build_message
from app.utils import get_logger

logger = get_logger("WS发布器")


class _WSPublisher:
    """业务模块的统一 WebSocket 出站接口。

    主连接未就绪时消息直接丢弃（记录低级别日志），不缓存、不重放。
    """

    def config_ui_listener(self) -> Callable[[frozenset[UUID]], None]:
        """把配置提交送到宿主事件循环。同一批重复 UID 合并发送。"""
        loop = asyncio.get_running_loop()
        pending: set[UUID] = set()
        worker: asyncio.Task[None] | None = None

        async def flush() -> None:
            while pending:
                node_uids: list[JsonValue] = list(map(str, pending))
                pending.clear()
                await self.send(ID_CONFIG, CONFIG_UI_CHANGED, {"nodeUids": node_uids})

        def enqueue(sources: frozenset[UUID]) -> None:
            nonlocal worker
            pending.update(sources)
            if worker is None or worker.done():
                worker = loop.create_task(flush())

        def committed(sources: frozenset[UUID]) -> None:
            if not loop.is_closed():
                loop.call_soon_threadsafe(enqueue, sources)

        return committed

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
        from app.core import MainConnection

        payload = (
            data.model_dump(mode="json")
            if isinstance(data, BaseModel)
            else dict(data or {})
        )
        sent = await MainConnection.send(build_message(id=id, type=type, data=payload))
        if not sent:
            logger.debug(f"主连接未就绪，消息已丢弃: id={id}, type={type}")
        return sent
