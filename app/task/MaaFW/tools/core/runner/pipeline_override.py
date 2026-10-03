from __future__ import annotations

import copy
import math
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import json5

from app.task.MaaFW.tools.core.interface.models import (
    SUPPORTED_OPTION_TYPES,
    MaaFWController,
    MaaFWInterface,
    MaaFWOption,
    MaaFWPipelineOverride,
    MaaFWResource,
    MaaFWTask,
    MaaFWTaskOptionValue,
    checkbox_count_problem,
    hotkey_placeholders,
    pipeline_template_strings,
)

from .hotkey import MaaFWHotkeyError, resolve_hotkey


class MaaFWCheckboxCountError(ValueError):
    """checkbox 的勾选数不满足 ``min_count`` / ``max_count``（PI v2.10.1）。

    只带机器可读的事实；给人看的整句由建计划的一方拼（它有任务与选项的显示名）。
    """

    def __init__(
        self,
        option_name: str,
        *,
        selected: int,
        min_count: int,
        max_count: int | None,
    ) -> None:
        self.option_name = option_name
        self.selected = selected
        self.min_count = min_count
        self.max_count = max_count
        super().__init__(
            f"选项 {option_name} 选了 {selected} 项，要求 "
            f"{min_count}~{'不限' if max_count is None else max_count} 项"
        )


#: password 字段下发失败时代替原值写进提示的文字（核心包不引宿主的 option_secrets）。
SECRET_VALUE_PLACEHOLDER = "（密码字段，已隐藏）"


class MaaFWInputValueError(ValueError):
    """input 字段的值下发不了：该填数字的地方填的不是数字，或者没填也没有默认值。

    与 ``MaaFWCheckboxCountError`` 同样只带事实（选项名、字段名、值、期望的类型），
    给人看的整句由建计划的一方拼（它有任务与选项的显示名）。``value`` 为 None 表示没填。
    ``secret``：字段是 password（PI v2.10.0），原值不进异常——这句话会进运行日志与后端
    日志；``value`` 换成 ``SECRET_VALUE_PLACEHOLDER``。
    """

    def __init__(
        self,
        option_name: str,
        field_name: str,
        *,
        expected: str,
        value: str | None,
        secret: bool = False,
    ) -> None:
        self.option_name = option_name
        self.field_name = field_name
        self.expected = expected
        self.secret = secret
        self.value = SECRET_VALUE_PLACEHOLDER if secret and value is not None else value
        detail = (
            "未填写且 interface 未声明默认值" if value is None else f"值 {self.value}"
        )
        super().__init__(
            f"选项 {option_name} 的字段 {field_name} 需要 {expected} 值，{detail}"
        )


class MaaFWHotkeyValueError(ValueError):
    """hotkey 选项的覆盖下发不了：键位映射不成当前控制器的键码，或与 pipeline 的占位符对不上。

    与 ``MaaFWInputValueError`` 同样只带事实（选项名、字段名、值、原因），给人看的整句由
    建计划的一方拼（它有选项与字段的显示名）。``field_name`` / ``value`` 为空表示问题不在某个
    字段的取值上（例如 pipeline 里的占位符写法不对、控制器没有 hotkey 映射）。
    ``fallback`` 非空表示这一个字段已改用项目默认键位，选项的其余字段照常下发；为空表示
    整个选项的覆盖已跳过。
    """

    def __init__(
        self,
        option_name: str,
        field_name: str,
        *,
        value: str | None,
        reason: str,
        fallback: str | None = None,
    ) -> None:
        self.option_name = option_name
        self.field_name = field_name
        self.value = value
        self.reason = reason
        self.fallback = fallback
        target = f"{option_name}.{field_name}" if field_name else option_name
        detail = f"值 {value!r} " if value is not None else ""
        super().__init__(f"快捷键 {target} {detail}无法下发：{reason}")


def _parse_integer_text(text: str) -> int | None:
    """整数，或整数形态的小数 / 科学计数（``99.0``、``1e20``）；别的返回 None。"""

    stripped = text.strip()
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        number = Decimal(stripped)
    except InvalidOperation:
        return None
    if not number.is_finite() or number != number.to_integral_value():
        return None
    return int(number)


