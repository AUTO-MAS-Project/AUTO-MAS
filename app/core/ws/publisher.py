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


import time
from collections import OrderedDict
from typing import Dict, Mapping, Optional, Tuple, Union

from pydantic import BaseModel, JsonValue

from app.utils.logger import get_logger

from .manager import MainConnection
from .protocol import TASK_COMPLETED, TASK_CONFIG_DISCARDED, build_message

logger = get_logger("WS发布器")

# 只有任务终态消息值得断线补发：它们是用户可见的最终结果，其余消息都是可再取的中间态。
_TERMINAL_TYPES = frozenset({TASK_COMPLETED, TASK_CONFIG_DISCARDED})
# 待补发副本的留存窗口，与任务终态查询窗口（task_manager 的 _RECENT_RESULTS_*）一致。
_RETAIN_MAX = 200
_RETAIN_TTL_SECONDS = 1800


class _WSPublisher:
    """业务模块的统一 WebSocket 出站接口。

    主连接未就绪时消息直接丢弃（记录低级别日志）；只有任务终态消息留一份待补发
    副本，重连后由 replay_pending 补齐，其余消息仍不缓存、不重放。
    """

    def __init__(self) -> None:
        # key 为 "id|type"：同一任务的同类终态只留最新一条，补发时不会刷屏。
        self._pending: "OrderedDict[str, Tuple[float, Dict[str, JsonValue]]]" = (
            OrderedDict()
        )

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
        message = build_message(id=id, type=type, data=payload)
        sent = await MainConnection.send(message)
        if not sent:
            if type in _TERMINAL_TYPES:
                self._retain(id, type, message)
            logger.debug(f"主连接未就绪，消息已丢弃: id={id}, type={type}")
        else:
            # 已确认送达，撤掉可能残留的待补发副本
            self._pending.pop(f"{id}|{type}", None)
        return sent

    async def replay_pending(self) -> None:
        """重连后补发断线期间未送达的任务终态。

        作为主连接建立回调注册；补发失败的副本保留到下次重连，重复补发由前端去重。
        """

        self._prune()
        for key, (_, message) in list(self._pending.items()):
            if await MainConnection.send(message):
                self._pending.pop(key, None)
                logger.info(f"已补发断线期间的任务终态: {message.get('type')}")

    def _retain(self, id: str, type: str, message: Dict[str, JsonValue]) -> None:
        """留存一条待补发的任务终态副本，按条数上限与留存时长裁剪。"""

        key = f"{id}|{type}"
        self._pending.pop(key, None)
        self._pending[key] = (time.monotonic(), message)
        self._prune()
        while len(self._pending) > _RETAIN_MAX:
            self._pending.popitem(last=False)

    def _prune(self) -> None:
        """丢掉超过留存时长的待补发副本。"""

        deadline = time.monotonic() - _RETAIN_TTL_SECONDS
        for key in [k for k, (ts, _) in self._pending.items() if ts < deadline]:
            self._pending.pop(key, None)


Publisher = _WSPublisher()
