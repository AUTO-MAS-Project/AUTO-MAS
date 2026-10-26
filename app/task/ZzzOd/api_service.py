#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 宿主能力装配与编辑入口。"""

from typing import Any

from .config_context import ZzzOdConfigGateway, ZzzOdContext
from .service import ZzzOdService, read_task_catalog


def get_service(gateway: ZzzOdConfigGateway) -> ZzzOdService:
    """只注入配置集合与落盘能力，不把专项操作委托回宿主。"""
    return ZzzOdService(ZzzOdContext(gateway.ScriptConfig, flush=gateway.flush))


def get_task_catalog(
    gateway: ZzzOdConfigGateway, script_id: str
) -> list[dict[str, Any]]:
    """先走安装目录哨兵校验，避免空路径退回当前目录，再读取任务目录。"""
    return read_task_catalog(get_service(gateway).get_root(script_id))


async def save_native_config(
    gateway: ZzzOdConfigGateway,
    *,
    script_id: str,
    instance_idx: int,
    account: dict | None = None,
    tasks: list[dict] | None = None,
    instance_run: str | None = None,
    launch_args: dict | None = None,
    after_done: str | None = None,
) -> dict[str, Any]:
    """保存成功后在同一 Task 回读；读取失败不回退已写入的原生文件。"""
    service = get_service(gateway)
    await service.save_native_config(
        script_id,
        instance_idx,
        account=account,
        tasks=tasks,
        instance_run=instance_run,
        launch_args=launch_args,
        after_done=after_done,
    )
    return await service.get_native_config(script_id, instance_idx)
