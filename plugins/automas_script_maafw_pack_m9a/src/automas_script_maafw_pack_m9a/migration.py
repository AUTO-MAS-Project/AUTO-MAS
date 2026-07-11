from __future__ import annotations

import json
from typing import Any

from automas_maafw_interface.models import MaaFWInterface, MaaFWOption, MaaFWTask
from automas_maafw_interface.service import MaaFWInterfaceService


_RESERVED_TASK_NAMES = {
    "启动游戏",
    "关闭游戏",
    "切换账号",
    "StartUp",
    "CloseDown",
    "Close1999",
    "SwitchAccount",
}


async def migrate_legacy_m9a_config(legacy_script: Any, provider: Any) -> Any:
    """Convert a persisted M9AConfig into the generated MaaFW plugin shape."""

    raw_script = await legacy_script.toDict(if_decrypt=False)
    project_path = str(_nested(raw_script, "Info", "Path") or "").strip()
    if not project_path:
        raise ValueError("旧 M9A 配置缺少项目路径，暂不自动迁移")

    interface = MaaFWInterfaceService().load(project_path)
    controller_name = _default_adb_controller(interface)
    script_payload = _build_script_payload(raw_script, interface, controller_name)
    script_payload["SubConfigsInfo"] = {
        "UserData": await _build_user_collection(
            legacy_script,
            provider.user_config_class,
            interface,
            controller_name,
        )
    }

    migrated = provider.script_config_class()
    await migrated.load(script_payload)
    return migrated


def _build_script_payload(
    raw_script: dict[str, Any],
    interface: MaaFWInterface,
    controller_name: str,
) -> dict[str, Any]:
    daily_tasks = (
        _task_names_for_entries(interface, "Psychube")
        if bool(_nested(raw_script, "Run", "IfPsychubeDailyOnce"))
        else []
    )
    monthly_tasks = (
        _task_names_for_entries(interface, "Limbo", "Lucidscape", "SleepDream")
        if bool(_nested(raw_script, "Run", "IfSleepDreamMonthlyOnce"))
        else []
    )
    return {
        "Info": {
            "Name": _nested(raw_script, "Info", "Name"),
            "ProjectLabel": interface.label or interface.name,
            "Path": _nested(raw_script, "Info", "Path"),
            "Controller": controller_name,
            "Resource": "",
        },
        "Emulator": {
            "Id": _nested(raw_script, "Emulator", "Id"),
            "Index": _nested(raw_script, "Emulator", "Index"),
        },
        "Update": {
            "IfAutoUpdate": bool(
                _nested(raw_script, "Run", "IfAutoUpdateAfterQueue")
            ),
        },
        "Run": {
            "ProxyTimesLimit": _nested(raw_script, "Run", "ProxyTimesLimit"),
            "RunTimesLimit": _nested(raw_script, "Run", "RunTimesLimit"),
            "RunTimeLimit": _nested(raw_script, "Run", "RunTimeLimit"),
            "DailyOnceTasks": _json(daily_tasks),
            "WeeklyOnceTasks": _json([]),
            "MonthlyOnceTasks": _json(monthly_tasks),
        },
    }


async def _build_user_collection(
    legacy_script: Any,
    user_config_class: type,
    interface: MaaFWInterface,
    controller_name: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {"instances": []}
    for uid, old_user in legacy_script.UserData.items():
        raw_user = await old_user.toDict(if_decrypt=False)
        result["instances"].append(
            {"uid": str(uid), "type": user_config_class.__name__}
        )
        result[str(uid)] = _build_user_payload(
            raw_user,
            interface,
            controller_name,
        )
    return result


def _build_user_payload(
    raw_user: dict[str, Any],
    interface: MaaFWInterface,
    controller_name: str,
) -> dict[str, Any]:
    task_snapshot = _build_task_snapshot(
        _load_json(_nested(raw_user, "Task", "Queue"), list),
        interface,
    )
    period_records = {
        "daily": _period_records(
            interface,
            str(_nested(raw_user, "Data", "LastPsychubeDate") or "2000-01-01"),
            "Psychube",
        ),
        "weekly": {},
        "monthly": {
            **_period_records(
                interface,
                str(_nested(raw_user, "Data", "LastLimboMonth") or "2000-01"),
                "Limbo",
            ),
            **_period_records(
                interface,
                str(
                    _nested(raw_user, "Data", "LastLucidscapeMonth")
                    or "2000-01"
                ),
                "Lucidscape",
            ),
        },
    }
    resource_name = _match_resource_name(
        interface,
        str(_nested(raw_user, "Info", "Resource") or ""),
        controller_name,
    )
    payload = {
        "Info": {
            **_copy_group(
                raw_user,
                "Info",
                (
                    "Name",
                    "Status",
                    "RemainedDay",
                    "IfScriptBeforeTask",
                    "ScriptBeforeTask",
                    "IfScriptAfterTask",
                    "ScriptAfterTask",
                    "Notes",
                    "Account",
                ),
            ),
            "Controller": controller_name,
            "Resource": resource_name,
        },
        "Task": {
            "SelectedPreset": "",
            "TaskSnapshot": _json(task_snapshot),
        },
        "Data": {
            **_copy_group(
                raw_user,
                "Data",
                ("LastProxyDate", "ProxyTimes", "IfPassCheck"),
            ),
            "PeriodTaskRecords": _json(period_records),
        },
        "Notify": _copy_group(
            raw_user,
            "Notify",
            (
                "Enabled",
                "IfSendStatistic",
                "IfSendMail",
                "ToAddress",
                "IfServerChan",
                "ServerChanKey",
            ),
        ),
    }
    custom_webhooks = (
        raw_user.get("SubConfigsInfo", {}).get("Notify_CustomWebhooks")
        if isinstance(raw_user.get("SubConfigsInfo"), dict)
        else None
    )
    if isinstance(custom_webhooks, dict):
        payload["SubConfigsInfo"] = {
            "Notify_CustomWebhooks": custom_webhooks,
        }
    return payload


def _build_task_snapshot(
    queue: list[Any],
    interface: MaaFWInterface,
) -> dict[str, Any]:
    task_order: list[str] = []
    task_checked = {task.name: False for task in interface.task}
    task_options: dict[str, dict[str, Any]] = {}
    for item in queue:
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("name") or item.get("entry") or "").strip()
        if not raw_name or raw_name in _RESERVED_TASK_NAMES:
            continue
        task = _match_task(interface, raw_name, str(item.get("entry") or ""))
        if task is None or task.name in task_order:
            continue
        task_order.append(task.name)
        task_checked[task.name] = True
        task_options[task.name] = _convert_task_options(
            item.get("options"),
            interface,
        )

    task_order.extend(task.name for task in interface.task if task.name not in task_order)
    return {
        "taskOrder": task_order,
        "taskChecked": task_checked,
        "taskOptions": task_options,
    }


