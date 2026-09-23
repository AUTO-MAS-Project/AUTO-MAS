from __future__ import annotations

import copy
import json
import logging
import os
import shutil
from importlib import metadata
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.agent_env import (
    build_maafw_agent_command_plans,
)
from app.task.MaaFW.tools.core.interface.loader import parse_json_text
from app.task.MaaFW.tools.core.interface.models import (
    SUPPORTED_OPTION_TYPES,
    MaaFWController,
    MaaFWInterface,
    MaaFWOption,
    MaaFWPretask,
    MaaFWResource,
    MaaFWTask,
    MaaFWTaskOptionsByTask,
    MaaFWTaskOptionValue,
    build_pretask_task_name,
    checkbox_count_problem,
    find_pretask_by_task_name,
    interface_load_warnings,
    is_pretask_task_name,
    iter_pretasks,
    resolve_task_instance_name,
)
from app.task.MaaFW.tools.core.interface.task_config import (
    MaaFWTaskPresetSnapshot,
    _build_option_defaults,
    build_default_task_instances,
    build_interface_preset_snapshot,
    normalize_snapshot,
    normalize_task_execution_payload,
)

from .models import (
    MaaFWPretaskRunPlan,
    MaaFWResolvedPath,
    MaaFWResourceBundlePlan,
    MaaFWRunPlan,
    MaaFWSkippedTaskPlan,
    MaaFWTaskRunPlan,
)
from .pipeline_override import (
    MaaFWCheckboxCountError,
    MaaFWInputValueError,
    MaaFWPipelineOverrideBuilder,
)

# 本模块会被运行池隔离 venv 里的 worker 进程导入（``runner``
# 的 ``__init__`` 连带 import 它），那个 venv 只装了 maafw 与项目依赖，没有
# 宿主的第三方包。所以这里**不能** ``from app.utils import resource_path``：
# ``app.utils`` 的包初始化会连锁拉起 ``app.utils.logger`` 里的 loguru，worker
# 一启动就 ``ModuleNotFoundError``；就算补上依赖，那个模块还会在导入期往
# ``Path.cwd()/debug`` 挂一份 app.log 的 sink，让 worker 变成第二个写同一份
# 轮转日志的进程。数法与 ``app/utils/paths.py`` 的 SOURCE_ROOT 同源，只是从
# 本文件自己的位置往上数六层。守卫见 tests/task/test_maafw_worker_import_isolation.py。
_SOURCE_ROOT = Path(__file__).resolve().parents[6]

logger = logging.getLogger("automas.maafw.runner.run_plan")
# 语言文件解析失败只提醒一次：同一份坏文件每次建计划都会再撞上。
_WARNED_LANGUAGE_FILES: set[str] = set()

