from __future__ import annotations

import copy
import json
import os
from importlib import metadata
from pathlib import Path
from typing import Any

import json5

from app.task.MaaFW.tools.core.automas_maafw_agent_env import (
    build_maafw_agent_command_plans,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    SUPPORTED_OPTION_TYPES,
    MaaFWController,
    MaaFWInterface,
    MaaFWOption,
    MaaFWPretask,
    MaaFWResource,
    MaaFWTask,
    MaaFWTaskOptionsByTask,
    MaaFWTaskOptionValue,
    find_pretask_by_task_name,
    is_pretask_task_name,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.task_config import (
    MaaFWTaskPresetSnapshot,
    build_interface_preset_snapshot,
    normalize_snapshot,
    normalize_task_execution_payload,
)
from app.utils import resource_path

from .models import (
    MaaFWPretaskRunPlan,
    MaaFWResolvedPath,
    MaaFWResourceBundlePlan,
    MaaFWRunPlan,
    MaaFWSkippedTaskPlan,
    MaaFWTaskRunPlan,
)
from .pipeline_override import MaaFWPipelineOverrideBuilder

PI_INTERFACE_VERSION = "v2.8.1"
PI_CLIENT_LANGUAGE = "zh_cn"
PI_CLIENT_NAME = "AUTO-MAS"
PROJECT_RUNTIME_MANIFEST_NAME = ".auto_mas_maafw_project.json"
MAAFW_DIRECT_CONTROLLER_TYPES = {"Adb", "Win32"}
# 并入自 mfwa：i18n 语言文件体积上限，避免超大文件拖垮计划构建
MAX_LANGUAGE_FILE_BYTES = 4 * 1024 * 1024
SENSITIVE_CONFIG_KEYWORDS = (
    "account",
    "credential",
    "email",
    "password",
    "passwd",
    "phone",
    "pwd",
    "secret",
    "token",
    "username",
    "令牌",
    "口令",
    "密钥",
    "密码",
    "手机号",
    "邮箱",
    "账户",
    "账号",
    "用户名",
    "凭据",
)


class MaaFWRunPlanError(ValueError):
    """Raised when a MaaFW project cannot be converted into a runnable plan."""


def build_maafw_run_plan(
    base_dir: str | Path,
    interface_model: MaaFWInterface | dict[str, Any],
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
    selected_preset: str | None = None,
    task_snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None = None,
    task_names: list[str] | None = None,
    task_options: dict[str, Any] | None = None,
    managed_env_root: str | Path | None = None,
) -> MaaFWRunPlan:
    interface = _coerce_interface(interface_model)
    resolved_base_dir = Path(base_dir).resolve()
    controller = _select_controller(interface, controller_name)
    resource = _select_resource(interface, resource_name, controller)
    selected_task_names, selected_task_options = _select_tasks(
        interface,
        controller_name=controller.name,
        resource_name=resource.name,
        selected_preset=selected_preset,
        task_snapshot=task_snapshot,
        task_names=task_names,
        task_options=task_options,
    )
    selected_pretask_names = [
        task_name
        for task_name in selected_task_names
        if is_pretask_task_name(task_name)
    ]
    selected_common_task_names = [
        task_name
        for task_name in selected_task_names
        if not is_pretask_task_name(task_name)
    ]
    task_map = {task.name: task for task in interface.task}
    controller_names = {controller.name}
    pipeline_builder = MaaFWPipelineOverrideBuilder(
        interface,
        controller_names=controller_names,
        resource_name=resource.name,
    )
    i18n_mapping = _load_i18n_mapping(resolved_base_dir, interface)

    runnable_tasks: list[MaaFWTaskRunPlan] = []
    skipped_tasks: list[MaaFWSkippedTaskPlan] = []
    for task_name in selected_common_task_names:
        task = task_map.get(task_name)
        if task is None:
            skipped_tasks.append(
                MaaFWSkippedTaskPlan(name=task_name, reason="任务不存在")
            )
            continue

        compatible, reason = _check_task_compatible(
            task,
            controller_names=controller_names,
            resource_name=resource.name,
        )
        if not compatible:
            skipped_tasks.append(
                MaaFWSkippedTaskPlan(
                    name=task.name,
                    label=_resolve_i18n_label(task.label, task.name, i18n_mapping),
                    entry=task.entry,
                    reason=reason,
                )
            )
            continue

        options = selected_task_options.get(task.name, {})
        pipeline_override = pipeline_builder.build_task_pipeline_override(
            task.name,
            options,
        )
        runnable_tasks.append(
            MaaFWTaskRunPlan(
                name=task.name,
                label=_resolve_i18n_label(task.label, task.name, i18n_mapping),
                entry=task.entry,
                options=options,
                pipelineOverride=pipeline_override,
                logOptions=_build_task_log_options(interface, options),
                overrideNodes=list(pipeline_override),
            )
        )

    if not runnable_tasks:
        raise MaaFWRunPlanError("当前 controller/resource 下没有可执行任务")

    return MaaFWRunPlan(
        path=str(resolved_base_dir),
        projectName=interface.name,
        projectLabel=interface.label,
        controllerName=controller.name,
        controllerType=controller.type,
        resourceName=resource.name,
        resource=_build_resource_bundle_plan(resolved_base_dir, resource, controller),
        nativePluginPaths=_build_native_plugin_paths(resolved_base_dir),
        agents=build_maafw_agent_command_plans(
            resolved_base_dir,
            interface.agent,
            managed_env_root=managed_env_root,
        ),
        pretasks=_build_pretask_plans(
            resolved_base_dir,
            interface,
            controller,
            resource,
            selected_pretask_names,
            selected_task_options,
        ),
        piEnv=_build_pi_env(resolved_base_dir, interface, controller, resource),
        tasks=runnable_tasks,
        skippedTasks=skipped_tasks,
    )


def _coerce_interface(
    interface_model: MaaFWInterface | dict[str, Any],
) -> MaaFWInterface:
    if isinstance(interface_model, MaaFWInterface):
        return interface_model
    if hasattr(interface_model, "model_dump"):
        return MaaFWInterface.model_validate(
            interface_model.model_dump(mode="json", by_alias=True)
        )
    return MaaFWInterface.model_validate(interface_model)


def _select_controller(
    interface_model: MaaFWInterface,
    controller_name: str | None,
) -> MaaFWController:
    if controller_name:
        controller = next(
            (
                item
                for item in interface_model.controller
                if item.name == controller_name
            ),
            None,
        )
        if controller is None:
            raise MaaFWRunPlanError(f"未找到 controller: {controller_name}")
        _ensure_direct_controller(controller)
        return controller

    if not interface_model.controller:
        raise MaaFWRunPlanError("interface 未声明 controller")
    controller = next(
        (
            item
            for item in interface_model.controller
            if item.type in MAAFW_DIRECT_CONTROLLER_TYPES
        ),
        None,
    )
    if controller is None:
        declared_types = ", ".join(
            f"{item.name}({item.type})" for item in interface_model.controller
        )
        raise MaaFWRunPlanError(
            "AUTO-MAS MaaFW Direct currently supports only Adb/Win32 "
            f"controllers; use the project UI for: {declared_types}"
        )
    return controller


def _ensure_direct_controller(controller: MaaFWController) -> None:
    if controller.type in MAAFW_DIRECT_CONTROLLER_TYPES:
        return
    raise MaaFWRunPlanError(
        "AUTO-MAS MaaFW Direct currently supports only Adb/Win32 "
        f"controllers; use the project UI for {controller.name}({controller.type})"
    )


def _select_resource(
    interface_model: MaaFWInterface,
    resource_name: str | None,
    controller: MaaFWController,
) -> MaaFWResource:
    if resource_name:
        resource = next(
            (item for item in interface_model.resource if item.name == resource_name),
            None,
        )
        if resource is None:
            raise MaaFWRunPlanError(f"未找到 resource: {resource_name}")
        if resource.controller and controller.name not in resource.controller:
            raise MaaFWRunPlanError(
                f"resource {resource.name} 不支持 controller {controller.name}"
            )
        return resource

    for resource in interface_model.resource:
        if not resource.controller or controller.name in resource.controller:
            return resource

    if not interface_model.resource:
        raise MaaFWRunPlanError("interface 未声明 resource")
    raise MaaFWRunPlanError(f"没有适用于 controller {controller.name} 的 resource")


def _select_tasks(
    interface_model: MaaFWInterface,
    *,
    controller_name: str,
    resource_name: str,
    selected_preset: str | None,
    task_snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
    task_names: list[str] | None,
    task_options: dict[str, Any] | None,
) -> tuple[list[str], MaaFWTaskOptionsByTask]:
    if task_names is not None:
        selected_names, selected_options = normalize_task_execution_payload(
            task_names,
            task_options,
            interface_model,
            controller_name=controller_name,
            resource_name=resource_name,
        )
        return selected_names, selected_options

    snapshot = _resolve_snapshot(
        interface_model,
        selected_preset=selected_preset,
        task_snapshot=task_snapshot,
    )
    selected_names = [
        task_name
        for task_name in snapshot.taskOrder
        if snapshot.taskChecked.get(task_name, False)
    ]
    selected_names, selected_options = normalize_task_execution_payload(
        selected_names,
        snapshot.taskOptions,
        interface_model,
        controller_name=controller_name,
        resource_name=resource_name,
    )
    return selected_names, selected_options


def _resolve_snapshot(
    interface_model: MaaFWInterface,
    *,
    selected_preset: str | None,
    task_snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
) -> MaaFWTaskPresetSnapshot:
    if task_snapshot is not None:
        return normalize_snapshot(task_snapshot, interface_model)

    if selected_preset:
        preset = next(
            (item for item in interface_model.preset if item.name == selected_preset),
            None,
        )
        if preset is None:
            raise MaaFWRunPlanError(f"未找到 preset: {selected_preset}")
        return normalize_snapshot(
            build_interface_preset_snapshot(interface_model, preset),
            interface_model,
        )

    if interface_model.preset:
        return normalize_snapshot(
            build_interface_preset_snapshot(interface_model, interface_model.preset[0]),
            interface_model,
        )

    return normalize_snapshot(
        {
            "taskOrder": [task.name for task in interface_model.task],
            "taskChecked": {
                task.name: bool(task.default_check) for task in interface_model.task
            },
            "taskOptions": {},
        },
        interface_model,
    )


def _check_task_compatible(
    task: MaaFWTask,
    *,
    controller_names: set[str],
    resource_name: str,
) -> tuple[bool, str]:
    if task.controller and not controller_names.intersection(task.controller):
        return False, f"当前控制器不受支持，支持: {', '.join(task.controller)}"
    if task.resource and resource_name not in task.resource:
        return False, f"当前资源不受支持，支持: {', '.join(task.resource)}"
    return True, ""


def _build_pretask_plans(
    base_dir: Path,
    interface_model: MaaFWInterface,
    controller: MaaFWController,
    resource: MaaFWResource,
    selected_names: list[str],
    task_options: MaaFWTaskOptionsByTask,
) -> list[MaaFWPretaskRunPlan]:
    plans: list[MaaFWPretaskRunPlan] = []
    i18n_mapping = _load_i18n_mapping(base_dir, interface_model)
    for task_name in selected_names:
        pretask = find_pretask_by_task_name(interface_model, task_name)
        if pretask is None:
            continue
        if pretask.controller and controller.name not in pretask.controller:
            continue
        if pretask.resource and resource.name not in pretask.resource:
            continue

        serialized_options = _collect_pretask_option_values(
            pretask,
            interface_model,
            task_options.get(task_name, {}),
            controller_name=controller.name,
            resource_name=resource.name,
        )
        args = list(pretask.args or [])
        if pretask.option:
            args.append(
                json.dumps(
                    serialized_options,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        plans.append(
            MaaFWPretaskRunPlan(
                name=task_name,
                label=_resolve_i18n_label(
                    pretask.label,
                    pretask.name or pretask.exec,
                    i18n_mapping,
                ),
                executable=_resolve_pretask_executable(base_dir, pretask.exec),
                # 并入自 mfwa：pretask 参数里的 {PROJECT_DIR} 也要展开，
                # 否则声明 args: ["{PROJECT_DIR}/x.json"] 的项目会拿到字面量
                args=[arg.replace("{PROJECT_DIR}", str(base_dir)) for arg in args],
                options=serialized_options,
            )
        )
    return plans


def _collect_pretask_option_values(
    pretask: MaaFWPretask,
    interface_model: MaaFWInterface,
    option_values: dict[str, MaaFWTaskOptionValue],
    *,
    controller_name: str,
    resource_name: str,
) -> dict[str, MaaFWTaskOptionValue]:
    result: dict[str, MaaFWTaskOptionValue] = {}

    def collect(option_name: str, lineage: set[str]) -> None:
        if option_name in lineage or option_name in result:
            return
        option = interface_model.option.get(option_name)
        if (
            option is None
            or option.type not in SUPPORTED_OPTION_TYPES
            or not _is_option_compatible(
                option,
                controller_name=controller_name,
                resource_name=resource_name,
            )
        ):
            return
        value = option_values.get(option_name)
        if value is None:
            return
        result[option_name] = copy.deepcopy(value)

        next_lineage = {*lineage, option_name}
        if option.type in {"select", "scan_select", "switch"} and isinstance(
            value, str
        ):
            active_case = next(
                (case for case in option.cases or [] if case.name == value), None
            )
            for nested_name in (
                active_case.option if active_case and active_case.option else []
            ):
                collect(nested_name, next_lineage)
        elif option.type == "checkbox" and isinstance(value, list):
            selected_names = set(value)
            for case in option.cases or []:
                if case.name not in selected_names:
                    continue
                for nested_name in case.option or []:
                    collect(nested_name, next_lineage)

    for option_name in pretask.option or []:
        collect(option_name, set())
    return result


def _is_option_compatible(
    option: MaaFWOption,
    *,
    controller_name: str,
    resource_name: str,
) -> bool:
    if option.controller and controller_name not in option.controller:
        return False
    if option.resource and resource_name not in option.resource:
        return False
    return True


def _resolve_pretask_executable(base_dir: Path, raw_exec: str) -> str:
    resolved = _resolve_project_path(base_dir, raw_exec)
    candidate = Path(resolved.resolved)
    # 并入自 mfwa：补 .exe 仅在 Windows 上进行，且越界判定用 resolve 后的路径，
    # 避免 symlink 绕过 _is_within_base_dir
    if not candidate.is_file() and not candidate.suffix and os.name == "nt":
        windows_candidate = candidate.with_suffix(".exe")
        if (
            _is_within_base_dir(windows_candidate.resolve(), base_dir)
            and windows_candidate.is_file()
        ):
            candidate = windows_candidate
    if not candidate.is_file():
        raise MaaFWRunPlanError(f"pretask 可执行文件不存在: {raw_exec}")
    return str(candidate)


def _build_task_log_options(
    interface_model: MaaFWInterface,
    options: dict[str, Any],
) -> dict[str, Any]:
    safe_options: dict[str, Any] = {}
    for option_name, value in options.items():
        option = interface_model.option.get(option_name)
        safe_options[option_name] = _sanitize_config_log_value(
            value,
            redact_all=bool(option and option.type == "input"),
            key=option_name,
        )
    return safe_options


def _sanitize_config_log_value(
    value: Any,
    *,
    redact_all: bool,
    key: str,
) -> Any:
    if redact_all or _is_sensitive_config_key(key):
        if isinstance(value, dict):
            return {
                str(child_key): _configured_value_marker(child_value)
                for child_key, child_value in value.items()
            }
        return _configured_value_marker(value)
    if isinstance(value, dict):
        return {
            str(child_key): _sanitize_config_log_value(
                child_value,
                redact_all=False,
                key=str(child_key),
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize_config_log_value(item, redact_all=False, key=key)
            for item in value
        ]
    return value


def _is_sensitive_config_key(key: str) -> bool:
    normalized = str(key).casefold()
    return any(keyword in normalized for keyword in SENSITIVE_CONFIG_KEYWORDS)


def _configured_value_marker(value: Any) -> str:
    if value is None:
        return "<未配置>"
    if isinstance(value, str):
        return "<已配置>" if value.strip() else "<未配置>"
    if isinstance(value, (dict, list, tuple, set)):
        return "<已配置>" if value else "<未配置>"
    return "<已配置>"


def _build_resource_bundle_plan(
    base_dir: Path,
    resource: MaaFWResource,
    controller: MaaFWController,
) -> MaaFWResourceBundlePlan:
    return MaaFWResourceBundlePlan(
        name=resource.name,
        label=resource.label,
        paths=[_resolve_project_path(base_dir, item) for item in resource.path],
        attachedPaths=[
            _resolve_project_path(base_dir, item)
            for item in controller.attach_resource_path or []
        ],
    )


def _build_native_plugin_paths(base_dir: Path) -> list[MaaFWResolvedPath]:
    manifest_path = base_dir / PROJECT_RUNTIME_MANIFEST_NAME
    declared_paths: list[str] | None = None
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MaaFWRunPlanError(
                f"解析 MaaFW project manifest 失败: {manifest_path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise MaaFWRunPlanError(
                f"MaaFW project manifest 必须是 JSON 对象: {manifest_path}"
            )
        raw_paths = payload.get("nativePluginPaths")
        runtime_payload = payload.get("runtime")
        if raw_paths is None and isinstance(runtime_payload, dict):
            raw_paths = runtime_payload.get("nativePluginPaths")
        if raw_paths is not None:
            if not isinstance(raw_paths, list) or not all(
                isinstance(item, str) and item.strip() for item in raw_paths
            ):
                raise MaaFWRunPlanError(
                    "nativePluginPaths 必须是字符串数组，且每项不能为空"
                )
            declared_paths = list(dict.fromkeys(item.strip() for item in raw_paths))

    if declared_paths is None:
        default_path = base_dir / "plugins"
        declared_paths = ["plugins"] if default_path.is_dir() else []
    return [_resolve_project_path(base_dir, item) for item in declared_paths]


def _resolve_project_path(base_dir: Path, raw_path: str) -> MaaFWResolvedPath:
    replaced = raw_path.replace("{PROJECT_DIR}", str(base_dir))
    candidate = Path(replaced)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    resolved_path = candidate.resolve()
    if not _is_within_base_dir(resolved_path, base_dir):
        raise MaaFWRunPlanError(f"路径越界，禁止访问项目目录之外的资源: {raw_path}")
    return MaaFWResolvedPath(
        raw=raw_path,
        resolved=str(resolved_path),
        exists=resolved_path.exists(),
        isFile=resolved_path.is_file(),
        isDir=resolved_path.is_dir(),
    )


def _is_within_base_dir(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _build_pi_env(
    base_dir: Path,
    interface_model: MaaFWInterface,
    controller: MaaFWController,
    resource: MaaFWResource,
) -> dict[str, str]:
    controller_payload = _resolve_i18n_payload(
        controller.model_dump(mode="json", exclude_none=True),
        base_dir,
        interface_model,
    )
    resource_payload = _resolve_i18n_payload(
        resource.model_dump(mode="json", exclude_none=True),
        base_dir,
        interface_model,
    )
    return {
        "PI_INTERFACE_VERSION": PI_INTERFACE_VERSION,
        "PI_CLIENT_NAME": PI_CLIENT_NAME,
        "PI_CLIENT_VERSION": _load_client_version(),
        "PI_CLIENT_LANGUAGE": PI_CLIENT_LANGUAGE,
        "PI_CLIENT_MAAFW_VERSION": _load_maafw_version(),
        "PI_VERSION": interface_model.version or "",
        "PI_CONTROLLER": json.dumps(
            controller_payload, ensure_ascii=False, separators=(",", ":")
        ),
        "PI_RESOURCE": json.dumps(
            resource_payload, ensure_ascii=False, separators=(",", ":")
        ),
    }


def _load_client_version() -> str:
    version_path = resource_path("version.json")
    try:
        data = json.loads(version_path.read_text(encoding="utf-8"))
        version = data.get("version")
        return version if isinstance(version, str) else ""
    except Exception:
        return ""


def _load_maafw_version() -> str:
    try:
        return f"v{metadata.version('maafw')}"
    except Exception:
        return ""


def _resolve_i18n_payload(
    payload: Any, base_dir: Path, interface_model: MaaFWInterface
) -> Any:
    mapping = _load_i18n_mapping(base_dir, interface_model)
    return _resolve_i18n_value(payload, mapping)


def _load_i18n_mapping(
    base_dir: Path, interface_model: MaaFWInterface
) -> dict[str, Any]:
    if not interface_model.languages:
        return {}
    language_file = interface_model.languages.get(PI_CLIENT_LANGUAGE)
    if not isinstance(language_file, str) or not language_file.strip():
        return {}
    language_path = _resolve_project_path(base_dir, language_file)
    if not language_path.exists or not language_path.isFile:
        return {}
    try:
        resolved_path = Path(language_path.resolved)
        if resolved_path.stat().st_size > MAX_LANGUAGE_FILE_BYTES:
            return {}
        data = json5.loads(resolved_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_i18n_value(value: Any, mapping: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_i18n_value(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_i18n_value(item, mapping) for item in value]
    if isinstance(value, str) and value.startswith("$"):
        translated = _lookup_i18n_text(value, mapping)
        if translated is not None:
            return translated
    return value


def _resolve_i18n_label(
    value: Any,
    fallback: str,
    mapping: dict[str, Any],
) -> str:
    resolved = _resolve_i18n_value(value, mapping)
    if (
        isinstance(resolved, str)
        and resolved.strip()
        and not resolved.lstrip().startswith("$")
    ):
        return resolved

    # MaaFW projects commonly keep task labels in a flat locale map while
    # leaving ``interface.json`` task.label unset (for example,
    # ``task.VisitFriends.label``).  Resolve that conventional key before
    # falling back to the machine-facing task id, so overview/run logs do not
    # expose raw IDs when a project already ships i18n data.
    normalized_fallback = str(fallback or "").strip()
    if normalized_fallback:
        for prefix in ("task", "pretask"):
            translated = _lookup_i18n_text(
                f"{prefix}.{normalized_fallback}.label",
                mapping,
            )
            if isinstance(translated, str) and translated.strip():
                return translated
    return fallback


def _lookup_i18n_text(key: str, mapping: dict[str, Any]) -> str | None:
    normalized_key = key[1:] if key.startswith("$") else key
    if not normalized_key:
        return None
    current: Any = mapping
    for part in normalized_key.split("."):
        if not isinstance(current, dict) or part not in current:
            current = None
            break
        current = current[part]
    if isinstance(current, str):
        return current
    flat_value = mapping.get(normalized_key)
    if isinstance(flat_value, str):
        return flat_value
    return None
