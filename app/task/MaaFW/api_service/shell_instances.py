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

"""``/maafw/shell-instances*`` 端点背后的业务：列出项目目录里外壳（MFAAvalonia / MXU）
保存的配置实例，按勾选逐个建成用户。格式解析与换算在 ``tools/embedded/shell_instances``。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.schema import MaaFWShellInstanceImportItem, MaaFWShellInstanceItem
from app.task.MaaFW.api_service.common import (
    MaaFWApiReply,
    logger,
    maafw_effective_root,
    maafw_script_config,
)
from app.task.MaaFW.tools.core.interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
)
from app.task.MaaFW.tools.core.interface.models import MaaFWInterface
from app.task.MaaFW.tools.embedded.embedded_project import embedded_project_dir
from app.task.MaaFW.tools.embedded.shell_instances import (
    ShellInstance,
    assign_user_names,
    display_name,
    plan_instance_import,
    scan_shell_instances,
)

INSTANCE_NOT_FOUND = "项目目录里找不到这份配置（可能已在外壳里删除或改名）"


def _candidate_roots(script_id: str, script_config: Any) -> list[Path]:
    """按顺序去哪里找外壳配置：先来源目录，再内嵌副本。

    外壳把实例存在它自己的目录里，也就是用户选的来源目录（``Info.Path``）；副本导入时
    把外壳剔掉了（MFAAvalonia 的 ``appsettings.json`` 在项目根上、随外壳一起不带），
    ``config/`` 下留下的只是运行期用得到的那几份，所以副本只在来源目录不在了、或来源
    目录里没有外壳配置时兜底——副本若恰好保留了外壳配置，也能读出来。「复用已有脚本的
    项目」克隆出来的脚本 ``Info.Path`` 沿用源脚本的来源目录（与 ``Embedded.*`` 成对继承），
    走的是同一条路。
    """

    roots: list[Path] = []
    source = str(script_config.get("Info", "Path") or "").strip()
    if source:
        roots.append(Path(source))
    roots.append(embedded_project_dir(script_id))
    return roots


def _scan_first_root(roots: list[Path]) -> list[ShellInstance]:
    for root in roots:
        if not root.is_dir():
            continue
        found = scan_shell_instances(root)
        if found:
            return found
    return []


def _existing_user_names(script_config: Any) -> list[str]:
    return [
        str(user.get("Info", "Name") or "")
        for _, user in script_config.UserData.items()
    ]


def _interface_name(items: list[Any], raw: str) -> str:
    """脚本上记的 controller / resource 名在 interface 里存在才算数，否则当作不限。"""

    return raw if raw and any(item.name == raw for item in items) else ""


async def list_shell_instances(script_id: str) -> MaaFWApiReply:
    """``/maafw/shell-instances``：项目目录里外壳保存的配置实例。"""

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")
    try:
        instances = await asyncio.to_thread(
            _scan_first_root, _candidate_roots(script_id, script_config)
        )
    except Exception as exc:  # noqa: BLE001 - 扫描只读，失败不该挡住引导
        logger.opt(exception=True).warning(
            f"扫描外壳配置实例失败（{script_id}）：{type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"扫描外壳配置失败: {exc}")

    # 显示名要 interface；副本还没建好就退回外壳里记的原名，不为这个触发导入
    interface: MaaFWInterface | None = None
    view_root = embedded_project_dir(script_id)
    if instances and view_root.is_dir():
        try:
            interface = await asyncio.to_thread(load_interface_model_cached, view_root)
        except Exception as exc:  # noqa: BLE001 - 只影响显示名
            logger.warning(f"读取 interface 失败，实例列表显示原名：{exc}")

    user_names = assign_user_names(
        [instance.name for instance in instances], _existing_user_names(script_config)
    )
    items = [
        MaaFWShellInstanceItem(
            id=instance.id,
            name=instance.name,
            userName=user_name,
            source=instance.source,
            active=instance.active,
            taskCount=len(instance.tasks),
            controller=display_name(interface.controller, instance.controller)
            if interface
            else instance.controller,
            resource=display_name(interface.resource, instance.resource)
            if interface
            else instance.resource,
        )
        for instance, user_name in zip(instances, user_names)
    ]
    return MaaFWApiReply(data=items)


async def import_shell_instances(
    script_id: str, instance_ids: list[str]
) -> MaaFWApiReply:
    """``/maafw/shell-instances/import``：每个实例建一个用户，名字、任务队列与选项一起导入。

    逐个实例独立：一个失败（找不到、建用户被拒）不影响其它的，原因写进该项结果。
    用户名与列表里显示的一致——按全部实例的顺序去重，不随勾选变化。
    """

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")
    root, error = await maafw_effective_root(script_id, "")
    if root is None:
        return MaaFWApiReply.error(400, error)
    try:
        interface = await asyncio.to_thread(load_interface_model_cached, root)
        instances = await asyncio.to_thread(
            _scan_first_root, _candidate_roots(script_id, script_config)
        )
    except MaaFWInterfaceLoadError as exc:
        return MaaFWApiReply.error(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - 文件系统异常也要给出文案
        logger.opt(exception=True).warning(
            f"导入外壳配置实例失败（{script_id}）：{type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"读取外壳配置失败: {exc}")

    by_id = {instance.id: instance for instance in instances}
    name_by_id = dict(
        zip(
            [instance.id for instance in instances],
            assign_user_names(
                [instance.name for instance in instances],
                _existing_user_names(script_config),
            ),
        )
    )
    script_controller = _interface_name(
        interface.controller, str(script_config.get("Info", "Controller") or "")
    )
    script_resource = _interface_name(
        interface.resource, str(script_config.get("Info", "Resource") or "")
    )

    results: list[MaaFWShellInstanceImportItem] = []
    for instance_id in dict.fromkeys(instance_ids):
        instance = by_id.get(instance_id)
        if instance is None:
            logger.warning(f"导入外壳配置：找不到实例 {instance_id}")
            results.append(
                MaaFWShellInstanceImportItem(
                    instanceId=instance_id, error=INSTANCE_NOT_FOUND
                )
            )
            continue
        results.append(
            await _import_one(
                script_id,
                instance,
                name_by_id[instance.id],
                interface,
                script_controller=script_controller,
                script_resource=script_resource,
            )
        )
    return MaaFWApiReply(data=results)


async def _import_one(
    script_id: str,
    instance: ShellInstance,
    user_name: str,
    interface: MaaFWInterface,
    *,
    script_controller: str,
    script_resource: str,
) -> MaaFWShellInstanceImportItem:
    result = MaaFWShellInstanceImportItem(
        instanceId=instance.id, instanceName=instance.name, name=user_name
    )
    try:
        plan = await asyncio.to_thread(
            plan_instance_import,
            instance,
            interface,
            script_controller=script_controller,
            script_resource=script_resource,
        )
    except Exception as exc:  # noqa: BLE001 - 一份实例换算失败不影响其它实例
        logger.opt(exception=True).warning(
            f"换算外壳配置实例失败（{instance.id}）：{type(exc).__name__}: {exc}"
        )
        result.error = f"读不懂这份配置: {exc}"
        return result

    try:
        uid, _ = await Config.add_user(script_id)
    except Exception as exc:  # noqa: BLE001 - 脚本运行中等情况会拒绝新增
        logger.warning(f"导入外壳配置实例 {instance.id} 时新增用户失败：{exc}")
        result.error = f"新增用户失败: {exc}"
        return result
    try:
        await Config.update_user(
            script_id,
            str(uid),
            {
                "Info": {
                    "Name": user_name,
                    "Controller": plan.controller,
                    "Resource": plan.resource,
                },
                "Task": {
                    "SelectedPreset": "",
                    "TaskSnapshot": json.dumps(plan.snapshot, ensure_ascii=False),
                },
            },
        )
    except Exception as exc:  # noqa: BLE001 - 写不进去就把刚建的空用户撤掉
        logger.warning(f"导入外壳配置实例 {instance.id} 时写入用户失败：{exc}")
        try:
            await Config.del_user(script_id, str(uid))
        except Exception as cleanup_exc:  # noqa: BLE001
            logger.warning(f"撤销半成品用户 {uid} 失败：{cleanup_exc}")
        result.error = f"写入用户配置失败: {exc}"
        return result

    result.success = True
    result.userId = str(uid)
    result.importedTaskCount = plan.task_count
    result.skipped = plan.skipped
    logger.info(
        f"已从 {instance.source} 实例「{instance.name}」建用户「{user_name}」（{uid}）："
        f"导入 {plan.task_count} 个任务"
        + (
            f"，跳过 {len(plan.skipped)} 项：{'、'.join(plan.skipped)}"
            if plan.skipped
            else ""
        )
    )
    return result