# 注入给 agent 的 PI_INTERFACE_VERSION：Client 侧实际实现到的 PI 语义化版本（不是
# interface_version 那个固定的 2）。取「协议里要求 Client 必须做到的行为都已实现」的
# 最高版本，依据（对照 MaaFramework docs/zh_cn/3.3-ProjectInterfaceV2协议.md 的版本表）：
# - v2.1.0–v2.8.1：import / attach_resource_path、checkbox、option 适用性过滤、preset、
#   group、PI_* 环境变量、pretask（含 controller / resource 过滤与选项 JSON 参数）、
#   hotkey 都已实现；未做的只有「应」级的界面行为：resource.hash 不匹配时的提示
#   （v2.6.0）、setting 设置分区的渲染（v2.8.0）。
# - v2.9.0–v2.9.2：telemetry 协议写明「并非所有 Client 都会支持」，不上报即合规。
# - v2.10.0–v2.10.2：password 输入的掩码与加密存储（v2.10.0）、checkbox 的
#   min_count / max_count（v2.10.1）已实现，welcome 数组（v2.10.2）已能解析；
#   声明版本是否随之提升另行决定，这里仍停在 v2.9.2。
PI_INTERFACE_VERSION = "v2.9.2"
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
    task_ids: list[str] | None = None,
    task_options: dict[str, Any] | None = None,
    managed_env_root: str | Path | None = None,
) -> MaaFWRunPlan:
    interface = _coerce_interface(interface_model)
    resolved_base_dir = Path(base_dir).resolve()
    controller = _select_controller(interface, controller_name)
    resource = _select_resource(interface, resource_name, controller)
    selected_task_ids, selected_task_options = _select_tasks(
        interface,
        controller_name=controller.name,
        resource_name=resource.name,
        selected_preset=selected_preset,
        task_snapshot=task_snapshot,
        task_ids=task_ids,
        task_options=task_options,
    )
    selected_pretask_ids = [
        task_id for task_id in selected_task_ids if is_pretask_task_name(task_id)
    ]
    selected_common_task_ids = [
        task_id for task_id in selected_task_ids if not is_pretask_task_name(task_id)
    ]
    task_map = {task.name: task for task in interface.task}
    controller_names = {controller.name}
    pipeline_builder = MaaFWPipelineOverrideBuilder(
        interface,
        controller_names=controller_names,
        resource_name=resource.name,
    )
    i18n_mapping = _load_i18n_mapping(resolved_base_dir, interface)
    option_defaults, _ = _build_option_defaults(interface.option)
    resource_bundle = _build_resource_bundle_plan(
        resolved_base_dir, resource, controller
    )
    # 选中的资源在发行包里没有目录（导入时已记成「不可用的资源」，MaaDuDuL 的
    # zh_hant）：在宿主建计划 / 运行前检查时就报，别等拉起游戏或模拟器之后 runner
    # 加载资源时才失败。
    missing_path = next(
        (path for path in resource_bundle.paths if not path.exists), None
    )
    if missing_path is not None:
        resource_label = _resolve_i18n_label(
            resource.label, resource.name, i18n_mapping
        )
        raise MaaFWRunPlanError(
            f"资源「{resource_label}」的目录 {missing_path.raw} 不存在："
            "发行包里缺少这个资源目录，请在脚本设置里换一个资源"
        )

    runnable_tasks: list[MaaFWTaskRunPlan] = []
    skipped_tasks: list[MaaFWSkippedTaskPlan] = []
    input_warnings: list[str] = []
    # 队列元素是任务实例 id：同一个任务可以出现多次，每份各带自己的一套选项。
    for task_id in selected_common_task_ids:
        task_name = resolve_task_instance_name(task_id, task_map)
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

        options = selected_task_options.get(task_id, {})
        try:
            pipeline_override = pipeline_builder.build_task_pipeline_override(
                task.name,
                options,
            )
        except MaaFWCheckboxCountError as exc:
            raise MaaFWRunPlanError(
                _describe_checkbox_count_error(
                    exc,
                    _resolve_i18n_label(task.label, task.name, i18n_mapping),
                    interface,
                    i18n_mapping,
                )
            ) from exc
        # 值下发不了的 input 选项已被跳过覆盖：按任务拼成告警（只影响这个任务的这个选项）
        for input_error in pipeline_builder.input_errors:
            input_warnings.append(
                _describe_input_value_error(
                    input_error,
                    _resolve_i18n_label(task.label, task.name, i18n_mapping),
                    interface,
                    i18n_mapping,
                )
            )
        pipeline_builder.input_errors.clear()
        runnable_tasks.append(
            MaaFWTaskRunPlan(
                name=task.name,
                label=_resolve_i18n_label(task.label, task.name, i18n_mapping),
                entry=task.entry,
                options=options,
                pipelineOverride=pipeline_override,
                logOptions=_build_task_log_options(interface, options),
                overrideNodes=list(pipeline_override),
                nonDefaultOptions=_build_non_default_options(
                    interface, options, option_defaults, i18n_mapping
                ),
            )
        )

    if not runnable_tasks:
        raise MaaFWRunPlanError("当前 controller/resource 下没有可执行任务")

    builder_warnings = [*pipeline_builder.warnings, *input_warnings]
    for warning in builder_warnings:
        logger.warning("MaaFW 运行计划：%s", warning)
    # 加载 interface 时的告警（preset 引用不存在的 case、缺 import 文件……）以前只进后端
    # 日志；与建覆盖时跳过的项一起进计划，运行日志开头列一次（加载时已写过后端日志）。
    plan_warnings = list(
        dict.fromkeys([*interface_load_warnings(interface), *builder_warnings])
    )

    return MaaFWRunPlan(
        path=str(resolved_base_dir),
        projectName=interface.name,
        projectLabel=interface.label,
        controllerName=controller.name,
        controllerType=controller.type,
        controllerDisplay=_build_controller_display(controller),
        resourceName=resource.name,
        resource=resource_bundle,
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
            selected_pretask_ids,
            selected_task_options,
            i18n_mapping,
        ),
        piEnv=_build_pi_env(interface, controller, resource, i18n_mapping),
        tasks=runnable_tasks,
        skippedTasks=skipped_tasks,
        warnings=plan_warnings,
        i18n=i18n_mapping,
    )


