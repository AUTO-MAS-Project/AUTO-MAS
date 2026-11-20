#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""连接神秘入口解锁状态与宿主配置，供后端校验与插件门禁共用。

口令只是轻量访问门槛，不承担身份认证：它由当日北京日期派生，任何看到实现的人都能算出。
真正的作用是让附属插件在未解锁时不出现在市场上、也不允许安装。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from app.config import ConfigError, config_manager
from app.core import Config
from app.utils import UTC8

# 与前端 frontend/src/utils/mysteryAccess.ts 保持同一口令形态。
ACCESS_CODE_PATTERN = re.compile(r"^[0-9A-F]{8,64}$")


class MysteryAccessError(ValueError):
    """神秘入口未解锁或口令不正确。"""


def current_access_date(now: datetime | None = None) -> str:
    """取口令所属的北京日期，跨日后旧口令自然失效。"""
    moment = now if now is not None else datetime.now(tz=UTC8)
    return moment.astimezone(UTC8).strftime("%Y-%m-%d")


def derive_access_code(date: str) -> str:
    """按日期派生当日完整口令，与前端算法一致。"""
    return hashlib.sha256(date.replace("-", "").encode("utf-8")).hexdigest().upper()


def matches_access_code(candidate: str, *, date: str) -> bool:
    """校验用户输入是否为当日口令的一段，前端同样按子串匹配。"""
    code = candidate.strip().upper()
    if not ACCESS_CODE_PATTERN.fullmatch(code):
        return False
    return code in derive_access_code(date)


class MysteryGate:
    """神秘入口的解锁状态：读取持久化日期、校验口令、写入与撤销解锁。"""

    def unlocked_date(self) -> str:
        """返回上次解锁的北京日期，从未解锁时返回空串。"""
        moment = Config.setting.mystery.UnlockedDate
        if moment.year <= 2000:
            return ""
        return moment.astimezone(UTC8).strftime("%Y-%m-%d")

    def is_unlocked(self, now: datetime | None = None) -> bool:
        """判断当日是否已解锁；跨日后需要重新解锁。"""
        return self.unlocked_date() == current_access_date(now)

    async def unlock(self, access_code: str, now: datetime | None = None) -> str:
        """校验口令并记录当日解锁，返回记录的日期。"""
        date = current_access_date(now)
        if not matches_access_code(access_code, date=date):
            raise MysteryAccessError("神秘入口口令不正确")
        await self._write_date(date)
        return date

    async def lock(self) -> None:
        """主动撤销解锁。"""
        await self._write_date("")

    async def _write_date(self, date: str) -> None:
        """把解锁日期写回全局配置；空串表示回到未解锁的初始值。"""
        moment = (
            datetime(2000, 1, 1, tzinfo=UTC8)
            if not date
            else datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC8)
        )
        try:
            async with config_manager.transaction():
                await Config.setting.update(
                    type(Config.setting).model_validate(
                        {"mystery": {"UnlockedDate": moment}}
                    ),
                    check_visibility=False,
                )
        except ConfigError as exc:
            # 在宿主边界转换框架异常，调用方只处理通用写入失败。
            raise OSError(f"神秘入口解锁状态更新失败: {exc}") from exc


Mystery = MysteryGate()


__all__ = [
    "ACCESS_CODE_PATTERN",
    "Mystery",
    "MysteryAccessError",
    "current_access_date",
    "derive_access_code",
    "matches_access_code",
]
