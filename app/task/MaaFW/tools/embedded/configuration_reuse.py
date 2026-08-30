from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_CONFIGURATION_BYTES = 32 * 1024 * 1024
MAX_CONFIGURATION_TOTAL_BYTES = 64 * 1024 * 1024
MAX_CONFIGURATION_SOURCES = 200
MAX_CONFIGURATION_JSON_DEPTH = 64
MAX_CONFIGURATION_JSON_NODES = 200_000
UINT64_SIGN_BIT = 1 << 63
UINT64_MODULUS = 1 << 64


class MaaFWConfigurationReuseError(RuntimeError):
    """A user-facing configuration discovery or import-plan failure."""


def discover_configuration_sources(source_path: str | Path) -> list[dict[str, Any]]:
    """Discover explicit MaaFW-native configuration sources without mutation."""

    path = Path(source_path).expanduser().resolve()
    if not path.exists():
        raise MaaFWConfigurationReuseError(f"配置来源不存在：{path}")

    if path.is_file() and path.name.casefold() == "multi_config.json":
        files = _multi_config_files(path, path.parent)
    else:
        files = [path] if path.is_file() else _configuration_files(path)
    files = list(dict.fromkeys(files))
    if len(files) > MAX_CONFIGURATION_SOURCES:
        raise MaaFWConfigurationReuseError(
            f"配置来源文件超过 {MAX_CONFIGURATION_SOURCES} 个限制"
        )
    total_bytes = 0
    for file_path in files:
        try:
            if file_path.is_symlink() or not file_path.is_file():
                raise MaaFWConfigurationReuseError("配置来源必须是普通 JSON 文件")
            total_bytes += file_path.stat().st_size
        except OSError as exc:
            raise MaaFWConfigurationReuseError("无法读取配置来源文件信息") from exc
        if total_bytes > MAX_CONFIGURATION_TOTAL_BYTES:
            raise MaaFWConfigurationReuseError(
                f"配置来源总大小超过 {MAX_CONFIGURATION_TOTAL_BYTES // (1024 * 1024)} MiB 限制"
            )
    discovered: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for file_path in files:
        for source in _discover_file(file_path):
            key = (
                str(source["path"]),
                str(source["kind"]),
                _stable_json(source.get("selector") or {}),
            )
            if key in seen:
                continue
            seen.add(key)
            discovered.append(source)
            if len(discovered) >= MAX_CONFIGURATION_SOURCES:
                return discovered
    return discovered


def load_configuration_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """Reload one selected source and verify the discovery fingerprint."""

    path = Path(_required_text(source, "path", "配置文件路径")).resolve()
    kind = _required_text(source, "kind", "配置格式")
    selector = _mapping(source.get("selector"))
    expected_source_id = _required_text(source, "sourceId", "配置来源 ID")
    expected_fingerprint = _required_text(source, "fingerprint", "配置来源指纹")
    payload, file_digest = _read_json_object(path)
    fingerprint = _source_fingerprint(file_digest, kind, selector)
    source_id = _source_id(path, kind, selector)
    if source_id != expected_source_id:
        raise MaaFWConfigurationReuseError("配置来源标识不匹配，请重新发现并确认")
    if fingerprint != expected_fingerprint:
        raise MaaFWConfigurationReuseError(
            "外部 MaaFW 配置在预览后已发生变化，请重新发现并确认"
        )

    selected = _select_source_payload(payload, kind, selector)
    return {
        "source": {
            **dict(source),
            "path": str(path),
            "fingerprint": fingerprint,
        },
        "payload": selected,
    }


def plan_external_configuration_import(
    source: Mapping[str, Any],
    interface: Any,
    *,
    target: str,
) -> dict[str, Any]:
    """Build a JSON-only plan for one explicit external configuration."""

    if target not in {"project-and-first-user", "new-user"}:
        raise MaaFWConfigurationReuseError(f"不支持的配置导入目标：{target}")

    loaded = load_configuration_source(source)
    selected_source = _mapping(loaded["source"])
    payload = _mapping(loaded["payload"])
    index = _InterfaceIndex(interface)
    kind = str(selected_source.get("kind") or "")
    if kind == "mfaa-v1":
        mapped = _map_mfaa_v1(payload, index)
    elif kind == "mfaa-v2":
        mapped = _map_mfaa_v2(payload, index)
    elif kind == "mxu-v1":
        mapped = _map_mxu_v1(payload, index)
    else:
        raise MaaFWConfigurationReuseError(f"不支持的配置格式：{kind}")

    script_target = _mapping(mapped.get("scriptTargetConfig"))
    manual_actions = _mapping_list(mapped.get("manualActions"))
    if target == "new-user" and script_target:
        field_names = _leaf_field_names(script_target)
        manual_actions.append(
            {
                "kind": "script-fields-preserved",
                "blocking": False,
                "message": (
                    "外部配置还包含脚本级设置；新增用户不会覆盖当前项目绑定："
                    + "、".join(field_names)
                ),
            }
        )
        script_target = {}

    user_target = _mapping(mapped.get("userTargetConfig"))
    if not user_target:
        raise MaaFWConfigurationReuseError("所选来源没有可导入的用户配置")

    summary = _mapping(mapped.get("summary"))
    return {
        "schemaVersion": 1,
        "kind": "maafw.configuration-import-plan",
        "target": target,
        "source": selected_source,
        "sourceFingerprint": str(selected_source.get("fingerprint") or ""),
        "scriptTargetConfig": script_target,
        "userTargetConfigs": [user_target],
        "summary": summary,
        "warnings": _string_list(mapped.get("warnings")),
        "orphans": _mapping(mapped.get("orphans")),
        "manualActions": manual_actions,
        "readyToApply": not any(
            item.get("blocking") is True for item in manual_actions
        ),
        "preview": {
            "sourceLabel": str(selected_source.get("label") or "外部配置"),
            "format": kind,
            "scriptFields": _leaf_field_names(script_target),
            "userName": str(_nested(user_target, "Info", "Name") or "新用户"),
            "taskCount": int(summary.get("taskCount") or 0),
            "optionCount": int(summary.get("optionCount") or 0),
            "gamePathPresent": bool(_nested(script_target, "Game", "Path")),
            "adbDevicePresent": bool(
                _nested(script_target, "Device", "AdbAddress")
            ),
        },
    }