def _describe_checkbox_count_error(
    exc: MaaFWCheckboxCountError,
    task_label: str,
    interface_model: MaaFWInterface,
    i18n_mapping: dict[str, Any],
) -> str:
    """勾选数不满足 checkbox 限制时给用户看的一句话：哪个任务、哪个选项、要几项、现在几项。"""

    option = interface_model.option.get(exc.option_name)
    option_label = (
        _resolve_i18n_label(option.label, exc.option_name, i18n_mapping)
        if option is not None
        else exc.option_name
    )
    if exc.max_count is None:
        requirement = f"至少需要选择 {exc.min_count} 项"
    elif exc.min_count <= 0:
        requirement = f"最多只能选择 {exc.max_count} 项"
    elif exc.min_count == exc.max_count:
        requirement = f"需要恰好选择 {exc.min_count} 项"
    else:
        requirement = f"需要选择 {exc.min_count}~{exc.max_count} 项"
    return (
        f"任务「{task_label}」的选项「{option_label}」{requirement}，"
        f"当前选了 {exc.selected} 项，请在用户配置的任务队列里调整后再运行"
    )


_INPUT_TYPE_NAMES = {
    "int": "整数",
    "integer": "整数",
    "float": "数字",
    "double": "数字",
    "number": "数字",
}


def _describe_input_value_error(
    exc: MaaFWInputValueError,
    task_label: str,
    interface_model: MaaFWInterface,
    i18n_mapping: dict[str, Any],
) -> str:
    """input 的值下发不了、覆盖已跳过时的告警：哪个任务、哪个选项（多字段时带字段名）、什么值。"""

    option = interface_model.option.get(exc.option_name)
    option_label = (
        _resolve_i18n_label(option.label, exc.option_name, i18n_mapping)
        if option is not None
        else exc.option_name
    )
    inputs = (option.inputs or []) if option is not None else []
    if len(inputs) > 1:
        field = next((item for item in inputs if item.name == exc.field_name), None)
        field_label = (
            _resolve_i18n_label(field.label, exc.field_name, i18n_mapping)
            if field is not None
            else exc.field_name
        )
        option_label = f"{option_label}」的「{field_label}"
    kind = _INPUT_TYPE_NAMES.get(
        exc.expected, "布尔值" if "bool" in exc.expected else exc.expected
    )
    skipped = "已跳过该选项的设置，这个任务按项目原本的流程跑"
    if exc.value is None:
        # 数字 / 布尔类型的输入没有「空」这个取值，项目又没给默认值（MAH 的 select_team
        # default 是空串）：只跳过这一个选项，说清去哪填。
        return (
            f"任务「{task_label}」的选项「{option_label}」需要填一个{kind}，"
            f"但没有填写、项目也没有给默认值，{skipped}；请在用户配置的任务队列里填写"
        )
    return (
        f"任务「{task_label}」的选项「{option_label}」的值 {exc.value} 不是{kind}，"
        f"{skipped}"
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


CONTROLLER_DISPLAY_FIELDS = (
    "display_short_side",
    "display_long_side",
    "display_expand",
    "display_raw",
)


def _build_controller_display(controller: MaaFWController) -> dict[str, Any]:
    """controller 的截图缩放声明原样摘出，交给 worker 在建控制器后下发。"""

    dumped = controller.model_dump(mode="json")
    return {
        name: dumped[name]
        for name in CONTROLLER_DISPLAY_FIELDS
        if dumped.get(name) is not None
    }


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


def select_snapshot_tasks(
    interface_model: MaaFWInterface,
    *,
    selected_preset: str | None,
    task_snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any]]:
    """把用户快照（或预设）归一化成「勾选的任务实例 id 列表 + 各自选项」。

    与 ``build_maafw_run_plan`` 走快照时的第一步完全相同；特调钩子在这一步之后、
    建计划之前装饰列表，再以 ``task_ids`` / ``task_options`` 建计划。
    """

    snapshot = _resolve_snapshot(
        interface_model,
        selected_preset=selected_preset,
        task_snapshot=task_snapshot,
    )
    selected_ids = [
        task_id
        for task_id in snapshot.taskOrder
        if snapshot.taskChecked.get(task_id, False)
    ]
    return selected_ids, dict(snapshot.taskOptions)


