#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""MSS 实例配置（MFAAvalonia 外壳私有格式）的透传读写、快照与恢复。

``<根>/config/instances/<实例ID>.json`` 是上游 MFAAvalonia 的私有格式，MAS 只在
**值**层面经手：把用户已配好的文件当模板，只替换 `CurrentTasks` 与 `AdbDevice`
里由 MAS 调度的模拟器决定的字段，其余键值原样写回；运行结束后用
``app.utils.io`` 的目录级原子换入恢复原始现场。MAS 不解析这份配置的语义，
也不在它之上建模型。

已实测的契约（样本：``D:\\jiao_ben\\maa\\mss``）：

- 实例 ID 取自 ``<根>/appsettings.json`` 的 ``Instances.List``（样本为 ``default``）；
- ``CurrentTasks`` 的元素是字面分隔的 ``"显示名<|||>entry"``；
- ``TaskItems[].option[]``：``select`` 型写 ``index``（``cases`` 的下标），
  ``input`` 型写 ``data``（``{输入名: 值}``）；子选项在 ``sub_options`` 里同构重复；
- ``AdbDevice.Config`` 是**嵌套 JSON 字符串**，``extras.<类型>.index`` 是模拟器实例序号。

快照与恢复复用 ``app.utils.io`` 的目录级快照原语（M9A / MaaEnd / Okww 同一套）：
快照对象是 ``<根>/config/instances`` 整个目录，因为 MAS 唯一会改的就是它，
``config/`` 下的外壳自身设置不参与快照，避免复原时把它们一起回退。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from app.utils import get_logger
from app.utils.io import (
    clear_native_config_snapshot,
    commit_native_config_snapshot,
    force_rmtree,
    mark_native_config_injected,
    read_file,
    recover_native_config,
    swap_in_dir,
    write_file,
)

logger = get_logger("MSS 实例配置")

## 外壳可执行文件与 PI V2 清单名（都在 MSS 根目录下）
EXE_NAME = "MFAAvalonia.exe"
INTERFACE_NAME = "interface.json"
## 外壳全局设置（实例列表与当前激活实例在这里）
APP_SETTINGS_NAME = "appsettings.json"
## 实例配置目录与日志目录（相对 MSS 根目录）
INSTANCE_DIR_RELATIVE = ("config", "instances")
LOG_DIR_NAME = "logs"
## instance id 读不到时的回退值，也是 MSS 发行包的默认实例
DEFAULT_INSTANCE_ID = "default"
## 实例配置文件名后缀
INSTANCE_SUFFIX = ".json"
## CurrentTasks 元素里的分隔符（字面量，非正则）
TASK_REF_SEPARATOR = "<|||>"

## 实例配置里 MAS 会经手的顶层键
CURRENT_TASKS_KEY = "CurrentTasks"
TASK_ITEMS_KEY = "TaskItems"
ADB_DEVICE_KEY = "AdbDevice"
## TaskItems 元素里承载选项列表的键名（PI V2 与外壳实例配置同名）
TASK_ITEMS_OPTION_KEY = "option"

## 队列项里承载选项取值的键名（宽松接受几种既有写法）
QUEUE_OPTION_KEYS = ("options", "option", "optionValues")
## 队列项里显式关闭该任务的键名
QUEUE_ENABLED_KEYS = ("enabled", "check", "checked")

## MAS 的模拟器类型 → MFAAvalonia 的 AdbDevice.Config.extras 键名
EXTRAS_KEY_BY_EMULATOR_TYPE = {
    "mumu": "mumu",
    "ldplayer": "ld",
}


def resolve_instance_dir(root: Path) -> Path:
    """返回 MSS 实例配置目录（``<根>/config/instances``）。

    Args:
        root: MSS 根目录（含 MFAAvalonia.exe 与 interface.json）。

    Returns:
        Path: 实例配置目录路径，不保证存在。
    """

    return root.joinpath(*INSTANCE_DIR_RELATIVE)


def resolve_instance_id(root: Path) -> str:
    """读 ``<根>/appsettings.json`` 的 ``Instances.List`` 得到当前激活实例 ID。

    外壳可以纳管多个实例，MAS 只驱动当前激活的那一个：``Instances.List`` 是
    实例 ID 列表，取第一个；读不到时回退 ``default``（发行包的默认实例）。

    Args:
        root: MSS 根目录。

    Returns:
        str: 实例 ID。
    """

    settings = read_file(root / APP_SETTINGS_NAME)
    if isinstance(settings, dict):
        raw = str(settings.get("Instances.List") or "").strip()
        ## 分隔符未在实测样本中出现（本机只有 default），按常见几种切开取首个非空段
        for token in raw.replace("|", ",").replace(";", ",").split(","):
            instance_id = token.strip()
            if instance_id and instance_id not in {".", ".."}:
                return instance_id
    return DEFAULT_INSTANCE_ID