def plan_internal_user_copy(
    source_user: Mapping[str, Any],
    *,
    target_name: str | None = None,
) -> dict[str, Any]:
    """Build a clean business-config snapshot for an internal user copy."""

    source_config = _mapping(source_user.get("config"))
    if not source_config:
        raise MaaFWConfigurationReuseError("来源用户没有可复制配置")

    copied: dict[str, Any] = {}
    for group_name in ("Info", "Task", "Notify"):
        group = source_config.get(group_name)
        if isinstance(group, Mapping):
            copied[group_name] = copy.deepcopy(dict(group))

    info = copied.setdefault("Info", {})
    original_name = str(
        info.get("Name")
        or source_user.get("name")
        or "用户"
    ).strip()
    info["Name"] = str(target_name or f"{original_name} - 副本").strip()
    if not info["Name"]:
        info["Name"] = "用户 - 副本"

    # Runtime state and transaction/resource journals are intentionally reset.
    copied["Data"] = {
        "LastProxyDate": "2000-01-01",
        "ProxyTimes": 0,
        "IfPassCheck": True,
        "LastProxyStatus": "未知",
        "PeriodTaskRecords": "{}",
    }
    for group_name in tuple(copied):
        if group_name.casefold() in {
            "managedupgrade",
            "pendingupgrade",
            "journal",
            "lease",
            "references",
        }:
            copied.pop(group_name, None)

    return {
        "schemaVersion": 1,
        "kind": "maafw.configuration-copy-plan",
        "target": "new-user",
        "scriptTargetConfig": {},
        "userTargetConfigs": [copied],
        "summary": {
            "sourceUserId": str(source_user.get("id") or ""),
            "sourceUserName": original_name,
            "targetUserName": info["Name"],
        },
        "warnings": [],
        "orphans": {},
        "manualActions": [],
        "readyToApply": True,
        "preview": {
            "sourceLabel": original_name,
            "format": "internal-user",
            "scriptFields": [],
            "userName": info["Name"],
            "taskCount": _snapshot_task_count(copied),
            "optionCount": _snapshot_option_count(copied),
            "gamePathPresent": False,
            "adbDevicePresent": False,
        },
    }