def _select_tasks(
    interface_model: MaaFWInterface,
    *,
    controller_name: str,
    resource_name: str,
    selected_preset: str | None,
    task_snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
    task_ids: list[str] | None,
    task_options: dict[str, Any] | None,
) -> tuple[list[str], MaaFWTaskOptionsByTask]:
    if task_ids is not None:
        selected_ids, selected_options = normalize_task_execution_payload(
            task_ids,
            task_options,
            interface_model,
            controller_name=controller_name,
            resource_name=resource_name,
        )
        return selected_ids, selected_options

    snapshot = _resolve_snapshot(
        interface_model,
        selected_preset=selected_preset,
        task_snapshot=task_snapshot,
    )
    selected_ids = [
        task_id
        for task_id in snapshot.taskOrder
        if snapshot.taskChecked.get(task_id, False)
    ]
    selected_ids, selected_options = normalize_task_execution_payload(
        selected_ids,
        snapshot.taskOptions,
        interface_model,
        controller_name=controller_name,
        resource_name=resource_name,
    )
    return selected_ids, selected_options


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

    # 按出现位置各自取 default_check：同名任务出现两次时，以前 {任务名: 勾选} 字典让后一次
    # （没勾）覆盖前一次，这个任务就从默认计划里消失了（MaaGFNeuralCloud 的收集任务奖励）。
    instances = build_default_task_instances(interface_model)
    return normalize_snapshot(
        {
            "taskOrder": [task_id for task_id, _ in instances],
            "taskChecked": {
                task_id: bool(task.default_check) for task_id, task in instances
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
    selected_ids: list[str],
    task_options: MaaFWTaskOptionsByTask,
    i18n_mapping: dict[str, Any],
) -> list[MaaFWPretaskRunPlan]:
    plans: list[MaaFWPretaskRunPlan] = []
    pretask_names = {
        build_pretask_task_name(pretask) for pretask in iter_pretasks(interface_model)
    }
    for task_id in selected_ids:
        task_name = resolve_task_instance_name(task_id, pretask_names)
        pretask = find_pretask_by_task_name(interface_model, task_name)
        if pretask is None:
            continue
        if pretask.controller and controller.name not in pretask.controller:
            continue
        if pretask.resource and resource.name not in pretask.resource:
            continue

        pretask_label = _resolve_i18n_label(
            pretask.label,
            pretask.name or pretask.exec,
            i18n_mapping,
        )
        try:
            serialized_options = _collect_pretask_option_values(
                pretask,
                interface_model,
                task_options.get(task_id, {}),
                controller_name=controller.name,
                resource_name=resource.name,
            )
        except MaaFWCheckboxCountError as exc:
            raise MaaFWRunPlanError(
                _describe_checkbox_count_error(
                    exc, pretask_label, interface_model, i18n_mapping
                )
            ) from exc
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
                label=pretask_label,
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
            selected_count = sum(
                1 for case in option.cases or [] if case.name in selected_names
            )
            problem = checkbox_count_problem(option, selected_count)
            if problem is not None:
                raise MaaFWCheckboxCountError(
                    option_name,
                    selected=selected_count,
                    min_count=problem[1],
                    max_count=problem[2],
                )
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


def _is_bare_command(raw_exec: str) -> bool:
    """``python`` / ``node.exe`` 这种不带路径的命令名（PI：exec 可以是系统 PATH 上的程序）。"""

    value = raw_exec.strip()
    return bool(value) and not any(
        marker in value for marker in ("/", "\\", ":", "{PROJECT_DIR}")
    )


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
    if candidate.is_file():
        return str(candidate)
    if _is_bare_command(raw_exec):
        # 项目目录里没有同名文件时按系统 PATH 找（PI 文档的示例就是 ``"exec": "python"``），
        # 解析成绝对路径再交给子进程：裸名原样交给 CreateProcess 的话，它先在父进程
        # （AUTO-MAS 宿主解释器）所在目录里找，``python`` 永远落到宿主自己的解释器上——
        # 与 agent 规划不把裸 ``python`` 交给 PATH 是同一个原因。
        found = shutil.which(raw_exec.strip())
        if found:
            return str(Path(found).resolve())
        raise MaaFWRunPlanError(
            f"pretask 可执行文件不存在: {raw_exec}（项目目录与系统 PATH 里都没有）"
        )
    raise MaaFWRunPlanError(f"pretask 可执行文件不存在: {raw_exec}")


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


def _build_non_default_options(
    interface_model: MaaFWInterface,
    options: dict[str, Any],
    option_defaults: dict[str, Any],
    i18n_mapping: dict[str, Any],
) -> dict[str, Any]:
    """挑出与 interface 默认值不同的选项，键值换成给人看的标签。

    默认值口径与 ``task_config._build_option_defaults`` 完全一致：select 类比
    ``default_case``，checkbox 比集合，input 的默认永远是空串（填了就算非默认），
    hotkey 比默认键位。脱敏规则与完整配置行相同：敏感项只显示 ``<已配置>``。
    ``options`` 里未在 interface 声明的键（旧配置残留）原样带出，宁多勿漏。
    """

    result: dict[str, Any] = {}
    for option_name, value in options.items():
        option = interface_model.option.get(option_name)
        if _is_default_option_value(option, value, option_defaults.get(option_name)):
            continue
        label = (
            _resolve_i18n_label(option.label, option_name, i18n_mapping)
            if option is not None
            else option_name
        )
        result[label] = _sanitize_config_log_value(
            _display_option_value(option, value, i18n_mapping),
            redact_all=bool(option and option.type == "input"),
            key=option_name,
        )
    return result


def _is_default_option_value(
    option: MaaFWOption | None, value: Any, default: Any
) -> bool:
    if option is None or default is None:
        return False
    if option.type == "checkbox":
        if not isinstance(value, list) or not isinstance(default, list):
            return value == default
        return set(map(str, value)) == set(map(str, default))
    if option.type == "input":
        if isinstance(value, dict):
            return all(not str(item or "").strip() for item in value.values())
        return not str(value or "").strip()
    return value == default


def _display_option_value(
    option: MaaFWOption | None, value: Any, i18n_mapping: dict[str, Any]
) -> Any:
    """把 case 名换成 case 标签；input / hotkey 的字典按输入项标签展开。"""

    if option is None:
        return value
    if option.type in {"select", "scan_select", "switch", "checkbox"}:
        case_labels = {
            case.name: _resolve_i18n_label(case.label, case.name, i18n_mapping)
            for case in option.cases or []
        }
        if isinstance(value, list):
            return [case_labels.get(str(item), str(item)) for item in value]
        return case_labels.get(str(value), value)
    if isinstance(value, dict):
        item_labels = {
            item.name: _resolve_i18n_label(item.label, item.name, i18n_mapping)
            for item in [*(option.inputs or []), *(option.hotkeys or [])]
        }
        return {
            item_labels.get(str(key), str(key)): item
            for key, item in value.items()
            if option.type != "input" or str(item or "").strip()
        }
    return value


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
    interface_model: MaaFWInterface,
    controller: MaaFWController,
    resource: MaaFWResource,
    i18n_mapping: dict[str, Any],
) -> dict[str, str]:
    controller_payload = _resolve_i18n_value(
        controller.model_dump(mode="json", exclude_none=True), i18n_mapping
    )
    resource_payload = _resolve_i18n_value(
        resource.model_dump(mode="json", exclude_none=True), i18n_mapping
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
    version_path = _SOURCE_ROOT / "res" / "version.json"
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
        # 走 loader 的 json→json5 快路径：绝大多数语言文件是严格 JSON，
        # 纯 Python 的 json5 解析同一份文件要慢三个数量级。
        data = parse_json_text(resolved_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        if language_file not in _WARNED_LANGUAGE_FILES:
            _WARNED_LANGUAGE_FILES.add(language_file)
            logger.warning(
                "MaaFW 语言文件解析失败，任务文案退回原始键: %s: %s",
                language_file,
                exc,
            )
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
