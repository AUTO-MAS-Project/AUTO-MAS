#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ConfigRestoreService 分发逻辑的最小回归测试（stub 目标池，不触真实配置）。"""

import asyncio

import pytest

from app.utils.config_restore import ConfigRestoreService, ConfigRestoreTarget


def make_service(**target_kwargs) -> ConfigRestoreService:
    async def empty_list() -> list[str]:
        return []

    return ConfigRestoreService(
        targets=[
            ConfigRestoreTarget(key="mas", list_backups=empty_list, **target_kwargs)
        ],
    )


def test_ensure_dispatches_to_snapshot() -> None:
    """ensure(key) 分发到目标池 snapshot 回调并透传返回值。"""
    calls: list[str] = []

    async def snapshot() -> dict:
        calls.append("snapshot")
        return {"created": True, "time": "20260907-000000"}

    service = make_service(snapshot=snapshot)
    result = asyncio.run(service.ensure("mas"))
    assert calls == ["snapshot"]
    assert result == {"created": True, "time": "20260907-000000"}


def test_ensure_rejects_target_without_snapshot() -> None:
    """目标池未提供 snapshot 时 ensure 报 ValueError（该目标不支持按需归档）。"""
    service = make_service()
    with pytest.raises(ValueError, match="不支持按需归档"):
        asyncio.run(service.ensure("mas"))


def test_ensure_rejects_unknown_target() -> None:
    """未知目标 key 报 ValueError（与 list/preview/restore 同一守卫语义）。"""

    async def snapshot() -> dict:
        return {}

    service = make_service(snapshot=snapshot)
    with pytest.raises(ValueError, match="不支持的恢复目标"):
        asyncio.run(service.ensure("nonexistent"))