def public_configuration_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return a preview without target payloads or raw orphan values."""

    return {
        key: copy.deepcopy(plan.get(key))
        for key in (
            "planId",
            "schemaVersion",
            "kind",
            "target",
            "sourceFingerprint",
            "summary",
            "warnings",
            "manualActions",
            "readyToApply",
            "preview",
            "expiresAt",
        )
        if key in plan
    } | {
        "orphans": _public_orphans(plan.get("orphans")),
    }


def stable_json_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def user_records_hash(records: Sequence[Mapping[str, Any]]) -> str:
    snapshot = [
        {
            "id": str(record.get("id") or ""),
            "type": str(record.get("type") or ""),
            "config": record.get("config") or {},
        }
        for record in records
    ]
    snapshot.sort(key=lambda item: item["id"])
    return stable_json_hash(snapshot)


def _configuration_files(root: Path) -> list[Path]:
    config_root = root / "config" if (root / "config").is_dir() else root
    result: list[Path] = []
    multi_config = config_root / "multi_config.json"
    if multi_config.is_file():
        result.extend(_multi_config_files(multi_config, config_root))

    for pattern in ("instances/*.json", "configs/*.json", "mxu-*.json"):
        for file_path in config_root.glob(pattern):
            result.append(file_path)
            if len(result) > MAX_CONFIGURATION_SOURCES:
                raise MaaFWConfigurationReuseError(
                    f"配置来源文件超过 {MAX_CONFIGURATION_SOURCES} 个限制"
                )

    # A selected config directory may contain only one directly placed source.
    if not result:
        for file_path in config_root.glob("*.json"):
            if file_path.name.casefold() not in {"interface.json", "maa_option.json"}:
                result.append(file_path)
                if len(result) > MAX_CONFIGURATION_SOURCES:
                    raise MaaFWConfigurationReuseError(
                        f"配置来源文件超过 {MAX_CONFIGURATION_SOURCES} 个限制"
                    )
    return sorted(
        dict.fromkeys(path.resolve() for path in result if path.is_file())
    )


def _multi_config_files(multi_config: Path, config_root: Path) -> list[Path]:
    try:
        payload, _digest = _read_json_object(multi_config)
    except MaaFWConfigurationReuseError:
        return []
    config_dir = config_root / "configs"
    result: list[Path] = []
    config_list = payload.get("config_list")
    if isinstance(config_list, Sequence) and not isinstance(
        config_list, (str, bytes, bytearray)
    ):
        for index, raw_item in enumerate(config_list):
            if index >= MAX_CONFIGURATION_SOURCES:
                raise MaaFWConfigurationReuseError(
                    f"配置来源文件超过 {MAX_CONFIGURATION_SOURCES} 个限制"
                )
            token = str(raw_item or "").strip()
            if not token or Path(token).name != token:
                continue
            names = [token]
            if not token.casefold().endswith(".json"):
                names.extend((f"{token}.json", f"c_{token}.json"))
            for name in names:
                candidate = config_dir / name
                if candidate.is_file():
                    result.append(candidate)
                    break
    if result:
        return result
    fallback: list[Path] = []
    for file_path in config_dir.glob("*.json"):
        fallback.append(file_path)
        if len(fallback) > MAX_CONFIGURATION_SOURCES:
            raise MaaFWConfigurationReuseError(
                f"配置来源文件超过 {MAX_CONFIGURATION_SOURCES} 个限制"
            )
    return sorted(fallback)


def _discover_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() != ".json" or not path.is_file():
        return []
    try:
        payload, file_digest = _read_json_object(path)
    except MaaFWConfigurationReuseError:
        return []

    if isinstance(payload.get("instances"), list):
        result: list[dict[str, Any]] = []
        for index, instance in enumerate(payload["instances"]):
            if len(result) >= MAX_CONFIGURATION_SOURCES:
                break
            if not isinstance(instance, Mapping):
                continue
            selector = {
                "index": index,
                "id": str(instance.get("id") or ""),
            }
            result.append(
                _source_descriptor(
                    path,
                    file_digest,
                    "mxu-v1",
                    selector,
                    instance,
                )
            )
        return result

    if "TaskItems" in payload or "InstanceName" in payload:
        return [
            _source_descriptor(path, file_digest, "mfaa-v1", {}, payload)
        ]
    if isinstance(payload.get("tasks"), list):
        return [
            _source_descriptor(path, file_digest, "mfaa-v2", {}, payload)
        ]
    return []


def _source_descriptor(
    path: Path,
    file_digest: str,
    kind: str,
    selector: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    label = str(
        payload.get("InstanceName")
        or payload.get("name")
        or payload.get("id")
        or path.stem
    ).strip()
    fingerprint = _source_fingerprint(file_digest, kind, selector)
    source_id = _source_id(path, kind, selector)
    stat = path.stat()
    return {
        "sourceId": source_id,
        "label": label or path.stem,
        "kind": kind,
        "path": str(path.resolve()),
        "selector": dict(selector),
        "fingerprint": fingerprint,
        "modifiedAt": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        "summary": _source_summary(payload),
    }


def _source_id(path: Path, kind: str, selector: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        f"{path.resolve()}\0{kind}\0{_stable_json(selector)}".encode("utf-8")
    ).hexdigest()[:24]


def _source_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    tasks = payload.get("tasks") or payload.get("TaskItems") or []
    saved_device = _mapping(payload.get("savedDevice"))
    adb_device = _mapping(payload.get("AdbDevice"))
    controller = str(
        payload.get("controllerName")
        or payload.get("CurrentControllerName")
        or ""
    )
    resource = str(payload.get("resourceName") or payload.get("Resource") or "")
    control_details: dict[str, Any] = {}
    if isinstance(tasks, list):
        (
            discovered_controller,
            discovered_resource,
            controller_options,
            resource_options,
        ) = _mfaa_v2_control_options(tasks)
        controller = controller or discovered_controller
        resource = resource or discovered_resource
        control_details = _selected_mfaa_v2_control_details(
            controller,
            controller_options,
            resource_options,
        )
    return {
        "taskCount": len(tasks) if isinstance(tasks, list) else 0,
        "controller": controller,
        "resource": resource,
        "hasGamePath": bool(
            payload.get("SoftwarePath")
            or saved_device.get("connectedProgramPath")
            or control_details.get("program_path")
        ),
        "hasAdbDevice": bool(
            adb_device.get("AdbSerial")
            or saved_device.get("adbDeviceName")
            or control_details.get("address")
        ),
    }


def _select_source_payload(
    payload: Mapping[str, Any],
    kind: str,
    selector: Mapping[str, Any],
) -> dict[str, Any]:
    if kind != "mxu-v1":
        return dict(payload)
    instances = payload.get("instances")
    if not isinstance(instances, list):
        raise MaaFWConfigurationReuseError("MXU 配置缺少 instances")
    wanted_id = str(selector.get("id") or "")
    if wanted_id:
        for instance in instances:
            if isinstance(instance, Mapping) and str(instance.get("id") or "") == wanted_id:
                return dict(instance)
    try:
        index = int(selector.get("index", -1))
    except (TypeError, ValueError):
        index = -1
    if 0 <= index < len(instances) and isinstance(instances[index], Mapping):
        return dict(instances[index])
    raise MaaFWConfigurationReuseError("MXU 配置实例已不存在，请重新发现")


def _map_mfaa_v1(
    payload: Mapping[str, Any],
    interface: "_InterfaceIndex",
) -> dict[str, Any]:
    warnings: list[str] = []
    manual_actions: list[dict[str, Any]] = []
    orphans: dict[str, Any] = {}
    info = _compact_mapping(
        {
            "Controller": payload.get("CurrentControllerName"),
            "Resource": payload.get("Resource"),
        }
    )
    adb = _mapping(payload.get("AdbDevice"))
    device = _compact_mapping(
        {
            "AdbScreencapMethods": _method_mask_or_none(
                adb.get("ScreencapMethods")
            ),
            "AdbInputMethods": _method_mask_or_none(adb.get("InputMethods")),
        }
    )
    game = _compact_mapping(
        {
            "WaitTime": _integer_or_none(payload.get("WaitSoftwareTime")),
        }
    )
    script_target = _compact_groups({"Info": info, "Device": device, "Game": game})

    if adb.get("Name") or adb.get("AdbSerial"):
        manual_actions.append(_emulator_confirmation_action(adb))
    if adb.get("AdbPath") or adb.get("AdbSerial") or payload.get("SoftwarePath"):
        manual_actions.append(_local_binding_confirmation_action())

    task_items = payload.get("TaskItems")
    task_rows: list[tuple[Mapping[str, Any], bool, Any]] = []
    if isinstance(task_items, list):
        for item in task_items:
            if not isinstance(item, Mapping):
                continue
            enabled = _external_bool(item.get("default_check"))
            task_rows.append((item, enabled, item.get("option")))
    snapshot, task_orphans = interface.build_snapshot(task_rows, option_style="mfaa-v1")
    if task_orphans:
        orphans["tasks"] = task_orphans
    if payload.get("pipeline_override"):
        orphans["pipelineOverride"] = copy.deepcopy(payload.get("pipeline_override"))

    if str(payload.get("BeforeTask") or "").strip() or str(
        payload.get("AfterTask") or ""
    ).strip():
        manual_actions.append(
            {
                "kind": "external-scripts-ignored",
                "blocking": False,
                "message": "外部前置/后置脚本不会导入或执行，请在新用户中重新选择可信脚本。",
            }
        )
    user_info = {
        "Name": payload.get("InstanceName") or "外部 MaaFW 配置",
        "IfScriptBeforeTask": False,
        "ScriptBeforeTask": "",
        "IfScriptAfterTask": False,
        "ScriptAfterTask": "",
    }
    user_target = {
        "Info": user_info,
        "Task": {"SelectedPreset": "", "TaskSnapshot": _stable_json(snapshot)},
    }
    return _mapped_result(
        script_target,
        user_target,
        snapshot,
        warnings,
        orphans,
        manual_actions,
    )


def _map_mfaa_v2(
    payload: Mapping[str, Any],
    interface: "_InterfaceIndex",
) -> dict[str, Any]:
    warnings: list[str] = []
    manual_actions: list[dict[str, Any]] = []
    orphans: dict[str, Any] = {}
    task_rows: list[tuple[Mapping[str, Any], bool, Any]] = []
    tasks = payload.get("tasks")
    (
        controller,
        resource,
        controller_options,
        resource_options,
    ) = _mfaa_v2_control_options(tasks if isinstance(tasks, list) else [])
    if isinstance(tasks, list):
        for item in tasks:
            if not isinstance(item, Mapping):
                continue
            options = _mapping(item.get("task_option"))
            raw_name = str(item.get("name") or "").strip().casefold()
            if (
                raw_name in {"controller", "resource", "控制器", "资源"}
                or "controller_type" in options
                or ("resource" in options and len(options) <= 2)
            ):
                continue
            task_rows.append((item, bool(item.get("is_checked")), options))

    snapshot, task_orphans = interface.build_snapshot(task_rows, option_style="mfaa-v2")
    if task_orphans:
        orphans["tasks"] = task_orphans
    known_task = payload.get("know_task")
    if known_task:
        orphans["knownTaskMetadata"] = copy.deepcopy(known_task)

    control_details = _selected_mfaa_v2_control_details(
        controller,
        controller_options,
        resource_options,
    )
    device, game, control_actions, control_orphans = _map_mfaa_v2_control_details(
        controller,
        control_details,
    )
    manual_actions.extend(control_actions)
    if control_orphans:
        orphans["controllerDetails"] = control_orphans

    script_target = _compact_groups(
        {
            "Info": _compact_mapping(
                {"Controller": controller, "Resource": resource}
            ),
            "Device": device,
            "Game": game,
        }
    )
    user_target = {
        "Info": {"Name": str(payload.get("name") or "外部 MaaFW 配置")},
        "Task": {"SelectedPreset": "", "TaskSnapshot": _stable_json(snapshot)},
    }
    return _mapped_result(
        script_target,
        user_target,
        snapshot,
        warnings,
        orphans,
        manual_actions,
    )


def _mfaa_v2_control_options(
    tasks: Sequence[Any],
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    controller = ""
    resource = ""
    controller_options: dict[str, Any] = {}
    resource_options: dict[str, Any] = {}
    for item in tasks:
        if not isinstance(item, Mapping):
            continue
        options = _mapping(item.get("task_option"))
        candidate_controller = str(options.get("controller_type") or "").strip()
        candidate_resource = str(options.get("resource") or "").strip()
        if candidate_controller and not controller:
            controller = candidate_controller
            controller_options = copy.deepcopy(options)
        if candidate_resource and not resource:
            resource = candidate_resource
            resource_options = copy.deepcopy(options)
    return controller, resource, controller_options, resource_options


def _selected_mfaa_v2_control_details(
    controller: str,
    controller_options: Mapping[str, Any],
    resource_options: Mapping[str, Any],
) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    normalized_controller = controller.casefold()
    for options in (resource_options, controller_options):
        for name, value in options.items():
            if (
                isinstance(value, Mapping)
                and str(name).strip().casefold() == normalized_controller
            ):
                selected.update(copy.deepcopy(dict(value)))

    if selected:
        return selected

    android_keys = {
        "adb_path",
        "address",
        "emulator_path",
        "screencap_methods",
        "input_methods",
        "device_index",
    }
    desktop_keys = {
        "program_path",
        "program_params",
        "hwnd",
        "win32_screencap_methods",
        "mouse_input_methods",
        "keyboard_input_methods",
        "window_name",
    }
    wants_android = any(
        token in normalized_controller
        for token in ("adb", "android", "安卓", "模拟器")
    )
    wants_desktop = any(
        token in normalized_controller
        for token in ("win32", "desktop", "桌面", "pc")
    )
    candidates: list[tuple[int, dict[str, Any]]] = []
    for options in (resource_options, controller_options):
        for value in options.values():
            if not isinstance(value, Mapping):
                continue
            fields = {str(key).casefold() for key in value}
            score = len(fields & android_keys) if wants_android else 0
            score = max(score, len(fields & desktop_keys) if wants_desktop else 0)
            if score:
                candidates.append((score, copy.deepcopy(dict(value))))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _map_mfaa_v2_control_details(
    controller: str,
    details: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if not details:
        return {}, {}, [], {}

    normalized_fields = {str(key).casefold() for key in details}
    is_android = bool(
        normalized_fields
        & {"adb_path", "address", "emulator_path", "screencap_methods", "input_methods"}
    )
    is_desktop = bool(
        normalized_fields
        & {
            "program_path",
            "program_params",
            "hwnd",
            "win32_screencap_methods",
            "mouse_input_methods",
            "keyboard_input_methods",
        }
    )
    manual_actions: list[dict[str, Any]] = []
    mapped_fields: set[str] = set()
    device: dict[str, Any] = {}
    game: dict[str, Any] = {}

    if is_android:
        device = _compact_mapping(
            {
                "AdbScreencapMethods": _method_mask_or_none(
                    details.get("screencap_methods")
                ),
                "AdbInputMethods": _method_mask_or_none(
                    details.get("input_methods")
                ),
            }
        )
        mapped_fields.update(
            {"adb_path", "address", "screencap_methods", "input_methods"}
        )
        if any(
            details.get(name) not in (None, "", [], {})
            for name in (
                "address",
                "emulator_path",
                "device_index",
                "name",
                "device_name",
            )
        ):
            manual_actions.append(
                _emulator_confirmation_action(
                    {
                        "Name": details.get("name")
                        or details.get("device_name")
                        or controller,
                        "adbDeviceName": details.get("address"),
                    }
                )
            )
        if details.get("adb_path") or details.get("address"):
            manual_actions.append(_local_binding_confirmation_action())

    if is_desktop:
        device.update(
            _compact_mapping(
                {
                    "Win32ScreencapMethod": _method_mask_or_none(
                        details.get("win32_screencap_methods")
                    ),
                    "Win32MouseMethod": _method_mask_or_none(
                        details.get("mouse_input_methods")
                    ),
                    "Win32KeyboardMethod": _method_mask_or_none(
                        details.get("keyboard_input_methods")
                    ),
                }
            )
        )
        game = _compact_mapping(
            {
                "WaitTime": _integer_or_none(details.get("wait_time")),
            }
        )
        mapped_fields.update(
            {
                "program_path",
                "program_params",
                "wait_time",
                "win32_screencap_methods",
                "mouse_input_methods",
                "keyboard_input_methods",
            }
        )
        if any(
            details.get(name) not in (None, "", [], {})
            for name in ("hwnd", "window_name", "class_name", "window_id")
        ):
            manual_actions.append(
                {
                    "kind": "desktop-window",
                    "blocking": False,
                    "message": (
                        "已导入桌面游戏路径和控制方式；旧窗口句柄不会复制，"
                        "运行时会按当前窗口重新解析。"
                    ),
                }
            )
        if details.get("program_path") or details.get("program_params"):
            manual_actions.append(_local_binding_confirmation_action())

    orphans = {
        str(key): copy.deepcopy(value)
        for key, value in details.items()
        if str(key).casefold() not in mapped_fields
        and value not in (None, "", [], {})
    }
    return (
        _compact_mapping(device),
        _compact_mapping(game),
        manual_actions,
        orphans,
    )


def _map_mxu_v1(
    payload: Mapping[str, Any],
    interface: "_InterfaceIndex",
) -> dict[str, Any]:
    warnings: list[str] = []
    manual_actions: list[dict[str, Any]] = []
    orphans: dict[str, Any] = {}
    saved_device = _mapping(payload.get("savedDevice"))
    address = saved_device.get("adbDeviceName")
    script_target = _compact_groups(
        {
            "Info": _compact_mapping(
                {
                    "Controller": payload.get("controllerName"),
                    "Resource": payload.get("resourceName"),
                }
            ),
            "Device": {},
            "Game": {},
        }
    )
    if address:
        manual_actions.append(_emulator_confirmation_action(saved_device))
    if address or saved_device.get("connectedProgramPath"):
        manual_actions.append(_local_binding_confirmation_action())
    if saved_device.get("windowName"):
        manual_actions.append(
            {
                "kind": "desktop-window",
                "blocking": False,
                "message": "旧 Win32 窗口句柄不会复制，请在脚本页重新选择本机窗口。",
            }
        )

    task_rows: list[tuple[Mapping[str, Any], bool, Any]] = []
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        for item in tasks:
            if isinstance(item, Mapping):
                task_rows.append(
                    (item, _external_bool(item.get("enabled")), item.get("optionValues"))
                )
    snapshot, task_orphans = interface.build_snapshot(task_rows, option_style="mxu-v1")
    if task_orphans:
        orphans["tasks"] = task_orphans
    pre_actions = payload.get("preActions")
    if isinstance(pre_actions, list) and pre_actions:
        orphans["preActions"] = copy.deepcopy(pre_actions)
        manual_actions.append(
            {
                "kind": "external-pre-actions",
                "blocking": False,
                "message": "外部自定义前置程序不会自动执行；已保留在未映射项中供人工确认。",
            }
        )

    user_target = {
        "Info": {"Name": str(payload.get("name") or "外部 MaaFW 配置")},
        "Task": {"SelectedPreset": "", "TaskSnapshot": _stable_json(snapshot)},
    }
    return _mapped_result(
        script_target,
        user_target,
        snapshot,
        warnings,
        orphans,
        manual_actions,
    )


class _InterfaceIndex:
    def __init__(self, interface: Any) -> None:
        self.interface = _json_mapping(interface, "ProjectInterface")
        task_values = self.interface.get("task")
        self.tasks = [dict(item) for item in task_values or [] if isinstance(item, Mapping)]
        option_values = self.interface.get("option")
        self.options = {
            str(name): dict(value)
            for name, value in _mapping(option_values).items()
            if isinstance(value, Mapping)
        }
        self.task_aliases = _named_aliases(self.tasks)
        self.option_aliases: dict[str, str] = {}
        for name, option in self.options.items():
            for alias in (name, option.get("label")):
                normalized = str(alias or "").strip().casefold()
                if normalized:
                    self.option_aliases.setdefault(normalized, name)

    def build_snapshot(
        self,
        rows: Sequence[tuple[Mapping[str, Any], bool, Any]],
        *,
        option_style: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        task_order: list[str] = []
        task_checked: dict[str, bool] = {}
        task_options: dict[str, dict[str, Any]] = {}
        orphans: list[dict[str, Any]] = []
        for raw_task, enabled, raw_options in rows:
            raw_name = str(
                raw_task.get("name")
                or raw_task.get("taskName")
                or raw_task.get("entry")
                or ""
            ).strip()
            raw_entry = str(raw_task.get("entry") or "").strip()
            task = self._match_task(raw_name, raw_entry)
            if task is None:
                if raw_name:
                    orphans.append({"task": raw_name, "reason": "ProjectInterface 未声明"})
                continue
            task_name = str(task.get("name") or "")
            if not task_name or task_name in task_order:
                continue
            task_order.append(task_name)
            task_checked[task_name] = bool(enabled)
            converted, option_orphans = self._convert_options(raw_options, option_style)
            if converted:
                task_options[task_name] = converted
            if option_orphans:
                orphans.append({"task": raw_name or task_name, "options": option_orphans})

        return (
            {
                "taskOrder": task_order,
                "taskChecked": task_checked,
                "taskOptions": task_options,
            },
            orphans,
        )

    def _match_task(self, name: str, entry: str) -> dict[str, Any] | None:
        for candidate in (name, entry):
            normalized = candidate.strip().casefold()
            if normalized and normalized in self.task_aliases:
                return self.task_aliases[normalized]
        return None

    def _convert_options(
        self,
        raw_options: Any,
        style: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        converted: dict[str, Any] = {}
        orphans: list[dict[str, Any]] = []
        if style == "mfaa-v1":
            items = raw_options if isinstance(raw_options, list) else []
            for raw_option in items:
                if not isinstance(raw_option, Mapping):
                    continue
                self._convert_option_item(raw_option, converted, orphans, style)
            return converted, orphans

        if not isinstance(raw_options, Mapping):
            return converted, orphans
        for raw_name, raw_value in raw_options.items():
            if str(raw_name).casefold() in {
                "controller_type",
                "resource",
                "_speedrun_config",
            }:
                continue
            self._convert_option_item(
                {"name": str(raw_name), "value": raw_value},
                converted,
                orphans,
                style,
            )
        return converted, orphans

    def _convert_option_item(
        self,
        raw_option: Mapping[str, Any],
        converted: dict[str, Any],
        orphans: list[dict[str, Any]],
        style: str,
    ) -> None:
        raw_name = str(raw_option.get("name") or "").strip()
        option_name = self.option_aliases.get(raw_name.casefold())
        if not option_name:
            if raw_name:
                orphans.append({"option": raw_name, "reason": "ProjectInterface 未声明"})
            return
        option = self.options[option_name]
        value = _convert_option_value(raw_option, option, style)
        if value is _MISSING:
            orphans.append({"option": raw_name, "reason": "值无法转换"})
        else:
            converted[option_name] = value

        sub_options = raw_option.get("sub_options")
        if isinstance(sub_options, list):
            for child in sub_options:
                if isinstance(child, Mapping):
                    self._convert_option_item(child, converted, orphans, style)


_MISSING = object()


def _convert_option_value(
    raw_option: Mapping[str, Any],
    option: Mapping[str, Any],
    style: str,
) -> Any:
    option_type = str(option.get("type") or "select").casefold()
    cases = [dict(item) for item in option.get("cases") or [] if isinstance(item, Mapping)]
    inputs = [dict(item) for item in option.get("inputs") or [] if isinstance(item, Mapping)]

    if style == "mfaa-v1":
        if option_type == "input":
            data = raw_option.get("data")
            if isinstance(data, Mapping):
                return {str(key): str(value) for key, value in data.items()}
            if data is not None and inputs:
                return {str(inputs[0].get("name") or "value"): str(data)}
        selected = raw_option.get("selected_cases")
        if option_type == "checkbox" and isinstance(selected, list):
            return [_match_case_name(item, cases) for item in selected if _match_case_name(item, cases)]
        if isinstance(selected, list) and selected:
            return _match_case_name(selected[0], cases)
        try:
            index = int(raw_option.get("index", 0))
        except (TypeError, ValueError):
            index = 0
        if 0 <= index < len(cases):
            return str(cases[index].get("name") or "")
        return _MISSING

    wrapped = raw_option.get("value")
    value_data = _mapping(wrapped) if isinstance(wrapped, Mapping) else {}
    raw_type = str(value_data.get("type") or "").casefold()
    if "caseName" in value_data:
        return _match_case_name(value_data.get("caseName"), cases)
    if "caseNames" in value_data:
        names = value_data.get("caseNames")
        if isinstance(names, list):
            return [name for item in names if (name := _match_case_name(item, cases))]
    if "values" in value_data:
        return _input_values(value_data.get("values"), inputs)
    if "value" in value_data:
        wrapped = value_data.get("value")
    elif value_data and raw_type:
        wrapped = value_data
    elif isinstance(wrapped, Mapping) and set(wrapped) == {"value"}:
        wrapped = wrapped.get("value")

    if option_type == "input":
        return _input_values(wrapped, inputs)
    if option_type == "checkbox":
        values = wrapped if isinstance(wrapped, list) else [wrapped]
        return [name for item in values if (name := _match_case_name(item, cases))]
    if isinstance(wrapped, bool):
        return _boolean_case(wrapped, cases)
    matched = _match_case_name(wrapped, cases)
    if matched:
        return matched
    if wrapped is not None and not cases:
        return str(wrapped)
    return _MISSING


def _input_values(raw_value: Any, inputs: Sequence[Mapping[str, Any]]) -> Any:
    if isinstance(raw_value, Mapping):
        return {str(key): str(value) for key, value in raw_value.items()}
    values = raw_value if isinstance(raw_value, list) else [raw_value]
    if not inputs or all(value is None for value in values):
        return _MISSING
    return {
        str(input_item.get("name") or index): str(values[index])
        for index, input_item in enumerate(inputs)
        if index < len(values) and values[index] is not None
    }


def _match_case_name(raw_value: Any, cases: Sequence[Mapping[str, Any]]) -> str:
    candidate = str(raw_value or "").strip()
    if not candidate:
        return ""
    normalized = candidate.casefold()
    for case in cases:
        for value in (case.get("name"), case.get("label")):
            if str(value or "").strip().casefold() == normalized:
                return str(case.get("name") or "")
    return ""


def _boolean_case(value: bool, cases: Sequence[Mapping[str, Any]]) -> Any:
    aliases = (
        {"yes", "是", "true", "on", "enable", "enabled"}
        if value
        else {"no", "否", "false", "off", "disable", "disabled"}
    )
    for case in cases:
        for raw in (case.get("name"), case.get("label")):
            if str(raw or "").strip().casefold() in aliases:
                return str(case.get("name") or "")
    if len(cases) == 2:
        return str(cases[0 if value else 1].get("name") or "")
    return _MISSING


def _mapped_result(
    script_target: Mapping[str, Any],
    user_target: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    warnings: list[str],
    orphans: Mapping[str, Any],
    manual_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    option_count = sum(
        len(value) for value in _mapping(snapshot.get("taskOptions")).values()
        if isinstance(value, Mapping)
    )
    return {
        "scriptTargetConfig": dict(script_target),
        "userTargetConfig": dict(user_target),
        "summary": {
            "taskCount": len(snapshot.get("taskOrder") or []),
            "enabledTaskCount": sum(
                1 for value in _mapping(snapshot.get("taskChecked")).values() if value is True
            ),
            "optionCount": option_count,
            "scriptFieldCount": len(_leaf_field_names(script_target)),
        },
        "warnings": warnings,
        "orphans": dict(orphans),
        "manualActions": manual_actions,
    }


def _emulator_confirmation_action(device: Mapping[str, Any]) -> dict[str, Any]:
    label = str(device.get("Name") or device.get("adbDeviceName") or "外部 ADB 设备")
    return {
        "kind": "emulator-selection",
        "blocking": False,
        "message": (
            f"已识别 {label} 的设备提示；宿主模拟器使用稳定 UUID，"
            "请在下一步“控制配置”中确认模拟器和实例。"
        ),
    }


def _local_binding_confirmation_action() -> dict[str, Any]:
    return {
        "kind": "local-binding",
        "blocking": False,
        "message": (
            "外部配置中的程序路径、启动参数、ADB 可执行文件和设备地址不会导入；"
            "请在脚本页按本机环境重新确认。"
        ),
    }


def _public_orphans(value: Any) -> dict[str, Any]:
    payload = _mapping(value)
    result: dict[str, Any] = {}
    for key, item in payload.items():
        if isinstance(item, list):
            result[str(key)] = [
                {
                    name: entry.get(name)
                    for name in ("task", "option", "reason")
                    if name in entry
                }
                if isinstance(entry, Mapping)
                else {"type": type(entry).__name__}
                for entry in item
            ]
        else:
            result[str(key)] = {"present": True, "type": type(item).__name__}
    return result


def _snapshot_task_count(config: Mapping[str, Any]) -> int:
    snapshot = _configuration_snapshot(config)
    return len(snapshot.get("taskOrder") or [])


def _snapshot_option_count(config: Mapping[str, Any]) -> int:
    snapshot = _configuration_snapshot(config)
    return sum(
        len(value)
        for value in _mapping(snapshot.get("taskOptions")).values()
        if isinstance(value, Mapping)
    )


def _configuration_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    raw = _nested(config, "Task", "TaskSnapshot")
    parsed = _parse_json_value(raw)
    return _mapping(parsed)


def _read_json_object(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise MaaFWConfigurationReuseError("配置来源必须是普通 JSON 文件")
    try:
        stat = path.stat()
    except OSError as exc:
        raise MaaFWConfigurationReuseError(f"无法读取配置文件：{path}") from exc
    if stat.st_size > MAX_CONFIGURATION_BYTES:
        raise MaaFWConfigurationReuseError(
            f"配置文件超过 {MAX_CONFIGURATION_BYTES // (1024 * 1024)} MiB 限制"
        )
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_CONFIGURATION_BYTES:
            raise MaaFWConfigurationReuseError(
                f"配置文件超过 {MAX_CONFIGURATION_BYTES // (1024 * 1024)} MiB 限制"
            )
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaaFWConfigurationReuseError(f"配置文件不是有效 UTF-8 JSON：{path}") from exc
    if not isinstance(payload, dict):
        raise MaaFWConfigurationReuseError(f"配置文件顶层必须是 JSON object：{path}")
    _validate_json_complexity(payload)
    return payload, hashlib.sha256(raw).hexdigest()


def _validate_json_complexity(payload: Mapping[str, Any]) -> None:
    nodes = 0
    stack: list[tuple[Any, int]] = [(payload, 1)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_CONFIGURATION_JSON_NODES:
            raise MaaFWConfigurationReuseError("配置文件结构过大，拒绝解析")
        if depth > MAX_CONFIGURATION_JSON_DEPTH:
            raise MaaFWConfigurationReuseError("配置文件嵌套过深，拒绝解析")
        if isinstance(value, Mapping):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)


def _source_fingerprint(
    file_digest: str,
    kind: str,
    selector: Mapping[str, Any],
) -> str:
    return hashlib.sha256(
        f"{file_digest}\0{kind}\0{_stable_json(selector)}".encode("utf-8")
    ).hexdigest()


def _json_mapping(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            payload = model_dump(mode="json", by_alias=True)
        except TypeError:
            payload = model_dump()
        if isinstance(payload, Mapping):
            return copy.deepcopy(dict(payload))
    raise MaaFWConfigurationReuseError(f"{label} 必须是 JSON object 或稳定 DTO")


def _named_aliases(items: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        payload = dict(item)
        for value in (payload.get("name"), payload.get("entry"), payload.get("label")):
            alias = str(value or "").strip().casefold()
            if alias:
                result.setdefault(alias, payload)
    return result


def _compact_mapping(
    payload: Mapping[str, Any],
    *,
    keep_false: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if value is False and not keep_false:
            continue
        result[str(key)] = value
    return result


def _compact_groups(payload: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {str(key): dict(value) for key, value in payload.items() if value}


def _integer_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        try:
            return int(float(value))
        except (TypeError, ValueError, OverflowError):
            return None


def _external_bool(value: Any) -> bool:
    """Parse external boolean fields without treating ``"false"`` as true."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return False