def resolve_instance_path(root: Path, instance_id: str | None = None) -> Path:
    """返回实例配置文件路径。

    Args:
        root: MSS 根目录。
        instance_id: 实例 ID；省略时按 appsettings.json 解析。

    Returns:
        Path: ``<根>/config/instances/<实例ID>.json``。
    """

    return resolve_instance_dir(root) / (
        f"{instance_id or resolve_instance_id(root)}{INSTANCE_SUFFIX}"
    )


def read_instance_config(path: Path) -> dict[str, Any]:
    """读实例配置。

    文件不存在返回空字典；存在但不是 JSON 对象时抛 ``ValueError``——那说明
    路径指错了（或文件被写坏），静默当成空配置会把用户的整份配置覆盖掉。

    Args:
        path: 实例配置文件路径。

    Returns:
        dict[str, Any]: 实例配置内容，不存在时为空字典。
    """

    if not path.is_file():
        return {}

    data = read_file(path)
    if not isinstance(data, dict):
        raise ValueError(f"MSS 实例配置不是合法的 JSON 对象: {path}")
    return data


def write_instance_config(path: Path, config: dict[str, Any]) -> None:
    """原子写回实例配置。

    用 ``app.utils.io.write_file``：``.json`` 走 ``indent=2`` / ``ensure_ascii=False``，
    与外壳自身落盘的排版一致，键序按字典顺序原样保留。

    Args:
        path: 实例配置文件路径。
        config: 完整的实例配置内容。
    """

    write_file(path, config)
    logger.info(f"已写入 MSS 实例配置: {path}")


def build_task_ref(name: str, entry: str) -> str:
    """拼出 ``CurrentTasks`` 的元素（``"显示名<|||>entry"``）。

    Args:
        name: 任务显示名。
        entry: 任务的 PI V2 entry。

    Returns:
        str: 元素文本；entry 为空时只留显示名。
    """

    return f"{name}{TASK_REF_SEPARATOR}{entry}" if entry else str(name)


def split_task_ref(raw: Any) -> tuple[str, str]:
    """拆开 ``"显示名<|||>entry"``。

    Args:
        raw: ``CurrentTasks`` 里的一个元素。

    Returns:
        tuple[str, str]: ``(显示名, entry)``；没有分隔符时 entry 为空串。
    """

    text = str(raw or "").strip()
    name, separator, entry = text.partition(TASK_REF_SEPARATOR)
    if not separator:
        return name, ""
    return name.strip(), entry.strip()


def _normalize_option_entries(raw: Any) -> list[dict[str, Any]]:
    """把队列项里的选项取值统一成 ``[{name, index?, data?, sub_options?}]``。

    宽松接受两种写法：列表形式（元素自带 ``name``）与映射形式
    （``{选项名: 下标}`` 或 ``{选项名: {index/data/sub_options}}``）。

    Args:
        raw: 队列项里的选项取值。

    Returns:
        list[dict[str, Any]]: 归一化后的选项项列表；无法识别时为空列表。
    """

    if isinstance(raw, dict):
        entries: list[dict[str, Any]] = []
        for name, value in raw.items():
            if isinstance(value, dict):
                ## 已经在写外壳形状（index/data/sub_options）就直接用；否则整个字典
                ## 就是 input 型选项的取值表，必须包进 data —— 展平到顶层会让外壳
                ## 把 "1号" 当成未知键丢掉，用户填的旅人名一个都写不进去。
                if {"index", "data", "sub_options"} & set(value):
                    entry = {"name": str(name), **value}
                else:
                    entry = {"name": str(name), "data": dict(value)}
            else:
                ## select 型：值既可能是外壳原生的下标，也可能是可读的 case 名，
                ## 由 _resolve_case_index 在写盘时按选项定义折成下标。
                entry = {"name": str(name), "index": value}
            entries.append(entry)
        return entries

    if isinstance(raw, list):
        return [
            dict(value)
            for value in raw
            if isinstance(value, dict) and str(value.get("name") or "").strip()
        ]

    return []


