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

"""ZZZ-OD 编辑业务入口：任务目录与原生配置保存回读。"""

from pathlib import Path
from typing import Any, Protocol


class ZzzOdConfigGateway(Protocol):
    """专项编辑需要的配置能力，由调用方注入。"""

    def get_zzzod_root(self, script_id: str) -> Path: ...

    async def get_zzzod_native_config(
        self, script_id: str, instance_idx: int
    ) -> dict[str, Any]: ...

    async def save_zzzod_native_config(
        self,
        script_id: str,
        instance_idx: int,
        account: dict | None = None,
        tasks: list[dict] | None = None,
        instance_run: str | None = None,
        launch_args: dict | None = None,
        after_done: str | None = None,
    ) -> dict: ...


def read_task_catalog(root: Path) -> list[dict[str, Any]]:
    """读取任务目录并补齐专项支持的配置与跳转能力。"""
    from .tools import get_task_app_fields, get_task_app_jump, list_app_catalog

    return [
        {
            **item,
            "configurable": get_task_app_fields(str(item["app_id"])) is not None,
            "jump": get_task_app_jump(str(item["app_id"])),
        }
        for item in list_app_catalog(root)
    ]


def get_task_catalog(
    gateway: ZzzOdConfigGateway, script_id: str
) -> list[dict[str, Any]]:
    """先走安装目录哨兵校验，避免空路径退回当前目录，再读取任务目录。"""
    return read_task_catalog(gateway.get_zzzod_root(script_id))


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
    await gateway.save_zzzod_native_config(
        script_id,
        instance_idx,
        account=account,
        tasks=tasks,
        instance_run=instance_run,
        launch_args=launch_args,
        after_done=after_done,
    )
    return await gateway.get_zzzod_native_config(script_id, instance_idx)