def _method_mask_or_none(value: Any) -> int | None:
    """Normalize MaaFramework uint64 JSON masks to the signed host form."""

    parsed = _integer_or_none(value)
    if parsed is None:
        return None
    if UINT64_SIGN_BIT <= parsed < UINT64_MODULUS:
        return parsed - UINT64_MODULUS
    return parsed


def _parse_json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _leaf_field_names(payload: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for group_name, group in payload.items():
        if isinstance(group, Mapping):
            result.extend(f"{group_name}.{name}" for name in group)
        else:
            result.append(str(group_name))
    return result


def _nested(payload: Mapping[str, Any], group: str, name: str) -> Any:
    group_value = payload.get(group)
    return group_value.get(name) if isinstance(group_value, Mapping) else None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        return []
    return [str(item) for item in value if str(item).strip()]


def _required_text(payload: Mapping[str, Any], key: str, label: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise MaaFWConfigurationReuseError(f"{label}不能为空（字段 {key}）")
    return value


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MaaFWConfigurationReuseError("配置导入契约只能包含 JSON 值") from exc


__all__ = [
    "MAX_CONFIGURATION_BYTES",
    "MAX_CONFIGURATION_SOURCES",
    "MaaFWConfigurationReuseError",
    "discover_configuration_sources",
    "load_configuration_source",
    "plan_external_configuration_import",
    "plan_internal_user_copy",
    "public_configuration_plan",
    "stable_json_hash",
    "user_records_hash",
]