def normalize_user_queue(raw: Any) -> list[dict[str, Any]]:
    """把用户配置里的 ``Task.Queue`` 解析成统一形状的队列项列表。

    接受 JSON 字符串或已经是列表的入参；每一项可以是
    ``"显示名<|||>entry"`` / ``"显示名"`` 字符串，也可以是含
    ``name`` / ``entry`` / ``options``（或 ``option`` / ``optionValues``）的字典。
    显式写成 ``false`` 的 ``enabled`` / ``check`` 项会被跳过。

    Args:
        raw: ``Task.Queue`` 的原始值。

    Returns:
        list[dict[str, Any]]: ``[{"name": str, "entry": str, "options": list[dict]}]``。

    Raises:
        ValueError: 入参不是 JSON 列表时。
    """

    queue = raw
    if isinstance(queue, str):
        text = queue.strip()
        if not text:
            return []
        queue = json.loads(text)

    if not isinstance(queue, list):
        raise ValueError(f"任务队列类型异常: {type(queue).__name__}")

    items: list[dict[str, Any]] = []
    for value in queue:
        if isinstance(value, str):
            name, entry = split_task_ref(value)
            options: Any = None
        elif isinstance(value, dict):
            if any(value.get(key) is False for key in QUEUE_ENABLED_KEYS):
                continue
            name = str(value.get("name") or value.get("task") or "").strip()
            entry = str(value.get("entry") or "").strip()
            if not name and not entry:
                continue
            if not entry:
                ## 只写了显示名时，按 `"显示名<|||>entry"` 再拆一次
                name, entry = split_task_ref(name)
            options = next(
                (value[key] for key in QUEUE_OPTION_KEYS if value.get(key)), None
            )
        else:
            continue

        if not name and not entry:
            continue
        items.append(
            {
                "name": name,
                "entry": entry,
                "options": _normalize_option_entries(options),
            }
        )

    return items


def build_current_tasks(queue: list[dict[str, Any]]) -> list[str]:
    """把队列项列表折成 ``CurrentTasks``。

    Args:
        queue: :func:`normalize_user_queue` 的输出。

    Returns:
        list[str]: ``"显示名<|||>entry"`` 元素列表。
    """

    refs = [build_task_ref(item["name"], item["entry"]) for item in queue]
    return [ref for ref in refs if ref.strip()]


def _resolve_case_index(
    option_definitions: dict[str, Any] | None, option_name: str, value: Any
) -> Any:
    """把 select 型选项的取值折成外壳要的下标。

    MAS 的用户队列里这个值是可读的 case 名（``"所有"``、``"最爱"``），写盘时
    要换成 ``cases`` 里的下标；外壳原生形状（已经是整数下标）原样通过。按名字
    查不到时退回原值，由外壳按自己的默认值处理，不在这里猜一个下标。

    Args:
        option_definitions: 选项名 → PI V2 选项定义。
        option_name: 选项名。
        value: 队列里给出的取值。

    Returns:
        Any: ``cases`` 的下标，或无法折换时的原值。
    """

    if isinstance(value, bool) or isinstance(value, int):
        return value

    text = str(value).strip()
    definition = (option_definitions or {}).get(option_name) or {}
    cases = [case for case in (definition.get("cases") or []) if isinstance(case, dict)]
    if not text or not cases:
        return value

    for index, case in enumerate(cases):
        if text in (str(case.get("name") or ""), str(case.get("label") or "")):
            return index
    return value


