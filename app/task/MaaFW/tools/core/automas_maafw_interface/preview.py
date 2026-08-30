from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .loader import parse_json_text
from .models import (
    PRETASK_TASK_ENTRY,
    SUPPORTED_OPTION_TYPES,
    MaaFWInterface,
    build_pretask_task_name,
    iter_pretasks,
)
from .task_config import _build_task_option_maps, build_interface_preset_snapshot


class MaaFWInterfaceValidationReport(BaseModel):
    ok: bool
    message: str = ""


# EmulatorExtras (ADB 截图/输入加速) 是 MaaFW 的 Windows-only 特性。每个模拟器
# 族支持的加速子集是固定的，此关系表对齐 MaaFW 控制器定义。能力是否真正可用取
# 决于运行时安装的 maa 是否带 MaaAdbControlUnit.dll，由下方探测函数按真实环境判断。
_EMULATOR_EXTRA_RELATION: dict[str, dict[str, bool]] = {
    "mumu": {"screencap": True, "input": True},
    "ldplayer": {"screencap": True, "input": False},
}


def _maafw_emulator_extras_runtime_available() -> bool:
    """Return whether the installed MaaFW runtime exposes ADB EmulatorExtras.

    定位运行环境真实安装的 ``maa`` 包并检查 ``MaaAdbControlUnit.dll`` 是否存在。
    用 ``importlib.util.find_spec`` 定位包目录——它只查找 spec、不执行 ``maa/__init__``
    也不加载原生绑定，因此**本函数自身**不触发 maa 导入。非 Windows 不可用。

    注意不要据此推断「maa 未被载入主进程」：``app/core/maa_manager.py`` 在模块级
    ``from maa.tasker import Tasker`` 并在导入时实例化单例，而 ``app.core`` 是全应用
    公共入口，进程里实际早已完成原生初始化。那是上游基线既有的第二层原生集成，
    与本层无关，也不要顺手去改它。
    
    """

    if os.name != "nt":
        return False
    spec = importlib.util.find_spec("maa")
    if spec is None or not spec.submodule_search_locations:
        return False
    maa_package_dir = Path(next(iter(spec.submodule_search_locations)))
    return (maa_package_dir / "bin" / "MaaAdbControlUnit.dll").is_file()


def build_adb_emulator_extra_capabilities() -> dict[str, dict[str, bool]]:
    """Return per-emulator EmulatorExtras capabilities for the installed MaaFW."""

    if not _maafw_emulator_extras_runtime_available():
        return {}
    return {
        emulator_type: dict(relation)
        for emulator_type, relation in _EMULATOR_EXTRA_RELATION.items()
    }


class MaaFWInterfacePreviewData(BaseModel):
    path: str
    project: dict[str, Any]
    globalOption: list[str] = Field(default_factory=list)
    controllers: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    groups: list[dict[str, Any]] = Field(default_factory=list)
    settings: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    options: list[dict[str, Any]] = Field(default_factory=list)
    presets: list[dict[str, Any]] = Field(default_factory=list)
    importCount: int = 0
    agentCount: int = 0
    controlCapabilities: dict[str, Any] = Field(default_factory=dict)


