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


import uuid
import asyncio
from typing import Dict, List, Optional

from pydantic import ValidationError

from . import protocol
from .dispatcher import Dispatcher
from .publisher import Publisher
from app.models.schema import WSEnvelope, WSDialogRequestData, WSDialogResponseData
from app.utils.logger import get_logger

logger = get_logger("WS弹窗")


class _WSDialogs:
    """应用内弹窗的请求-响应关联。

    请求与响应均使用 id=Main，通过 data.requestId 关联；
    等待无超时（与原手动审核行为一致），任务取消时随协程一并取消。
    """

    def __init__(self) -> None:
        self._pending: Dict[str, asyncio.Future] = {}
        Dispatcher.register(protocol.ID_MAIN, protocol.DIALOG_RESPONSE, self._on_response)

    async def ask(
        self,
        title: str,
        message: str,
        options: Optional[List[str]] = None,
        task_id: Optional[str] = None,
    ) -> bool:
        """向前端发起弹窗请求并等待用户选择。

        Args:
            title (str): 弹窗标题。
            message (str): 弹窗内容。
            options (Optional[List[str]]): 选项文案，默认 ["是", "否"]。
            task_id (Optional[str]): 关联的任务 ID，仅用于前端展示上下文。

        Returns:
            bool: 用户选择第一个选项时为 True。
        """
        request_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        await Publisher.send(
            id=protocol.ID_MAIN,
            type=protocol.DIALOG_REQUEST,
            data=WSDialogRequestData(
                requestId=request_id,
                taskId=task_id,
                title=title,
                message=message,
                options=options or ["是", "否"],
            ),
        )

        try:
            return await future
        finally:
            self._pending.pop(request_id, None)

    def _on_response(self, envelope: WSEnvelope) -> None:
        """处理前端弹窗响应，未匹配到等待方的响应直接丢弃。"""
        try:
            data = WSDialogResponseData(**envelope.data)
        except ValidationError:
            logger.warning("弹窗响应数据不合法，已丢弃")
            return

        future = self._pending.get(data.requestId)
        if future is None or future.done():
            logger.debug(f"弹窗响应无等待方，已丢弃: requestId={data.requestId}")
            return
        future.set_result(bool(data.choice))


Dialogs = _WSDialogs()