def deep_merge_pipeline_override(
    base: MaaFWPipelineOverride | None,
    override: MaaFWPipelineOverride | None,
) -> MaaFWPipelineOverride:
    merged: MaaFWPipelineOverride = copy.deepcopy(base) if base else {}
    if not override:
        return merged

    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge_pipeline_override(existing, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


class MaaFWPipelineOverrideBuilder:
    def __init__(
        self,
        interface_model: MaaFWInterface,
        *,
        controller_names: set[str],
        resource_name: str | None,
    ) -> None:
        self.interface_model = interface_model
        self.controller_names = controller_names
        self.resource_name = resource_name
        # 建覆盖时跳过的项（给用户看的原因）；调用方把它带进运行计划的告警。
        self.warnings: list[str] = []
        # 因为值下发不了而整段跳过覆盖的 input 选项（没填又没默认值、该填数字却不是）。
        # 只带事实，调用方按任务拼成告警后清空——它知道当前是哪个任务、显示名是什么。
        self.input_errors: list[MaaFWInputValueError] = []
        # 因为键位下发不了而整段跳过覆盖的 hotkey 选项，用法同 ``input_errors``。
        self.hotkey_errors: list[MaaFWHotkeyValueError] = []

    def build_task_pipeline_override(
        self,
        task_name: str,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> MaaFWPipelineOverride:
        task_definition = self._get_task_definition(task_name)
        if task_definition is None:
            return {}

        merged = copy.deepcopy(task_definition.pipeline_override) or {}
        for option_names in self._task_option_groups(task_definition):
            merged = deep_merge_pipeline_override(
                merged,
                self._build_option_group_override(option_names, options),
            )
        return merged

    def active_option_names(
        self,
        task_name: str,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> list[str]:
        """这个任务建覆盖时实际会生效的选项名（按出现顺序去重）。

        与 ``build_task_pipeline_override`` 同一套口径：global_option → 当前 resource 的
        option → 当前 controller 的 option → task.option，过滤掉未声明 / 不支持的类型 /
        不适用于当前 controller、resource 的选项，select / switch 展开当前选中 case 的子选项，
        checkbox 展开勾选 case 的子选项。不做勾选数校验、不解析值，没有副作用。
        """

        task_definition = self._get_task_definition(task_name)
        if task_definition is None:
            return []
        names: list[str] = []
        for option_names in self._task_option_groups(task_definition):
            self._collect_active_option_names(option_names, options, set(), names)
        return names

    def check_hotkey_value(self, option_name: str, field_name: str, value: str) -> None:
        """按当前控制器检查一个 hotkey 字段的取值能不能下发；不能就抛 ``MaaFWHotkeyError``。

        与建覆盖时同一套检查：映射成当前控制器的键码，并且 pipeline 引用到的
        ``{字段.modifierN}`` 这个键位都有。字段不是这个 option 声明的也抛。
        """

        option = self.interface_model.option.get(option_name)
        hotkey_item = next(
            (
                item
                for item in (option.hotkeys or [] if option is not None else [])
                if item.name == field_name
            ),
            None,
        )
        if option is None or option.type != "hotkey" or hotkey_item is None:
            raise MaaFWHotkeyError(f"未声明的快捷键字段: {option_name}.{field_name}")
        # 占位符写法不合规是 interface 的问题（建覆盖时另报），这里只看值本身。
        referenced_values = _hotkey_referenced_values(
            hotkey_item.name, pipeline_template_strings(option.pipeline_override or {})
        ) & hotkey_placeholders(hotkey_item.name)
        _resolve_hotkey_placeholders(
            hotkey_item.name,
            value,
            self._get_active_controller_type(),
            referenced_values,
        )

    def _task_option_groups(self, task_definition: MaaFWTask) -> list[list[str]]:
        resource_definition = self._get_resource_definition()
        controller_option_names: list[str] = []
        for controller in self._get_active_controller_definitions():
            if controller.option:
                controller_option_names.extend(controller.option)
        return [
            self.interface_model.global_option or [],
            resource_definition.option
            if resource_definition and resource_definition.option
            else [],
            controller_option_names,
            task_definition.option or [],
        ]

    def _collect_active_option_names(
        self,
        option_names: list[str],
        options: dict[str, MaaFWTaskOptionValue],
        lineage: set[str],
        result: list[str],
    ) -> None:
        for option_name in option_names:
            option = self.interface_model.option.get(option_name)
            if (
                option is None
                or option.type not in SUPPORTED_OPTION_TYPES
                or not self._is_option_active_for_context(option)
                or option_name in lineage
            ):
                continue
            if option_name not in result:
                result.append(option_name)
            next_lineage = {*lineage, option_name}
            if option.type in {"select", "switch"} and option.cases:
                active_case_name = self._normalize_choice_value(
                    option_name, option, options
                )
                active_case = next(
                    (case for case in option.cases if case.name == active_case_name),
                    None,
                )
                if active_case and active_case.option:
                    self._collect_active_option_names(
                        active_case.option, options, next_lineage, result
                    )
            elif option.type == "checkbox" and option.cases:
                selected_case_names = set(
                    self._normalize_checkbox_values(option_name, option, options)
                )
                for case in option.cases:
                    if case.name in selected_case_names and case.option:
                        self._collect_active_option_names(
                            case.option, options, next_lineage, result
                        )

    def _get_task_definition(self, task_name: str) -> MaaFWTask | None:
        return next(
            (task for task in self.interface_model.task if task.name == task_name), None
        )

    def _get_resource_definition(self) -> MaaFWResource | None:
        if self.resource_name is None:
            return None
        return next(
            (
                resource
                for resource in self.interface_model.resource
                if resource.name == self.resource_name
            ),
            None,
        )

    def _get_active_controller_definitions(self) -> list[MaaFWController]:
        return [
            controller
            for controller in self.interface_model.controller
            if controller.name in self.controller_names
        ]

    def _get_active_controller_type(self) -> str:
        controller_types = {
            controller.type for controller in self._get_active_controller_definitions()
        }
        if len(controller_types) != 1:
            raise MaaFWHotkeyError("hotkey 键码映射需要且只能选择一个 controller")
        return next(iter(controller_types))

    def _is_option_active_for_context(self, option: MaaFWOption) -> bool:
        if option.controller and not self.controller_names.intersection(
            option.controller
        ):
            return False
        if option.resource and (
            self.resource_name is None or self.resource_name not in option.resource
        ):
            return False
        return True

    def _normalize_choice_value(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> str:
        case_names = [case.name for case in option.cases or []]
        default_value = (
            option.default_case if isinstance(option.default_case, str) else ""
        )
        if default_value not in case_names:
            default_value = case_names[0] if case_names else ""

        raw_value = options.get(option_name)
        if isinstance(raw_value, str) and raw_value in case_names:
            return raw_value
        return default_value

    def _normalize_checkbox_values(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> list[str]:
        case_order = [case.name for case in option.cases or []]
        default_values = (
            option.default_case if isinstance(option.default_case, list) else []
        )
        raw_value = options.get(option_name)

        if raw_value is None:
            selected_values = [
                value for value in default_values if isinstance(value, str)
            ]
        elif isinstance(raw_value, list):
            selected_values = [value for value in raw_value if isinstance(value, str)]
        elif isinstance(raw_value, str):
            try:
                parsed_value = json5.loads(raw_value)
            except Exception:
                parsed_value = [raw_value] if raw_value in case_order else []
            selected_values = (
                [value for value in parsed_value if isinstance(value, str)]
                if isinstance(parsed_value, list)
                else []
            )
        else:
            selected_values = []

        selected_set = set(selected_values)
        return [case_name for case_name in case_order if case_name in selected_set]

    def _coerce_input_value(
        self,
        raw_value: str,
        pipeline_type: str | None,
        default: object = None,
        *,
        option_name: str = "",
        field_name: str = "",
        secret: bool = False,
    ) -> tuple[object, str]:
        normalized_type = (pipeline_type or "string").lower()
        if normalized_type not in {"string", "str", ""} and not raw_value.strip():
            # 非字符串类型没有「空」这个取值。未填写时必须回落到 interface 声明的
            # default —— 那是个真数字（MaaEnd 的 SupplyPlanLimit 默认 260、
            # CloseGamePCGameSettingResolutionWidth 默认 1280），不是「占位」那种
            # 哨兵，所以回落不会重演兑换码那个坑。字符串走不到这里：空串对它是
            # 合法取值（M9A 的兑换码没填就该是空）。
            fallback = "" if default is None else str(default).strip()
            if not fallback:
                raise MaaFWInputValueError(
                    option_name or "?",
                    field_name or "?",
                    expected=normalized_type,
                    value=None,
                )
            raw_value = fallback
        if normalized_type in {"bool", "boolean"}:
            typed_value = raw_value.lower() in {"true", "1", "yes", "y", "on"}
            return typed_value, "true" if typed_value else "false"
        if normalized_type in {"int", "integer"}:
            # 整数形态的小数（「99.0」「1e20」，preset / 默认值里写成数字时常见）规范成整数；
            # 确实不是整数的报清楚是哪个选项、什么值，不抛 int() 那句没有上下文的原文。
            integer = _parse_integer_text(raw_value)
            if integer is None:
                raise MaaFWInputValueError(
                    option_name or "?",
                    field_name or "?",
                    expected=normalized_type,
                    value=raw_value,
                    secret=secret,
                )
            return integer, str(integer)
        if normalized_type in {"float", "double", "number"}:
            try:
                typed_value = float(raw_value)
            except ValueError:
                typed_value = math.nan
            if not math.isfinite(typed_value):
                raise MaaFWInputValueError(
                    option_name or "?",
                    field_name or "?",
                    expected=normalized_type,
                    value=raw_value,
                    secret=secret,
                )
            return typed_value, str(typed_value)
        return raw_value, raw_value

    def _substitute_placeholders(
        self,
        value: Any,
        typed_replacements: dict[str, object],
        text_replacements: dict[str, str],
    ) -> Any:
        if isinstance(value, dict):
            return {
                key: self._substitute_placeholders(
                    nested_value, typed_replacements, text_replacements
                )
                for key, nested_value in value.items()
            }
        if isinstance(value, list):
            return [
                self._substitute_placeholders(
                    item, typed_replacements, text_replacements
                )
                for item in value
            ]
        if isinstance(value, str):
            if value in typed_replacements:
                return copy.deepcopy(typed_replacements[value])
            substituted = value
            for placeholder, replacement in text_replacements.items():
                substituted = substituted.replace(placeholder, replacement)
            return substituted
        return copy.deepcopy(value)

    def _assign_scan_select_attach_value(
        self,
        value: Any,
        option_name: str,
        selected_value: str,
    ) -> Any:
        if isinstance(value, dict):
            copied = {
                key: self._assign_scan_select_attach_value(
                    nested_value, option_name, selected_value
                )
                for key, nested_value in value.items()
            }
            attach_value = copied.get("attach")
            if isinstance(attach_value, dict) and option_name in attach_value:
                updated_attach = copy.deepcopy(attach_value)
                updated_attach[option_name] = selected_value
                copied["attach"] = updated_attach
            return copied
        if isinstance(value, list):
            return [
                self._assign_scan_select_attach_value(item, option_name, selected_value)
                for item in value
            ]
        return copy.deepcopy(value)

    def _build_input_override(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> MaaFWPipelineOverride:
        if not option.pipeline_override or not option.inputs:
            return {}

        typed_replacements: dict[str, object] = {}
        text_replacements: dict[str, str] = {}
        for input_item in option.inputs:
            raw_option_value = options.get(option_name)
            # 用户没填就当空，**不回退到 interface 的 default**。
            #
            # interface 里 input 的 default 是「用户打开该项后 UI 预填的提示值」，
            # 不是「没配时该应用的值」：M9A 的 自定义兑换码 default 就是字面量
            # 「占位」，MFAAvalonia 自己的配置里存的是空串。真机上把「占位」当真
            # 兑换码发出去，游戏兑换不掉，该任务直接卡死。
            #
            # 需要哨兵默认值的选项，interface 作者是写在 switch 的 case override
            # 里的（如 自定义吃糖次数=No -> EatCandyStart.max_hit=114514），
            # 不依赖 input default，因此这里置空不会误伤它们。
            raw_text = ""
            if isinstance(raw_option_value, dict):
                field_value = raw_option_value.get(input_item.name)
                if isinstance(field_value, str):
                    raw_text = field_value
            elif isinstance(raw_option_value, str):
                raw_text = raw_option_value
            elif isinstance(raw_option_value, list):
                raw_text = raw_option_value[0] if raw_option_value else ""

            try:
                typed_value, text_value = self._coerce_input_value(
                    raw_text,
                    input_item.pipeline_type,
                    input_item.default,
                    option_name=option_name,
                    field_name=input_item.name,
                    secret=bool(input_item.password),
                )
            except MaaFWInputValueError as exc:
                # 与 hotkey 没有默认值时同一口径：这个选项的覆盖整段跳过（半替换会把
                # 字面量 "{字段}" 塞进 pipeline），任务按项目原 pipeline 跑，不让整轮
                # 失败（MXU 填 0、CFA 失败时保留原值，也都不让整轮失败）。
                self.input_errors.append(exc)
                return {}
            placeholder = f"{{{input_item.name}}}"
            typed_replacements[placeholder] = typed_value
            text_replacements[placeholder] = text_value

        return cast(
            MaaFWPipelineOverride,
            self._substitute_placeholders(
                option.pipeline_override,
                typed_replacements,
                text_replacements,
            ),
        )

    def _build_hotkey_override(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> MaaFWPipelineOverride:
        if not option.pipeline_override or not option.hotkeys:
            return {}

        template_strings = pipeline_template_strings(option.pipeline_override)
        raw_option_value = options.get(option_name)
        typed_replacements: dict[str, object] = {}
        try:
            controller_type = self._get_active_controller_type()
        except MaaFWHotkeyError as exc:
            self.hotkey_errors.append(
                MaaFWHotkeyValueError(option_name, "", value=None, reason=str(exc))
            )
            return {}

        for hotkey_item in option.hotkeys:
            referenced_values = _hotkey_referenced_values(
                hotkey_item.name, template_strings
            )
            if not referenced_values:
                continue
            invalid_templates = referenced_values - hotkey_placeholders(
                hotkey_item.name
            )
            if invalid_templates:
                # interface 写法问题，与用户填的值无关：同样只跳过这个选项的覆盖。
                self.hotkey_errors.append(
                    MaaFWHotkeyValueError(
                        option_name,
                        hotkey_item.name,
                        value=None,
                        reason="hotkey 占位符必须作为完整值使用: "
                        + ", ".join(sorted(invalid_templates)),
                    )
                )
                return {}

            raw_text = hotkey_item.default or ""
            if isinstance(raw_option_value, dict):
                field_value = raw_option_value.get(hotkey_item.name)
                if isinstance(field_value, str):
                    raw_text = field_value
            if not raw_text.strip():
                # 项目没给 default、用户也没设：这一个快捷键选项的覆盖整段跳过（半替换
                # 会把字面量 "{K}" 塞进 pipeline），任务按项目原始 pipeline 跑，不让整次
                # 运行失败。
                warning = (
                    f"快捷键 {option_name}.{hotkey_item.name} 没有默认值也未设置，"
                    "已跳过该选项的 pipeline 覆盖"
                )
                if warning not in self.warnings:
                    self.warnings.append(warning)
                return {}

            try:
                values = _resolve_hotkey_placeholders(
                    hotkey_item.name, raw_text, controller_type, referenced_values
                )
            except MaaFWHotkeyError as exc:
                # 快照 / 预设 / 外壳导入里的键位映射不了：这一个字段改用项目默认键位，同一
                # 选项的其余字段（含叠上来的脚本级键位）照常下发；默认键位也用不了时才跳过
                # 整个选项的覆盖（半替换会把字面量 "{K}" 塞进 pipeline），任务按项目原始
                # pipeline 跑。两种情况都不让整轮失败。
                fallback = hotkey_item.default or ""
                fallback_values = None
                if fallback.strip() and fallback != raw_text:
                    try:
                        fallback_values = _resolve_hotkey_placeholders(
                            hotkey_item.name,
                            fallback,
                            controller_type,
                            referenced_values,
                        )
                    except MaaFWHotkeyError:
                        fallback_values = None
                self.hotkey_errors.append(
                    MaaFWHotkeyValueError(
                        option_name,
                        hotkey_item.name,
                        value=raw_text,
                        reason=str(exc),
                        fallback=fallback if fallback_values is not None else None,
                    )
                )
                if fallback_values is None:
                    return {}
                values = fallback_values
            typed_replacements.update(values)

        return cast(
            MaaFWPipelineOverride,
            self._substitute_placeholders(
                option.pipeline_override,
                typed_replacements,
                {},
            ),
        )

    def _build_scan_select_override(
        self,
        option_name: str,
        option: MaaFWOption,
        options: dict[str, MaaFWTaskOptionValue],
    ) -> MaaFWPipelineOverride:
        if not option.pipeline_override:
            return {}
        if option.cases is None:
            return copy.deepcopy(option.pipeline_override)
        selected_value = self._normalize_choice_value(option_name, option, options)
        return cast(
            MaaFWPipelineOverride,
            self._assign_scan_select_attach_value(
                option.pipeline_override, option_name, selected_value
            ),
        )

    def _build_option_override(
        self,
        option_name: str,
        options: dict[str, MaaFWTaskOptionValue],
        lineage: set[str] | None = None,
    ) -> MaaFWPipelineOverride:
        option = self.interface_model.option.get(option_name)
        if (
            option is None
            or option.type not in SUPPORTED_OPTION_TYPES
            or not self._is_option_active_for_context(option)
        ):
            return {}

        lineage = lineage or set()
        if option_name in lineage:
            return {}
        next_lineage = {*lineage, option_name}

        merged: MaaFWPipelineOverride = {}
        if option.type == "input":
            return deep_merge_pipeline_override(
                merged,
                self._build_input_override(option_name, option, options),
            )
        if option.type == "hotkey":
            return deep_merge_pipeline_override(
                merged,
                self._build_hotkey_override(option_name, option, options),
            )

        if option.type == "scan_select":
            merged = deep_merge_pipeline_override(
                merged,
                self._build_scan_select_override(option_name, option, options),
            )
        elif option.pipeline_override:
            merged = deep_merge_pipeline_override(merged, option.pipeline_override)

        if option.type in {"select", "switch"} and option.cases:
            active_case_name = self._normalize_choice_value(
                option_name, option, options
            )
            active_case = next(
                (case for case in option.cases if case.name == active_case_name), None
            )
            if active_case and active_case.pipeline_override:
                merged = deep_merge_pipeline_override(
                    merged, active_case.pipeline_override
                )
            if active_case and active_case.option:
                merged = deep_merge_pipeline_override(
                    merged,
                    self._build_option_group_override(
                        active_case.option, options, next_lineage
                    ),
                )
            return merged

        if option.type == "checkbox" and option.cases:
            selected_case_names = set(
                self._normalize_checkbox_values(option_name, option, options)
            )
            problem = checkbox_count_problem(option, len(selected_case_names))
            if problem is not None:
                _, min_count, max_count = problem
                raise MaaFWCheckboxCountError(
                    option_name,
                    selected=len(selected_case_names),
                    min_count=min_count,
                    max_count=max_count,
                )
            for case in option.cases:
                if case.name not in selected_case_names:
                    continue
                if case.pipeline_override:
                    merged = deep_merge_pipeline_override(
                        merged, case.pipeline_override
                    )
                if case.option:
                    merged = deep_merge_pipeline_override(
                        merged,
                        self._build_option_group_override(
                            case.option, options, next_lineage
                        ),
                    )
        return merged

    def _build_option_group_override(
        self,
        option_names: list[str],
        options: dict[str, MaaFWTaskOptionValue],
        lineage: set[str] | None = None,
    ) -> MaaFWPipelineOverride:
        merged: MaaFWPipelineOverride = {}
        for option_name in option_names:
            merged = deep_merge_pipeline_override(
                merged,
                self._build_option_override(option_name, options, lineage),
            )
        return merged


def _hotkey_referenced_values(field_name: str, template_strings: set[str]) -> set[str]:
    """pipeline 里引用到这个字段的字符串值（含写法不合规、占位符只是其中一段的）。"""

    placeholders = hotkey_placeholders(field_name)
    return {
        value
        for value in template_strings
        if any(placeholder in value for placeholder in placeholders)
    }


def _resolve_hotkey_placeholders(
    field_name: str,
    raw_text: str,
    controller_type: str,
    referenced_values: set[str],
) -> dict[str, int]:
    """键位 → 占位符值；映射不了或缺 pipeline 用到的修饰键时抛 ``MaaFWHotkeyError``。"""

    resolved = resolve_hotkey(raw_text, controller_type)
    values = resolved.placeholder_values(field_name)
    missing_placeholders = referenced_values - set(values)
    if missing_placeholders:
        raise MaaFWHotkeyError(
            f"快捷键 {raw_text} 不包含所需修饰键: "
            + ", ".join(sorted(missing_placeholders))
        )
    return values
