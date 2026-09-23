#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import json
import math
from collections.abc import Callable, Collection
from decimal import Decimal
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

MaaFWDocumentContent = str | list[str]
MaaFWPipelineOverride = dict[str, Any]
MaaFWPresetOptionValue = str | list[str] | dict[str, str]
MaaFWTaskOptionValue = str | list[str] | dict[str, str]
MaaFWTaskOptionsByTask = dict[str, dict[str, MaaFWTaskOptionValue]]

PRETASK_TASK_PREFIX = "__MXU_PRETASK__"
PRETASK_TASK_ENTRY = "MXU_PRETASK"
# Extra copies of a task queued more than once are persisted as
# "<name>__MAS_DUP__<suffix>"; the first copy keeps the bare task name, so
# configurations written before duplicates were supported need no migration.
DUPLICATE_TASK_SUFFIX_SEPARATOR = "__MAS_DUP__"
SUPPORTED_OPTION_TYPES = frozenset(
    {"select", "checkbox", "input", "hotkey", "switch", "scan_select"}
)


class MaaFWAdbController(BaseModel):
    model_config = ConfigDict(extra="allow")


class MaaFWWin32Controller(BaseModel):
    model_config = ConfigDict(extra="allow")

    class_regex: str | None = None
    window_regex: str | None = None
    # 协议写的是方法名字符串；MXU 另认数组（截图按位或），MFAA 另认旧版整数与
    # ``input``（mouse / keyboard 都没写时两者都用它）。解析与告警在
    # runner_task._resolve_win32_method，这里只放行这几种形状。
    mouse: str | list[str] | int | None = None
    keyboard: str | list[str] | int | None = None
    screencap: str | list[str] | int | None = None
    input: str | list[str] | int | None = None


class MaaFWMacOSController(BaseModel):
    model_config = ConfigDict(extra="allow")

    title_regex: str | None = None
    input: str | None = None
    screencap: str | None = None


class MaaFWPlayCoverController(BaseModel):
    model_config = ConfigDict(extra="allow")

    uuid: str | None = None


class MaaFWGamepadController(BaseModel):
    model_config = ConfigDict(extra="allow")

    class_regex: str | None = None
    window_regex: str | None = None
    gamepad_type: str | None = None
    screencap: str | None = None


class MaaFWWlRootsController(BaseModel):
    model_config = ConfigDict(extra="allow")


