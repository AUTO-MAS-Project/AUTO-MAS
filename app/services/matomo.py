#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import aiohttp
import json
import uuid
import psutil
import platform
import time
from typing import Dict, Any, Optional

from app.core import Config
from app.utils.logger import get_logger

logger = get_logger("信息上报")


class _MatomoHandler:
    """Matomo统计上报服务"""

    base_url = "https://statistics.auto-mas.top/matomo.php"
    site_id = "3"

    def __init__(self):

        self.session = None

    async def _get_session(self):
        """获取HTTP会话"""

        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()

    def _build_base_params(self, custom_vars: Optional[Dict[str, Any]] = None):
        """构建基础参数"""
        params = {
            "idsite": self.site_id,
            "rec": "1",
            "action_name": "AUTO-MAS后端",
            "_id": Config.get("Data", "UID")[:16],
            "uid": Config.get("Data", "UID"),
            "rand": str(uuid.uuid4().int)[:10],
            "apiv": "1",
            "h": time.strftime("%H"),
            "m": time.strftime("%M"),
            "s": time.strftime("%S"),
            "ua": f"AUTO-MAS/{Config.version()} ({platform.system()} {platform.release()})",
        }

        # 添加自定义变量
        if custom_vars is not None:
            cvar = {}
            for i, (key, value) in enumerate(custom_vars.items(), 1):
                if i <= 5:
                    cvar[str(i)] = [str(key), str(value)]
            if cvar:
                params["_cvar"] = json.dumps(cvar)

        return params

    async def send_event(
        self,
        category: str,
        action: str,
        name: Optional[str] = None,
        value: Optional[float] = None,
        custom_vars: Optional[Dict[str, Any]] = None,
    ):
        """发送事件数据到Matomo

        Args:
            category: 事件类别，如 "Script", "Config", "User"
            action: 事件动作，如 "Execute", "Update", "Login"
            name: 事件名称，如具体的脚本名称
            value: 事件值，如执行时长、文件大小等数值
            custom_vars: 自定义变量字典
        """
        try:
            session = await self._get_session()
            if session is None:
                return

            params = self._build_base_params(custom_vars)
            params.update({"e_c": category, "e_a": action, "e_n": name, "e_v": value})
            params = {k: v for k, v in params.items() if v is not None}

            async with session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    logger.debug(f"Matomo事件上报成功: {category}/{action}")
                else:
                    logger.warning(f"Matomo事件上报失败: {response.status}")

        except asyncio.TimeoutError:
            logger.warning("Matomo事件上报超时")
        except Exception as e:
            logger.error(f"Matomo事件上报错误: {e}")


Matomo = _MatomoHandler()