def build_interface_preview_data(
    root_path: str | Path,
    interface: MaaFWInterface,
) -> MaaFWInterfacePreviewData:
    root = Path(root_path).resolve()
    i18n_mapping = _load_i18n_mapping(root, interface)
    task_order = [task.name for task in interface.task]
    task_option_maps = _build_task_option_maps(interface)
    supported_option_names = {
        option_name
        for option_name, option in interface.option.items()
        if option.type in SUPPORTED_OPTION_TYPES
    }

    def filter_option_names(option_names: list[str] | None) -> list[str]:
        return [
            option_name
            for option_name in option_names or []
            if option_name in supported_option_names
        ]

    def tr_text(value: str | None) -> str | None:
        translated = _resolve_i18n_value(value, i18n_mapping)
        return translated if isinstance(translated, str) else value

    def tr_description(value: str | None) -> str | None:
        return resolve_description(root, tr_text(value))

    agent_count = 0
    if isinstance(interface.agent, list):
        agent_count = len(interface.agent)
    elif interface.agent is not None:
        agent_count = 1

    presets: list[dict[str, Any]] = []
    for preset in interface.preset:
        snapshot = build_interface_preset_snapshot(
            interface,
            preset,
            task_order=task_order,
            task_option_maps=task_option_maps,
            include_default_options=False,
        )
        checked_count = sum(1 for checked in snapshot.taskChecked.values() if checked)
        presets.append(
            {
                "name": preset.name,
                "label": tr_text(preset.label),
                "description": tr_description(preset.description),
                "taskCount": len(preset.task or []),
                "checkedCount": checked_count,
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    return MaaFWInterfacePreviewData(
        path=str(root),
        project={
            "name": interface.name,
            "label": tr_text(interface.label),
            "title": tr_text(interface.title),
            "version": interface.version,
            "github": interface.github,
            "mirrorchyanRid": interface.mirrorchyan_rid,
            "mirrorchyanMultiplatform": interface.mirrorchyan_multiplatform,
            "description": tr_description(interface.description),
            "icon": interface.icon,
        },
        globalOption=filter_option_names(interface.global_option),
        controllers=[
            {
                "name": controller.name,
                "label": tr_text(controller.label),
                "type": controller.type,
                "description": tr_description(controller.description),
                "icon": controller.icon,
                "option": filter_option_names(controller.option),
                "permissionRequired": bool(controller.permission_required),
            }
            for controller in interface.controller
        ],
        resources=[
            {
                "name": resource.name,
                "label": tr_text(resource.label),
                "description": tr_description(resource.description),
                "icon": resource.icon,
                "path": resource.path,
                "controller": resource.controller or [],
                "option": filter_option_names(resource.option),
            }
            for resource in interface.resource
        ],
        groups=[
            {
                "name": group.name,
                "label": tr_text(group.label),
                "description": tr_description(group.description),
                "icon": group.icon,
                "defaultExpand": bool(group.default_expand),
            }
            for group in interface.group or []
        ],
        settings=[
            {
                "name": setting.name,
                "label": tr_text(setting.label) or setting.name,
                "description": tr_description(setting.description),
                "icon": setting.icon,
                "option": filter_option_names(setting.option),
                "defaultExpand": bool(setting.default_expand),
            }
            for setting in interface.setting or []
        ],
        tasks=[
            *[
                {
                    "name": build_pretask_task_name(pretask),
                    "label": tr_text(pretask.label) or pretask.name or pretask.exec,
                    "entry": PRETASK_TASK_ENTRY,
                    "description": tr_description(pretask.description),
                    "icon": pretask.icon,
                    "group": [],
                    "controller": pretask.controller or [],
                    "resource": pretask.resource or [],
                    "option": filter_option_names(pretask.option),
                    "defaultCheck": False,
                }
                for pretask in iter_pretasks(interface)
            ],
            *[
                {
                    "name": task.name,
                    "label": tr_text(task.label),
                    "entry": task.entry,
                    "description": tr_description(task.description),
                    "icon": task.icon,
                    "group": task.group or [],
                    "controller": task.controller or [],
                    "resource": task.resource or [],
                    "option": filter_option_names(task.option),
                    "defaultCheck": bool(task.default_check),
                }
                for task in interface.task
            ],
        ],
        options=[
            {
                "name": option_name,
                "type": option.type,
                "label": tr_text(option.label),
                "description": tr_description(option.description),
                "icon": option.icon,
                "controller": option.controller or [],
                "resource": option.resource or [],
                "cases": [
                    {
                        "name": case.name,
                        "label": tr_text(case.label),
                        "description": tr_description(case.description),
                        "icon": case.icon,
                        "option": filter_option_names(case.option),
                    }
                    for case in option.cases or []
                ],
                "inputs": [
                    {
                        "name": input_item.name,
                        "label": tr_text(input_item.label),
                        "description": tr_description(input_item.description),
                        "icon": input_item.icon,
                        "default": input_item.default,
                        "pipelineType": input_item.pipeline_type,
                        "verify": input_item.verify,
                        "verifyError": input_item.verify_error,
                        "patternMsg": input_item.pattern_msg,
                    }
                    for input_item in option.inputs or []
                ],
                "hotkeys": [
                    {
                        "name": hotkey_item.name,
                        "label": tr_text(hotkey_item.label),
                        "description": tr_description(hotkey_item.description),
                        "default": hotkey_item.default,
                    }
                    for hotkey_item in option.hotkeys or []
                ],
                "defaultCase": option.default_case,
            }
            for option_name, option in interface.option.items()
            if option.type in SUPPORTED_OPTION_TYPES
        ],
        presets=presets,
        importCount=len(interface.import_ or []),
        agentCount=agent_count,
        controlCapabilities={"emulatorExtras": build_adb_emulator_extra_capabilities()},
    )


def resolve_description(root_path: Path, description: str | None) -> str | None:
    if not isinstance(description, str):
        return description

    raw_description = description.strip()
    if not raw_description or "\n" in raw_description or raw_description.startswith("<"):
        return description
    if raw_description.startswith(("http://", "https://")):
        return description

    description_path = Path(raw_description)
    if description_path.is_absolute() or ".." in description_path.parts:
        return description

    try:
        root = root_path.resolve()
        resolved_path = (root / description_path).resolve()
        resolved_path.relative_to(root)
    except Exception:
        return description

    if not resolved_path.is_file():
        return description
    if resolved_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        return description

    try:
        if resolved_path.stat().st_size > 512 * 1024:
            return description
        return resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return resolved_path.read_text(encoding="utf-8-sig")
        except Exception:
            return description
    except Exception:
        return description


def _load_i18n_mapping(root_path: Path, interface: MaaFWInterface) -> dict[str, Any]:
    if not interface.languages:
        return {}

    language_file = interface.languages.get("zh_cn")
    if not isinstance(language_file, str) or not language_file.strip():
        return {}

    language_path = _resolve_project_path(root_path, language_file)
    if language_path is None or not language_path.is_file():
        return {}

    try:
        # 走 loader 的 json→json5 快路径：语言文件是 preview 里最贵的一项，
        # MaaEnd 那份 108KB 的 zh_cn.json 用 json5 要 392ms，用 json 只要 0.3ms。
        data = parse_json_text(language_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_task_alias_index(
    root_path: str | Path,
    interface: MaaFWInterface,
) -> dict[str, tuple[str, ...]]:
    """任务名 → 它可能在外壳日志里出现的**全部写法**。

    外壳按自己的界面语言打任务名：中文界面是「任务开始: 信用点购物」，英文界面
    是「Task started: 🛍️ Credit Shopping」，而 interface 里存的是 name
    （``CreditShoppingN2``）与 entry（``CreditShoppingMain``）—— 三者互不相同。
    只认其中一种，换个语言就会把跑成功的运行误判成「选中任务未出现」。

    这里把 name、entry、以及 ``interface.languages`` 里**每一种**语言下解析出的
    label 全都收进来，判断时任一命中即算露面。MAS 手上就有全部语言文件，不必去
    猜外壳当前用的是哪一种。

    Returns:
        ``{任务名: (可能的写法, ...)}``，写法已去重且剔除空串。
    """

    root = Path(root_path).resolve()
    mappings: list[dict[str, Any]] = []
    for relative in (interface.languages or {}).values():
        if not isinstance(relative, str) or not relative.strip():
            continue
        language_path = _resolve_project_path(root, relative)
        if language_path is None or not language_path.is_file():
            continue
        try:
            data = parse_json_text(language_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 —— 语言文件坏了不该影响判定，少一种写法而已
            continue
        if isinstance(data, dict):
            mappings.append(data)

    index: dict[str, tuple[str, ...]] = {}
    for task in interface.task:
        aliases: list[str] = []
        for candidate in (task.name, task.entry):
            if isinstance(candidate, str) and candidate.strip():
                aliases.append(candidate.strip())
        raw_label = task.label
        if isinstance(raw_label, str) and raw_label.strip():
            if not raw_label.startswith("$"):
                aliases.append(raw_label.strip())
            for mapping in mappings:
                translated = _lookup_i18n_text(raw_label, mapping)
                if isinstance(translated, str) and translated.strip():
                    aliases.append(translated.strip())
        deduped: list[str] = []
        for alias in aliases:
            if alias not in deduped:
                deduped.append(alias)
        index[task.name] = tuple(deduped)
    return index


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
    return flat_value if isinstance(flat_value, str) else None


def _resolve_project_path(root_path: Path, raw_path: str) -> Path | None:
    candidate = Path(raw_path.replace("{PROJECT_DIR}", str(root_path)))
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved_path = candidate.resolve()
    try:
        resolved_path.relative_to(root_path.resolve())
    except ValueError:
        return None
    return resolved_path
