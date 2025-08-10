#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
from copy import deepcopy
from typing import Set

from app.utils import get_logger


logger = get_logger("消息广播")


class _Broadcast:

    def __init__(self):
        self.__subscribers: Set[asyncio.Queue] = set()

    async def subscribe(self, queue: asyncio.Queue):
        """订阅者注册"""
        self.__subscribers.add(queue)

    async def unsubscribe(self, queue: asyncio.Queue):
        """取消订阅"""
        self.__subscribers.remove(queue)

    async def put(self, item):
        """向所有订阅者广播消息"""
        for subscriber in self.__subscribers:
            await subscriber.put(deepcopy(item))


Broadcast = _Broadcast()
