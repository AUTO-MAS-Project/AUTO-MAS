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

"""``/maafw/shell-instances*`` 端点背后的业务：列出项目目录里外壳（MFAAvalonia / MXU / MFW-PyQt6）
保存的配置实例，按勾选逐个建成用户。格式解析与换算在 ``tools/embedded/shell_instances``。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
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
from app.task.MaaFW.tools.core.interface.preview import interface_text_translator
from app.task.MaaFW.tools.embedded.embedded_project import embedded_project_dir
from app.task.MaaFW.tools.embedded.shell_instances import (
    ShellImportPlan,
    ShellInstance,
    Translate,
    assign_user_names,
    collect_instance_hotkeys,
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


def _requested_roots(
    script_id: str, script_config: Any, path: str | None
) -> tuple[list[Path] | None, str]:
    """列表与覆盖共用的「去哪儿找」：给了 ``path`` 就只认那个目录，否则 :func:`_candidate_roots`。

    两边必须同一口径：实例 ID 只是外壳里的文件名 / 配置 id，同一份外壳拷两份 ID 就一样，
    列表从别的目录列出来、覆盖却回默认目录按 ID 找，会悄悄导进另一份配置。
    """

    if path is not None and path.strip():
        picked = Path(path.strip())
        if not picked.is_dir():
            return None, f"目录不存在: {picked}"
        return [picked], ""
    return _candidate_roots(script_id, script_config), ""


def _scan_first_root(roots: list[Path]) -> tuple[Path | None, list[ShellInstance]]:
    """第一个扫到外壳配置的目录与其中的实例；都没有时为 ``(None, [])``。"""

    for root in roots:
        if not root.is_dir():
            continue
        found = scan_shell_instances(root)
        if found:
            return root, found
    return None, []


def _existing_user_names(script_config: Any) -> list[str]:
    return [
        str(user.get("Info", "Name") or "")
        for _, user in script_config.UserData.items()
    ]


def _interface_name(items: list[Any], raw: str) -> str:
    """脚本上记的 controller / resource 名在 interface 里存在才算数，否则当作不限。"""

    return raw if raw and any(item.name == raw for item in items) else ""


@dataclass
class _ImportContext:
    """「导入成用户」与「覆盖到已有用户」共用的准备结果。"""

    interface: MaaFWInterface
    translate: Translate
    instances: list[ShellInstance]
    #: 脚本当前的控制方式 / 资源（interface 里的名字，空串表示不限）
    script_controller: str
    script_resource: str


async def _load_import_context(
    script_id: str, script_config: Any, roots: list[Path], *, action: str
) -> _ImportContext | MaaFWApiReply:
    """读 interface 与显示名翻译、扫 ``roots`` 里的外壳实例；失败时返回端点直接交回的错误。

    ``action`` 只用来写日志（「导入外壳配置实例」/「覆盖外壳配置到用户」）。
    """

    root, error = await maafw_effective_root(script_id, "")
    if root is None:
        return MaaFWApiReply.error(400, error)
    try:
        interface = await asyncio.to_thread(load_interface_model_cached, root)
        # 跳过项里写 interface 的显示名（按项目语言文件翻过），与预览同一口径
        translate = await asyncio.to_thread(interface_text_translator, root, interface)
        _, instances = await asyncio.to_thread(_scan_first_root, roots)
    except MaaFWInterfaceLoadError as exc:
        return MaaFWApiReply.error(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - 文件系统异常也要给出文案
        logger.opt(exception=True).warning(
            f"{action}失败（{script_id}）：{type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"读取外壳配置失败: {exc}")
    return _ImportContext(
        interface=interface,
        translate=translate,
        instances=instances,
        script_controller=_interface_name(
            interface.controller, str(script_config.get("Info", "Controller") or "")
        ),
        script_resource=_interface_name(
            interface.resource, str(script_config.get("Info", "Resource") or "")
        ),
    )


async def _plan_import(
    instance: ShellInstance,
    context: _ImportContext,
    result: MaaFWShellInstanceImportItem,
) -> ShellImportPlan | None:
    """换算一份实例；换算失败时把原因写进 ``result.error`` 并返回 None。"""

    try:
        return await asyncio.to_thread(
            plan_instance_import,
            instance,
            context.interface,
            script_controller=context.script_controller,
            script_resource=context.script_resource,
            translate=context.translate,
        )
    except Exception as exc:  # noqa: BLE001 - 换算失败要把原因交回界面
        logger.opt(exception=True).warning(
            f"换算外壳配置实例失败（{instance.id}）：{type(exc).__name__}: {exc}"
        )
        result.error = f"读不懂这份配置: {exc}"
        return None


def _task_update(plan: ShellImportPlan) -> dict[str, Any]:
    """换算结果写进用户配置的 ``Task`` 分组：整份任务快照换掉，已选预设清空。"""

    return {
        "SelectedPreset": "",
        "TaskSnapshot": json.dumps(plan.snapshot, ensure_ascii=False),
    }


def _mark_imported(result: MaaFWShellInstanceImportItem, plan: ShellImportPlan) -> str:
    """把换算结果填进成功的结果项；返回日志末尾的跳过说明（没有跳过为空串）。"""

    result.success = True
    result.importedTaskCount = plan.task_count
    result.skipped = plan.skipped
    if not plan.skipped:
        return ""
    return f"，跳过 {len(plan.skipped)} 项：{'、'.join(plan.skipped)}"


async def list_shell_instances(
    script_id: str, path: str | None = None
) -> MaaFWApiReply:
    """``/maafw/shell-instances``：项目目录里外壳保存的配置实例。

    ``path`` 给了就只扫那个目录（键位弹窗「选择其他目录」：来源目录挪过、或平时用的是另一份外壳），
    不写回 ``Info.Path``；没给时先来源目录再内嵌副本。
    """

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")
    roots, error = _requested_roots(script_id, script_config, path)
    if roots is None:
        return MaaFWApiReply.error(400, error)
    try:
        found_root, instances = await asyncio.to_thread(_scan_first_root, roots)
    except Exception as exc:  # noqa: BLE001 - 扫描只读，失败不该挡住引导
        logger.opt(exception=True).warning(
            f"扫描外壳配置实例失败（{script_id}）：{type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"扫描外壳配置失败: {exc}")

    # 显示名要 interface；副本还没建好就退回外壳里记的原名，不为这个触发导入
    interface: MaaFWInterface | None = None
    translate: Translate | None = None
    view_root = embedded_project_dir(script_id)
    if instances and view_root.is_dir():
        try:
            interface = await asyncio.to_thread(load_interface_model_cached, view_root)
            translate = await asyncio.to_thread(
                interface_text_translator, view_root, interface
            )
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
            controller=display_name(
                interface.controller, instance.controller, translate
            )
            if interface
            else instance.controller,
            resource=display_name(interface.resource, instance.resource, translate)
            if interface
            else instance.resource,
            hotkeys=_instance_hotkeys(instance, interface),
            sourceDir=str(found_root) if found_root is not None else "",
        )
        for instance, user_name in zip(instances, user_names)
    ]
    return MaaFWApiReply(data=items)


def _instance_hotkeys(
    instance: ShellInstance, interface: MaaFWInterface | None
) -> dict[str, dict[str, str]]:
    """列表里每个实例带的键位；没有 interface 或换算出错时当没有（只影响「导入键位」入口）。"""

    if interface is None:
        return {}
    try:
        return collect_instance_hotkeys(instance, interface)
    except Exception as exc:  # noqa: BLE001 - 一份实例读不出键位不影响列表
        logger.warning(f"读取外壳配置实例 {instance.id} 的键位失败：{exc}")
        return {}


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
    context = await _load_import_context(
        script_id,
        script_config,
        _candidate_roots(script_id, script_config),
        action="导入外壳配置实例",
    )
    if isinstance(context, MaaFWApiReply):
        return context

    instances = context.instances
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
            await _import_one(script_id, instance, name_by_id[instance.id], context)
        )
    return MaaFWApiReply(data=results)


async def apply_shell_instance_to_user(
    script_id: str, user_id: str, instance_id: str, path: str | None = None
) -> MaaFWApiReply:
    """``/maafw/shell-instances/apply``：把一份外壳配置的任务队列与选项覆盖到指定用户。

    与 :func:`import_shell_instances` 共用同一条换算（``plan_instance_import``），只差落到哪儿：
    那个一份实例建一个新用户（新建脚本引导里的一次性迁移），这个写进已有的某个用户——脚本建好
    之后又在外壳里调过队列、想再同步一次时用。对不上的任务 / 选项同样进 ``skipped``，与引导
    那次的判定一字不差。

    ``path`` 与列表时传的一致：实例是从哪个目录列出来的，就回哪个目录按 ID 找。
    """

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")

    user = _user_of(script_config, user_id)
    if user is None:
        return MaaFWApiReply.error(404, "这个用户已经不在这个脚本里了")

    roots, error = _requested_roots(script_id, script_config, path)
    if roots is None:
        return MaaFWApiReply.error(400, error)
    context = await _load_import_context(
        script_id, script_config, roots, action="覆盖外壳配置到用户"
    )
    if isinstance(context, MaaFWApiReply):
        return context

    instance = next(
        (item for item in context.instances if item.id == instance_id), None
    )
    if instance is None:
        logger.warning(f"覆盖外壳配置：找不到实例 {instance_id}")
        return MaaFWApiReply.error(404, INSTANCE_NOT_FOUND)

    result = MaaFWShellInstanceImportItem(
        instanceId=instance.id,
        instanceName=instance.name,
        userId=user_id,
        name=str(user.get("Info", "Name") or ""),
    )
    plan = await _plan_import(instance, context, result)
    if plan is None:
        return MaaFWApiReply(data={"result": result})

    # 整份任务快照换掉：这就是「覆盖」，用户页上的队列与选项都会变成外壳那份。
    # 名字不动——这个入口是「再同步一次队列」，不是重命名用户。
    update: dict[str, dict[str, Any]] = {"Task": _task_update(plan)}
    try:
        # update_user 原地改 update：特调整理（M9A 收走受管任务、切换账号并进 Info）与密码加密
        # 都写回这份字典，写完它就是实际落盘的样子
        await Config.update_user(script_id, user_id, update)
    except Exception as exc:  # noqa: BLE001 - 脚本运行中等情况会拒绝写入
        logger.warning(f"覆盖外壳配置实例 {instance.id} 到用户 {user_id} 失败：{exc}")
        result.error = f"写入用户配置失败: {exc}"
        return MaaFWApiReply(data={"result": result})

    skipped_note = _mark_imported(result, plan)
    logger.info(
        f"已把 {instance.source} 实例「{instance.name}」的任务队列覆盖到用户"
        f"「{result.name}」（{user_id}）：{plan.task_count} 个任务{skipped_note}"
    )
    # 交回实际落盘的快照与特调改过的 Info：界面拿到就刷新本地状态，不用回头拉一次用户配置；
    # 交 plan.snapshot 的话，M9A 收走的受管任务会留在页面队列里、账号也对不上
    stored = update["Task"]["TaskSnapshot"]
    snapshot = json.loads(stored) if isinstance(stored, str) else stored
    info = dict(update.get("Info") or {})
    return MaaFWApiReply(data={"result": result, "snapshot": snapshot, "info": info})


def _user_of(script_config: Any, user_id: str) -> Any | None:
    """按 ID 取用户配置；这个脚本里没有就返回 None。"""

    for key, user in script_config.UserData.items():
        if str(key) == str(user_id):
            return user
    return None


async def _import_one(
    script_id: str,
    instance: ShellInstance,
    user_name: str,
    context: _ImportContext,
) -> MaaFWShellInstanceImportItem:
    result = MaaFWShellInstanceImportItem(
        instanceId=instance.id, instanceName=instance.name, name=user_name
    )
    # 一份实例换算失败不影响其它实例：原因已写进 result.error
    plan = await _plan_import(instance, context, result)
    if plan is None:
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
                # 只写名字：Info.Controller / Info.Resource 保持空串，与用户页保存的形状一致——
                # 运行器与用户页都只看脚本级的这两项，写进用户配置没有作用
                "Info": {"Name": user_name},
                "Task": _task_update(plan),
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

    result.userId = str(uid)
    skipped_note = _mark_imported(result, plan)
    logger.info(
        f"已从 {instance.source} 实例「{instance.name}」建用户「{user_name}」（{uid}）："
        f"导入 {plan.task_count} 个任务{skipped_note}"
    )
    return result