def _convert_task_options(
    raw_options: Any,
    interface: MaaFWInterface,
) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    if not isinstance(raw_options, list):
        return converted
    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            continue
        option_name = str(raw_option.get("name") or "").strip()
        option = interface.option.get(option_name)
        if not option_name or option is None:
            continue
        value = _convert_option_value(raw_option, option)
        if value is not None:
            converted[option_name] = value
        converted.update(
            _convert_task_options(raw_option.get("sub_options"), interface)
        )
    return converted


def _convert_option_value(raw_option: dict[str, Any], option: MaaFWOption) -> Any:
    if option.type == "input":
        value = raw_option.get("input_values", raw_option.get("data"))
        if isinstance(value, dict):
            return {
                str(key): str(item)
                for key, item in value.items()
                if isinstance(key, str)
            }
        return None
    if option.type == "checkbox":
        selected = raw_option.get("selected_cases")
        if isinstance(selected, list):
            return [str(item) for item in selected]
        return []

    cases = option.cases or []
    selected = raw_option.get("selected_cases")
    if isinstance(selected, list) and selected:
        return str(selected[0])
    try:
        index = int(raw_option.get("index", 0))
    except (TypeError, ValueError):
        index = 0
    if 0 <= index < len(cases):
        return cases[index].name
    return cases[0].name if cases else None


def _match_task(
    interface: MaaFWInterface,
    name: str,
    entry: str = "",
) -> MaaFWTask | None:
    for candidate in (name, entry):
        if not candidate:
            continue
        task = next(
            (
                item
                for item in interface.task
                if candidate in {item.name, item.entry, item.label}
            ),
            None,
        )
        if task is not None:
            return task
    return None


def _task_names_for_entries(
    interface: MaaFWInterface,
    *entries: str,
) -> list[str]:
    wanted = set(entries)
    return [
        task.name
        for task in interface.task
        if task.entry in wanted or task.name in wanted
    ]


def _period_records(
    interface: MaaFWInterface,
    period_key: str,
    *entries: str,
) -> dict[str, str]:
    return {
        task_name: period_key
        for task_name in _task_names_for_entries(interface, *entries)
    }


def _default_adb_controller(interface: MaaFWInterface) -> str:
    controller = next(
        (item for item in interface.controller if item.type == "Adb"),
        None,
    )
    return controller.name if controller is not None else ""


def _match_resource_name(
    interface: MaaFWInterface,
    legacy_value: str,
    controller_name: str,
) -> str:
    if legacy_value:
        resource = next(
            (
                item
                for item in interface.resource
                if legacy_value in {item.name, item.label}
            ),
            None,
        )
        if resource is not None:
            return resource.name
    resource = next(
        (
            item
            for item in interface.resource
            if not item.controller or controller_name in item.controller
        ),
        None,
    )
    return resource.name if resource is not None else ""


def _copy_group(
    payload: dict[str, Any],
    group_name: str,
    field_names: tuple[str, ...],
) -> dict[str, Any]:
    group = payload.get(group_name)
    if not isinstance(group, dict):
        return {}
    return {name: group[name] for name in field_names if name in group}


def _nested(payload: dict[str, Any], group: str, name: str) -> Any:
    value = payload.get(group)
    return value.get(name) if isinstance(value, dict) else None


def _load_json(value: Any, expected_type: type) -> Any:
    if isinstance(value, expected_type):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return expected_type()
        if isinstance(parsed, expected_type):
            return parsed
    return expected_type()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


__all__ = ["migrate_legacy_m9a_config"]
