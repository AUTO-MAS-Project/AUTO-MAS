#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""``/api/scripts/maafw/shell-configs`` 与 ``/maafw/shell-config/import`` 的业务。

外壳（MFAAvalonia）的实例配置躺在项目的 ``config/instances/`` 下，而 ``config/`` 属于
投影排除目录、**不进内嵌副本**，所以只能从脚本记着的**来源目录**读。来源没设或已经
删掉时给用户一句能照做的话，而不是一个空列表——用户页那个按钮的下一步全指望着它。

只读外壳文件；写盘由前端拿到翻译结果后按 MAS 自己的用户配置走。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.task.MaaFW.tools.core.interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
)
from app.task.MaaFW.tools.embedded.shell_config import (
    list_shell_instances,
    read_shell_selection,
)
from app.utils import get_logger

from .common import MaaFWApiReply, maafw_effective_root, maafw_script_config

logger = get_logger("MaaFW 外壳配置")

## 项目来源没设时给用户的话；用户页的按钮据此提示
NO_SOURCE_HINT = "请先在脚本页选择项目目录，再导入外壳配置"


def _shell_source_dir(script_id: str | None, fallback_path: str) -> tuple[Path | None, str]:
    """取外壳的来源目录（``Info.Path``，其次请求里带的 ``path``）。

    Returns:
        tuple[Path | None, str]: 目录不存在时第一个是 None，第二个是给用户的一句话。
    """

    raw = ""
    if script_id:
        try:
            raw = str(maafw_script_config(script_id).get("Info", "Path") or "").strip()
        except (KeyError, ValueError, TypeError) as exc:
            return None, f"MFW 脚本无效: {exc}"
    if not raw:
        raw = (fallback_path or "").strip()
    if not raw:
        return None, NO_SOURCE_HINT

    path = Path(raw)
    if not path.is_dir():
        return None, f"项目目录已不存在：{raw}；请在脚本页重新选择项目目录"
    return path, ""


async def list_shell_configs(
    script_id: str | None, fallback_path: str
) -> MaaFWApiReply:
    """列出外壳里可以导入的实例配置。"""

    source, error = _shell_source_dir(script_id, fallback_path)
    if source is None:
        return MaaFWApiReply.error(400, error)

    try:
        instances = await asyncio.to_thread(list_shell_instances, source)
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"读取外壳实例列表失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"读取外壳配置失败: {exc}")

    if not instances:
        return MaaFWApiReply.error(
            400, f"项目目录下没有找到外壳配置（{source / 'config' / 'instances'}）"
        )
    return MaaFWApiReply(data={"instances": instances})


async def import_shell_config(
    script_id: str | None, fallback_path: str, instance_id: str
) -> MaaFWApiReply:
    """把一个外壳实例的任务与选项翻译成 MAS 的任务队列。

    项目 interface 从**内嵌副本**取（副本是按来源投影出来的，任务表与来源一致），
    外壳配置从**来源目录**取。
    """

    source, error = _shell_source_dir(script_id, fallback_path)
    if source is None:
        return MaaFWApiReply.error(400, error)

    root, root_error = await maafw_effective_root(script_id, fallback_path)
    if root is None:
        return MaaFWApiReply.error(400, root_error)

    try:
        interface_model = await asyncio.to_thread(load_interface_model_cached, root)
    except MaaFWInterfaceLoadError as exc:
        return MaaFWApiReply.error(400, f"读取项目 interface 失败: {exc}")

    try:
        selection = await asyncio.to_thread(
            read_shell_selection, source, instance_id, interface_model
        )
    except FileNotFoundError as exc:
        return MaaFWApiReply.error(400, str(exc))
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"导入外壳配置失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"导入外壳配置失败: {exc}")

    tasks = selection.get("tasks") or []
    skipped = selection.get("skipped") or []
    message = f"已从外壳配置「{instance_id}」导入 {len(tasks)} 个任务"
    if skipped:
        message += f"，跳过 {len(skipped)} 项（项目里没有或取值不认识）"
    return MaaFWApiReply(message=message, data={"tasks": tasks, "skipped": skipped})


__all__ = ["NO_SOURCE_HINT", "import_shell_config", "list_shell_configs"]