class MaaFWController(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    type: str
    # 协议写的是 number（schema 同），不只是整数；下发给控制器时再取整。
    display_short_side: int | float | None = 720
    display_long_side: int | float | None = None
    # Unity Canvas Scaler Expand 语义的参考分辨率 [width, height]。以前按未知字段放行，
    # 这里仍不做形状校验（写错不该让整份 interface 读不出来），建计划时校验、不对就告警忽略。
    display_expand: Any = None
    display_raw: bool | None = False
    permission_required: bool | None = False
    attach_resource_path: list[str] | None = None
    option: list[str] | None = None
    adb: MaaFWAdbController | None = None
    win32: MaaFWWin32Controller | None = None
    macos: MaaFWMacOSController | None = None
    playcover: MaaFWPlayCoverController | None = None
    gamepad: MaaFWGamepadController | None = None
    wlroots: MaaFWWlRootsController | None = None


class MaaFWResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    path: list[str] = Field(default_factory=list)
    controller: list[str] | None = None
    option: list[str] | None = None
    hash: str | None = None


class MaaFWAgent(BaseModel):
    model_config = ConfigDict(extra="allow")

    child_exec: str
    child_args: list[str] | None = None
    identifier: str | None = None
    embedded: bool | None = None
    # MFAA 私有扩展：等 agent 连上的秒数（>0 生效，-1 / 不写 = 不限）。MAS 据此定连接
    # 等待预算（runner.agent_connect_budget_seconds）。写法不对当没写，不让整份读不出来。
    timeout: int | float | None = None

    @field_validator("timeout", mode="before")
    @classmethod
    def coerce_timeout(cls, value: Any) -> int | float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value if math.isfinite(value) else None


class MaaFWPretask(BaseModel):
    model_config = ConfigDict(extra="allow")

    exec: str
    args: list[str] | None = None
    name: str | None = None
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    option: list[str] | None = None
    resource: list[str] | None = None
    controller: list[str] | None = None


class MaaFWTask(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    entry: str
    default_check: bool | None = False
    description: str | None = None
    doc: MaaFWDocumentContent | None = None
    desc: MaaFWDocumentContent | None = None
    icon: str | None = None
    group: list[str] | None = None
    resource: list[str] | None = None
    controller: list[str] | None = None
    pipeline_override: MaaFWPipelineOverride | None = None
    option: list[str] | None = None
    # MFAA 私有扩展：任务默认重复执行 repeat_count 次（MaaYuan 10 次、MATR 3 次）。
    # MAS 不在 runner 里循环，进队列时展开成 N 份重复任务实例（见 task_repeat_count）。
    # 不做形状校验：写错不该让整份 interface 读不出来，由 task_repeat_count 宽松解读。
    repeatable: Any = None
    repeat_count: Any = None


#: repeat_count 展开的上限（前端 ``maafwTaskInstance.ts`` 的
#: ``MAAFW_MAX_TASK_REPEAT_COUNT`` 同值）。真实项目最多写到 10（MaaYuan）；每份都是
#: 队列里一个独立实例，写成几万会把用户配置撑爆，超过的按上限展开并由加载器告警。
MAX_TASK_REPEAT_COUNT = 99


def task_repeat_count(task: MaaFWTask) -> int:
    """任务进队列时展开成几份：``repeatable`` 为 true 且 ``repeat_count`` ≥ 2 才展开。

    ``repeatable`` 缺省 / 为 false 时忽略 ``repeat_count``；``-1``（MFAA 的「无限」）、
    0、负数、非整数一律按 1 份（加载器对 repeatable 为 true 的这些写法告警）；超过
    ``MAX_TASK_REPEAT_COUNT`` 的按上限。
    """

    if task.repeatable is not True:
        return 1
    count = coerce_option_count(task.repeat_count)
    if count is None or count < 2:
        return 1
    return min(count, MAX_TASK_REPEAT_COUNT)


class MaaFWGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    default_expand: bool | None = True


class MaaFWSetting(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    option: list[str] | None = None
    default_expand: bool | None = True


class MaaFWOptionCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    option: list[str] | None = None
    pipeline_override: MaaFWPipelineOverride | None = None


class MaaFWInputCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    default: str | None = None
    pipeline_type: str | None = None
    verify: str | None = None
    verify_error: str | None = None
    pattern_msg: str | None = None
    # PI v2.10.0：密码 / 密钥字段。界面掩码、配置加密存储、不进日志；与 default 互斥
    # （两者同时出现时由加载器告警并丢掉 default）。
    password: bool = False

    @field_validator("default", mode="before")
    @classmethod
    def coerce_default_text(cls, value: Any) -> str | None:
        # 协议写的是字符串，但真实发行包里有写成数字的（MAG：``"default": 300000``）：
        # 与 preset 里的选项值同一口径按 JSON 写法转成字符串，结构值当没写。
        # 告警由加载器按原始值写。
        if value is None:
            return None
        return _preset_scalar_text(value)

    @field_validator("password", mode="before")
    @classmethod
    def coerce_password_flag(cls, value: Any) -> bool:
        # 写成 "true" / 1 也认；认不出来的一律当 false，别让整份 interface 读不出来。
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value == 1
        if isinstance(value, str):
            return value.strip().casefold() in {"true", "1", "yes"}
        return False

    @model_validator(mode="after")
    def fill_verify_error_alias(self):
        if self.pattern_msg is None and self.verify_error:
            self.pattern_msg = self.verify_error
        if self.verify_error is None and self.pattern_msg:
            self.verify_error = self.pattern_msg
        return self


class MaaFWHotkeyCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    default: str | None = None


class MaaFWOption(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = "select"
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    controller: list[str] | None = None
    resource: list[str] | None = None
    cases: list[MaaFWOptionCase] | None = None
    inputs: list[MaaFWInputCase] | None = None
    hotkeys: list[MaaFWHotkeyCase] | None = None
    scan_dir: str | None = None
    scan_filter: str | None = None
    pipeline_override: MaaFWPipelineOverride | None = None
    default_case: str | list[str] | None = None
    # PI v2.10.1：checkbox 的最少 / 最多选择数。写法不对（负数、小数、非数字）的按没写
    # 处理；与 case 数、彼此之间不自洽的由加载器告警并放宽（见 loader）。
    min_count: int | None = None
    max_count: int | None = None

    @field_validator("min_count", "max_count", mode="before")
    @classmethod
    def coerce_count(cls, value: Any) -> int | None:
        return coerce_option_count(value)


def coerce_option_count(value: Any) -> int | None:
    """把 ``min_count`` / ``max_count`` 宽松地归一成非负整数；不可用时返回 None。

    协议写的是 number；``"1"`` 这种数字字符串、``2.0`` 这种整数小数照样认，
    其余（负数、非整数、布尔、结构值）都当没写。告警由加载器按原始值写。
    """

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def checkbox_count_problem(
    option: "MaaFWOption", selected_count: int
) -> tuple[str, int, int | None] | None:
    """勾选数不满足 checkbox 的 ``min_count`` / ``max_count`` 时返回 ``(方向, 下限, 上限)``。

    方向是 ``"min"``（选少了）或 ``"max"``（选多了）；满足或没有限制时返回 None。
    限制值已由加载器放宽成自洽的（下限不超过 case 数、上限不小于下限）。
    """

    min_count = option.min_count or 0
    max_count = option.max_count
    if selected_count < min_count:
        return "min", min_count, max_count
    if max_count is not None and selected_count > max_count:
        return "max", min_count, max_count
    return None


def password_input_names(interface: "MaaFWInterface") -> dict[str, frozenset[str]]:
    """``{option 名: 其中 password 为 true 的输入字段名}``，只收 input 类型且至少有一个的。"""

    result: dict[str, frozenset[str]] = {}
    for option_name, option in interface.option.items():
        if option.type != "input":
            continue
        names = frozenset(item.name for item in option.inputs or [] if item.password)
        if names:
            result[option_name] = names
    return result


def map_password_values(
    task_options: Any,
    password_fields: dict[str, frozenset[str]],
    transform: Callable[[str, str, str], str],
) -> Any:
    """对快照 ``taskOptions``（``{任务实例: {option: {字段: 值}}}``）里的密码字段逐个套 ``transform``。

    ``transform(值, option 名, 字段名)`` 只作用于非空字符串；其余结构原样照抄（返回新
    对象，不改入参）。``transform`` 抛出的异常原样上抛，调用方决定怎么报。
    """

    if not isinstance(task_options, dict) or not password_fields:
        return task_options
    result: dict[Any, Any] = {}
    for task_id, option_values in task_options.items():
        if not isinstance(option_values, dict):
            result[task_id] = option_values
            continue
        mapped_options: dict[Any, Any] = {}
        for option_name, value in option_values.items():
            field_names = password_fields.get(option_name)
            if field_names and isinstance(value, dict):
                value = {
                    field: (
                        transform(item, option_name, field)
                        if field in field_names and isinstance(item, str) and item
                        else item
                    )
                    for field, item in value.items()
                }
            mapped_options[option_name] = value
        result[task_id] = mapped_options
    return result


def _preset_scalar_text(value: Any) -> str | None:
    """preset 里的标量按 JSON 写法转成字符串（99 → "99"，true → "true"）；非标量返回 None。

    整数形态的浮点（``99.0``、``1e20``）规范成整数串（"99"、"100000000000000000000"）：
    JSON 解析出来是 float，原样 ``json.dumps`` 会得到 "99.0" / "1e+20"，下发到
    pipeline_type 为 int 的输入时转不成整数。
    """

    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return format(Decimal(repr(value)).to_integral_value(), "f")
    if isinstance(value, (int, float)):
        return json.dumps(value)
    return None


def coerce_preset_option_value(
    value: Any,
) -> tuple[MaaFWPresetOptionValue | None, list[str]]:
    """把 preset 里写的一个选项值宽松地归一成协议形状，返回 ``(值, 问题说明)``。

    协议规定 ``OptionValue`` 只有字符串、字符串数组、字符串到字符串的对象三种，但真实
    发行包里有把 input 值写成数字的（MaaNTE v1.5.1：``{"count": 99}``）。官方
    MaaPiCli 对这类值是忽略而不是拒绝整份 interface，这里更进一步：数字 / 布尔标量
    按 JSON 写法转成字符串（与用户在输入框里填 ``99`` 等价），结构不对的项丢掉。
    值整个不可用时返回 ``None``。问题说明给加载器写告警用，这里不记日志。
    """

    problems: list[str] = []
    text = _preset_scalar_text(value)
    if text is not None:
        if not isinstance(value, str):
            problems.append(f"{json.dumps(value)} 已按字符串 {text!r} 处理")
        return text, problems
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            item_text = _preset_scalar_text(item)
            if item_text is None:
                problems.append(
                    f"数组元素 {json.dumps(item, ensure_ascii=False)} 不是字符串，已忽略"
                )
                continue
            if not isinstance(item, str):
                problems.append(
                    f"数组元素 {json.dumps(item)} 已按字符串 {item_text!r} 处理"
                )
            items.append(item_text)
        return items, problems
    if isinstance(value, dict):
        fields: dict[str, str] = {}
        for key, item in value.items():
            item_text = _preset_scalar_text(item)
            if not isinstance(key, str) or item_text is None:
                problems.append(
                    f"字段 {key} 的值 {json.dumps(item, ensure_ascii=False)} 不是字符串，已忽略"
                )
                continue
            if not isinstance(item, str):
                problems.append(
                    f"字段 {key} 的值 {json.dumps(item)} 已按字符串 {item_text!r} 处理"
                )
            fields[key] = item_text
        return fields, problems
    problems.append(
        f"值 {json.dumps(value, ensure_ascii=False, default=str)} 不是合法的选项值，已忽略"
    )
    return None, problems


class MaaFWPresetTask(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    enabled: bool | None = True
    option: dict[str, MaaFWPresetOptionValue] | None = None

    @field_validator("option", mode="before")
    @classmethod
    def coerce_option_values(cls, value: Any) -> Any:
        # 宽松解析：一个预设值写错不该让整份 interface 读不出来（告警由加载器写）。
        if value is None:
            return None
        if not isinstance(value, dict):
            return None
        coerced: dict[str, MaaFWPresetOptionValue] = {}
        for option_name, option_value in value.items():
            if not isinstance(option_name, str):
                continue
            normalized, _ = coerce_preset_option_value(option_value)
            if normalized is not None:
                coerced[option_name] = normalized
        return coerced


class MaaFWPreset(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    task: list[MaaFWPresetTask] | None = None


class MaaFWInterface(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    interface_version: Literal[2]
    languages: dict[str, str] | None = None
    name: str
    label: str | None = None
    title: str | None = None
    icon: str | None = None
    mirrorchyan_rid: str | None = None
    mirrorchyan_multiplatform: bool | None = None
    github: str | None = None
    version: str | None = None
    contact: str | None = None
    license: str | None = None
    # PI v2.10.2 起可以是字符串数组（多条公告按顺序展示）；单个字符串是旧写法。
    welcome: str | list[str] | None = None
    description: str | None = None
    controller: list[MaaFWController] = Field(default_factory=list)
    resource: list[MaaFWResource] = Field(default_factory=list)
    group: list[MaaFWGroup] | None = None
    setting: list[MaaFWSetting] | None = None
    pretask: MaaFWPretask | list[MaaFWPretask] | None = None
    agent: MaaFWAgent | list[MaaFWAgent] | None = None
    task: list[MaaFWTask] = Field(default_factory=list)
    option: dict[str, MaaFWOption] = Field(default_factory=dict)
    global_option: list[str] | None = None
    import_: list[str] | None = Field(default=None, alias="import")
    preset: list[MaaFWPreset] = Field(default_factory=list)
    # 加载器这次加载写下的告警（给用户看的原文，已去重），由加载器填、随磁盘缓存保存。
    # 私有属性：不进 model_dump，也不会被 interface.json 里的同名字段顶掉。
    _load_warnings: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def fill_display_defaults(self):
        if self.label is None:
            self.label = self.name
        if self.title is None and self.label and self.version:
            self.title = f"{self.label} {self.version}"
        return self


def interface_load_warnings(interface: MaaFWInterface) -> list[str]:
    """加载这份 interface 时的告警（preset 引用不存在的 case、缺 import 文件……）。

    只有经加载器读出来的模型才有；从字典直接校验出来的模型是空列表。
    """

    return list(getattr(interface, "_load_warnings", None) or [])


#: 归为简体中文的语言键前缀（小写、``_`` 换成 ``-`` 之后比），照 MFAA
#: ``LanguageHelper.NormalizeLangCode`` / ``IsSimplifiedChinese``。
_SIMPLIFIED_CHINESE_PREFIXES = ("zh-hans", "zh-cn", "zh-sg")


def simplified_chinese_language_file(interface: MaaFWInterface) -> str | None:
    """``languages`` 里简体中文那份语言文件的相对路径；没有返回 None。

    协议示例与多数项目写 ``zh_cn``，但键名没有强制写法：MaaGakumasu 写的是
    ``zh-CN`` / ``zh-Hant``，只认 ``zh_cn`` 时它的 ``$key`` 一个也翻不出来。精确的
    ``zh_cn`` 优先，其余按 MFAA 的口径归一（``zh-CN`` / ``zh_CN`` / ``zh-Hans`` /
    ``zh-SG`` 都算；繁体与裸 ``zh`` 不算）。
    """

    languages = interface.languages or {}
    exact = languages.get("zh_cn")
    if isinstance(exact, str) and exact.strip():
        return exact
    for key, value in languages.items():
        normalized = str(key).strip().lower().replace("_", "-")
        if (
            normalized.startswith(_SIMPLIFIED_CHINESE_PREFIXES)
            and isinstance(value, str)
            and value.strip()
        ):
            return value
    return None


def iter_pretasks(interface: MaaFWInterface) -> list[MaaFWPretask]:
    """Return ProjectInterface pretasks as a stable list."""

    raw_pretasks = interface.pretask
    if isinstance(raw_pretasks, list):
        return raw_pretasks
    return [raw_pretasks] if raw_pretasks is not None else []


def build_pretask_task_name(pretask: MaaFWPretask) -> str:
    """Build the pseudo-task name used by MXU-compatible clients."""

    return f"{PRETASK_TASK_PREFIX}{pretask.name or pretask.exec}"


def is_pretask_task_name(task_name: str) -> bool:
    """Return whether a persisted task name identifies a pretask pseudo-task."""

    return task_name.startswith(PRETASK_TASK_PREFIX)


def find_pretask_by_task_name(
    interface: MaaFWInterface,
    task_name: str,
) -> MaaFWPretask | None:
    """Resolve a persisted pseudo-task name to its ProjectInterface pretask."""

    return next(
        (
            pretask
            for pretask in iter_pretasks(interface)
            if build_pretask_task_name(pretask) == task_name
        ),
        None,
    )


def build_duplicate_task_id(task_name: str, suffix: str) -> str:
    """Build the persisted id of a duplicated task instance.

    The first instance of a task keeps the bare ProjectInterface task name as
    its id, so configurations written before duplicates were supported stay
    valid without migration.  Every extra copy gets ``<name>__MAS_DUP__<suffix>``.
    """

    return f"{task_name}{DUPLICATE_TASK_SUFFIX_SEPARATOR}{suffix}"


def resolve_task_instance_name(task_id: str, valid_task_names: Collection[str]) -> str:
    """Resolve a persisted task instance id back to its task name.

    A task whose own name happens to contain the separator still wins over the
    duplicate reading, so ids are never mis-resolved for such projects.
    """

    if task_id in valid_task_names:
        return task_id

    head, separator, _ = task_id.rpartition(DUPLICATE_TASK_SUFFIX_SEPARATOR)
    if separator and head in valid_task_names:
        return head
    return task_id