def _merge_option_items(
    base_items: list[Any],
    overrides: list[dict[str, Any]],
    option_definitions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """按选项名把队列项给出的取值并进基础选项项（``sub_options`` 递归同构）。

    Args:
        base_items: 模板或默认构建出的选项项。
        overrides: 队列项里用户显式给出的选项取值。
        option_definitions: 选项名 → PI V2 选项定义，用于把 case 名折成下标。

    Returns:
        list[dict[str, Any]]: 合并后的选项项列表。
    """

    merged = [copy.deepcopy(item) for item in base_items if isinstance(item, dict)]

    for override in overrides:
        name = str(override.get("name") or "")
        if not name:
            continue
        target = next(
            (item for item in merged if str(item.get("name") or "") == name), None
        )
        if target is None:
            target = {"name": name, "index": 0}
            merged.append(target)

        ## index 显式为 null 时保留基础值：真实配置里子选项的 index 就是 null，
        ## 那不是「用户要选第一个」，只是外壳没记下标
        if override.get("index") is not None:
            target["index"] = _resolve_case_index(
                option_definitions, name, override["index"]
            )
        if isinstance(override.get("data"), dict):
            target["data"] = dict(override["data"])

        sub_overrides = _normalize_option_entries(override.get("sub_options"))
        if sub_overrides:
            target["sub_options"] = _merge_option_items(
                target.get("sub_options") or [], sub_overrides, option_definitions
            )

    return merged


def build_default_option_items(
    option_names: list[str], option_definitions: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """按 PI V2 选项定义生成一份默认选项项。

    MSS 当前（实测 v1.1.0）的选项只有 ``input`` 与 ``select`` 两种类型：
    ``input`` 用定义的 ``inputs[].default`` 填 ``data``，``select`` 用
    ``default_case`` 在 ``cases`` 里的下标填 ``index``（匹配不上时取 0）。
    选中项带子选项时递归展开 ``sub_options``。其它类型退化为 ``index: 0``。

    Args:
        option_names: 选项名列表（任务定义里的 ``option``）。
        option_definitions: 选项名 → PI V2 选项定义；缺失时按空定义处理。

    Returns:
        list[dict[str, Any]]: 默认选项项列表。
    """

    definitions = option_definitions or {}
    items: list[dict[str, Any]] = []

    for name in option_names:
        definition = definitions.get(name)
        definition = definition if isinstance(definition, dict) else {}
        item: dict[str, Any] = {"name": name, "index": 0}

        option_type = str(definition.get("type") or "select")
        cases = [
            case for case in (definition.get("cases") or []) if isinstance(case, dict)
        ]
        selected_case: dict[str, Any] | None = None

        if option_type == "input":
            data = {
                str(input_def.get("name")): input_def.get("default")
                for input_def in (definition.get("inputs") or [])
                if isinstance(input_def, dict)
                and input_def.get("name")
                and input_def.get("default") is not None
            }
            if data:
                item["data"] = data
        elif cases:
            default_case = definition.get("default_case")
            index = _resolve_default_case_index(cases, default_case)
            item["index"] = index
            selected_case = cases[index]

        sub_names = list(selected_case.get("option") or []) if selected_case else []
        if sub_names:
            sub_items = build_default_option_items(sub_names, definitions)
            if sub_items:
                item["sub_options"] = sub_items

        items.append(item)

    return items


def _resolve_default_case_index(cases: list[dict[str, Any]], default_case: Any) -> int:
    """求 ``default_case`` 在 ``cases`` 里的下标，找不到返回 0。

    ``default_case`` 可能写 ``case.name``（如 ``属性_光土``），也可能写界面上
    展示的 ``label``（如 ``光土``），两种都认。

    Args:
        cases: 选项的 ``cases`` 列表。
        default_case: 选项定义里的 ``default_case``。

    Returns:
        int: 下标，落在 ``[0, len(cases))`` 内。
    """

    if isinstance(default_case, str) and default_case:
        for index, case in enumerate(cases):
            if default_case in (
                str(case.get("name") or ""),
                str(case.get("label") or ""),
            ):
                return index
    return 0


def build_task_item(
    queue_item: dict[str, Any],
    *,
    template: dict[str, Any] | None = None,
    task_definition: dict[str, Any] | None = None,
    option_definitions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建一个 ``TaskItems`` 元素。

    优先用用户自己在 MSS 里配好的同任务项当模板（``option`` 的既有取值、描述、
    控制端等全部保留），只把显示名与队列项显式给出的选项取值覆盖上去；模板缺失时
    按 PI V2 任务定义构建最小项。

    Args:
        queue_item: 一个队列项（``normalize_user_queue`` 的元素）。
        template: 同一任务的模板项（取自「本轮动手前」的实例配置）。
        task_definition: PI V2 任务定义（``name`` / ``entry`` / ``description`` / ``option``）。
        option_definitions: 选项名 → PI V2 选项定义，用于构建默认选项值。

    Returns:
        dict[str, Any]: ``TaskItems`` 元素。
    """

    definition = task_definition if isinstance(task_definition, dict) else {}
    name = str(queue_item.get("name") or "").strip()
    entry = str(queue_item.get("entry") or "").strip()

    if isinstance(template, dict):
        item = copy.deepcopy(template)
        option_names = [
            str(option.get("name") or "")
            for option in (item.get(TASK_ITEMS_OPTION_KEY) or [])
            if isinstance(option, dict) and option.get("name")
        ]
    else:
        option_names = [
            str(option_name)
            for option_name in (definition.get("option") or [])
            if str(option_name).strip()
        ]
        item = {
            "name": name or str(definition.get("name") or entry),
            "entry": entry or str(definition.get("entry") or ""),
            "default_check": False,
        }
        description = definition.get("description")
        if description:
            item["description"] = description
        default_options = build_default_option_items(option_names, option_definitions)
        if default_options:
            item[TASK_ITEMS_OPTION_KEY] = default_options

    ## 显示名以 MAS 队列为准：壳按它对上 CurrentTasks 的条目
    if name:
        item["name"] = name
    if entry:
        item["entry"] = entry
    item.setdefault("default_check", False)

    merged = _merge_option_items(
        item.get(TASK_ITEMS_OPTION_KEY) or [],
        queue_item.get("options") or [],
        option_definitions,
    )
    if merged:
        item[TASK_ITEMS_OPTION_KEY] = merged
    else:
        item.pop(TASK_ITEMS_OPTION_KEY, None)

    logger.debug(
        f"构建任务项: {item.get('name')} ({item.get('entry')}), "
        f"模板={'有' if isinstance(template, dict) else '无'}, "
        f"选项数={len(item.get(TASK_ITEMS_OPTION_KEY) or [])}, "
        f"PI 选项数={len(option_names)}"
    )
    return item


def apply_queue_to_config(
    config: dict[str, Any],
    queue: list[dict[str, Any]],
    *,
    task_definitions: dict[str, Any] | None = None,
    option_definitions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把用户队列写进实例配置：只改 ``CurrentTasks`` 与 ``TaskItems``。

    ``config`` 会被深拷贝，原对象不动；除这两个键以外的所有键值原样保留。

    Args:
        config: 「本轮动手前」的实例配置模板。
        queue: 队列项列表（``normalize_user_queue`` 的输出）。
        task_definitions: 任务定义索引（entry 或显示名 → PI V2 任务定义）。
        option_definitions: 选项名 → PI V2 选项定义。

    Returns:
        dict[str, Any]: 改写后的实例配置副本。
    """

    definitions = task_definitions or {}
    result = copy.deepcopy(config)

    templates = result.get(TASK_ITEMS_KEY)
    templates = templates if isinstance(templates, list) else []
    by_entry: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for template in templates:
        if not isinstance(template, dict):
            continue
        entry = str(template.get("entry") or "")
        if entry:
            by_entry.setdefault(entry, template)
        template_name = str(template.get("name") or "")
        if template_name:
            by_name.setdefault(template_name, template)

    items: list[dict[str, Any]] = []
    for queue_item in queue:
        entry = str(queue_item.get("entry") or "")
        name = str(queue_item.get("name") or "")
        template = by_entry.get(entry) if entry else None
        if template is None:
            template = by_name.get(name) if name else None
        definition = definitions.get(entry) or definitions.get(name)
        if template is None and definition is None:
            logger.warning(
                f"实例配置模板与 interface 里都没有任务 {name or entry}, "
                "按最小任务项写入（选项保持外壳默认值）"
            )
        items.append(
            build_task_item(
                queue_item,
                template=template,
                task_definition=definition,
                option_definitions=option_definitions,
            )
        )

    result[TASK_ITEMS_KEY] = items
    result[CURRENT_TASKS_KEY] = build_current_tasks(queue)
    logger.info(
        f"MSS 实例配置已改写: 任务 {len(result[CURRENT_TASKS_KEY])} 个 "
        f"(TaskItems {len(items)} 项), 其余字段原样保留"
    )
    return result


def _parse_adb_config(raw: Any) -> dict[str, Any] | None:
    """解析 ``AdbDevice.Config``（嵌套 JSON 字符串）。

    Args:
        raw: ``Config`` 字段的原始值。

    Returns:
        dict[str, Any] | None: 解析结果；无法解析为 JSON 对象时返回 None
        （调用方据此跳过改写，避免把用户的原值写坏）。
    """

    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    if not isinstance(raw, str) or not raw.strip():
        return {}

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("MSS AdbDevice.Config 不是合法 JSON 字符串, 已保留原值")
        return None

    return parsed if isinstance(parsed, dict) else None


def apply_adb_device(
    config: dict[str, Any],
    *,
    adb_path: str | None = None,
    adb_serial: str | None = None,
    emulator_type: str = "",
    emulator_index: Any = None,
    emulator_root: str | None = None,
    emulator_name: str | None = None,
) -> list[str]:
    """按 MAS 调度的模拟器改写 ``AdbDevice`` 里 adb 相关的字段。

    只动 ``AdbPath`` / ``AdbSerial`` / ``Name``（仅在原值为空时补）/ ``Config``
    里对应 ``extras`` 桶的 ``enable`` / ``index`` / ``path``；``ScreencapMethods``、
    ``InputMethods``、``AgentPath`` 等上游取值一律不碰——它们不是 MAS 该过手的语义。

    Args:
        config: 实例配置（原地修改）。
        adb_path: ``adb.exe`` 路径。
        adb_serial: 目标设备地址（如 ``127.0.0.1:16480``）。
        emulator_type: MAS 侧模拟器类型（``mumu`` / ``ldplayer``）。
        emulator_index: 模拟器原生实例序号。
        emulator_root: 模拟器安装根目录。
        emulator_name: 模拟器显示名，仅用于补空 ``Name``。

    Returns:
        list[str]: 实际改动的键名列表；未改动时为空列表。
    """

    device = config.get(ADB_DEVICE_KEY)
    if not isinstance(device, dict):
        device = {}
        config[ADB_DEVICE_KEY] = device

    changed: list[str] = []

    if adb_path and device.get("AdbPath") != adb_path:
        device["AdbPath"] = str(adb_path).replace("\\", "/")
        changed.append("AdbPath")

    if adb_serial and device.get("AdbSerial") != adb_serial:
        device["AdbSerial"] = str(adb_serial)
        changed.append("AdbSerial")

    if emulator_name and not str(device.get("Name") or "").strip():
        device["Name"] = str(emulator_name)
        changed.append("Name")

    extras_key = EXTRAS_KEY_BY_EMULATOR_TYPE.get(str(emulator_type).strip().lower())
    if extras_key and emulator_index is not None:
        adb_config = _parse_adb_config(device.get("Config"))
        if adb_config is not None:
            extras = adb_config.get("extras")
            if not isinstance(extras, dict):
                extras = {}
                adb_config["extras"] = extras
            bucket = extras.get(extras_key)
            if not isinstance(bucket, dict):
                bucket = {}
                extras[extras_key] = bucket

            bucket["enable"] = True
            bucket["index"] = _coerce_index(emulator_index)
            if emulator_root:
                bucket["path"] = str(emulator_root).replace("\\", "/")
            device["Config"] = json.dumps(adb_config, ensure_ascii=False)
            changed.append(f"Config.extras.{extras_key}")
        elif not str(device.get("Config") or "").strip():
            ## 原本没有 Config：只为这类空值补一份最小结构，非空且非法的原值不覆盖
            bucket: dict[str, Any] = {
                "enable": True,
                "index": _coerce_index(emulator_index),
            }
            if emulator_root:
                bucket["path"] = str(emulator_root).replace("\\", "/")
            device["Config"] = json.dumps(
                {"extras": {extras_key: bucket}}, ensure_ascii=False
            )
            changed.append(f"Config.extras.{extras_key}")

    return changed


def _coerce_index(index: Any) -> Any:
    """把模拟器序号折成整数（外壳的 ``extras.*.index`` 是整数）。

    Args:
        index: 原始序号。

    Returns:
        Any: 能转成整数时返回 ``int``，否则原样返回。
    """

    text = str(index).strip()
    return int(text) if text.lstrip("-").isdigit() else index


def commit_instance_snapshot(
    root: Path, snapshot_path: Path, *, script_id: str
) -> bool:
    """把 ``<根>/config/instances`` 备份为可恢复快照。

    备份只写进快照目录，全程不触碰原生配置；快照目录与提交标记由
    ``app.utils.io`` 维护，未提交的半成品会在下次恢复时被丢弃。

    Args:
        root: MSS 根目录。
        snapshot_path: 快照目录（``data/<script_id>/Temp``）。
        script_id: 所属脚本，供恢复时校验归属。

    Returns:
        bool: 原生实例配置目录是否存在并已备份。
    """

    return commit_native_config_snapshot(
        snapshot_path, resolve_instance_dir(root), script_id=script_id
    )


def recover_previous_instance_snapshot(
    root: Path, snapshot_path: Path, *, script_id: str
) -> str:
    """任务开始前处置上次崩溃残留的实例配置快照。

    只有确属 MAS 中途退出才恢复（原目录缺失或与注入后指纹一致）；用户在中止后
    自己改过实例配置时只清理快照、不覆盖。

    Args:
        root: MSS 根目录。
        snapshot_path: 快照目录。
        script_id: 所属脚本。

    Returns:
        str: ``restored`` / ``intact`` / ``skipped`` / ``cleared``。
    """

    return recover_native_config(
        snapshot_path,
        resolve_instance_dir(root),
        expected_script_id=script_id,
    )


def mark_instance_config_injected(
    root: Path, snapshot_path: Path, *, script_id: str
) -> None:
    """记录 MAS 注入后的实例配置目录指纹，供崩溃恢复区分污染与用户改动。

    Args:
        root: MSS 根目录。
        snapshot_path: 快照目录。
        script_id: 所属脚本。
    """

    mark_native_config_injected(
        snapshot_path, resolve_instance_dir(root), script_id=script_id
    )


def restore_instance_snapshot(
    root: Path, snapshot_path: Path, *, had_original: bool
) -> bool:
    """把实例配置目录原子恢复成快照里的原始现场。

    ``had_original`` 为假表示这次运行前实例配置目录根本不存在，恢复即删除本次
    运行建出来的目录，避免在用户机器上留下 MAS 造的文件。

    Args:
        root: MSS 根目录。
        snapshot_path: 快照目录。
        had_original: 快照时原生实例配置目录是否已存在。

    Returns:
        bool: 是否执行了恢复动作。
    """

    instance_dir = resolve_instance_dir(root)

    if not had_original:
        ## 本轮动手前实例配置目录就不存在（快照也可能是空的），恢复即清掉
        ## MAS 造出来的目录，不在用户机器上留下它的痕迹
        force_rmtree(instance_dir)
        logger.info(f"已清理本次运行新建的 MSS 实例配置目录: {instance_dir}")
        return True

    if not snapshot_path.is_dir():
        ## 没有可复原的原始现场：宁可什么都不做，也不能把用户的现场删掉
        return False

    swap_in_dir(snapshot_path, instance_dir)
    logger.success(f"已恢复 MSS 实例配置: {instance_dir}")
    return True


def discard_instance_snapshot(snapshot_path: Path) -> None:
    """丢弃快照及其提交标记（恢复完成后调用）。

    Args:
        snapshot_path: 快照目录。
    """

    clear_native_config_snapshot(snapshot_path)


def read_instance_template(
    root: Path, snapshot_path: Path, *, instance_id: str | None = None
) -> dict[str, Any]:
    """取「本轮动手前」的实例配置模板。

    模板必须优先取自快照：同一轮任务里多个用户共用一份实例文件，现场文件在第一个
    用户跑完后已经是 MAS 改写过的版本，拿它当模板会让上一个用户的队列残留下来。

    Args:
        root: MSS 根目录。
        snapshot_path: 快照目录。
        instance_id: 实例 ID；省略时按 appsettings.json 解析。

    Returns:
        dict[str, Any]: 实例配置模板，快照与现场都不存在时为空字典。
    """

    resolved_id = instance_id or resolve_instance_id(root)
    snapshot_file = snapshot_path / f"{resolved_id}{INSTANCE_SUFFIX}"
    if snapshot_file.is_file():
        data = read_file(snapshot_file)
        if isinstance(data, dict):
            return data
        logger.warning(f"快照里的 MSS 实例配置不是 JSON 对象, 改用现场文件: {snapshot_file}")

    return read_instance_config(resolve_instance_path(root, resolved_id))


def latest_log_file(log_dir: Path, since: float) -> Path | None:
    """在日志目录里找 ``since`` 之后被写过的最新日志文件。

    外壳按天写 ``log-YYYYMMDD.log``，常规路径由日期直接算出（见 AutoProxy 的
    按日滚动解析）；本函数只作兜底，用于日期路径还没出现时的等待窗口。

    Args:
        log_dir: 日志目录。
        since: 起始时间戳（``time.time()`` 口径）。

    Returns:
        Path | None: 最新的日志文件；没有符合条件时返回 None。
    """

    if not log_dir.is_dir():
        return None

    candidates = [
        path
        for path in log_dir.glob("log-*.log")
        if path.is_file() and path.stat().st_mtime >= since
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)
