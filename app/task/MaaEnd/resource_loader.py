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


from pathlib import Path
from typing import Any

import json5


SUPPORTED_CONTROLLER_PROTOCOLS = frozenset({"Adb", "Win32"})
LEGACY_CONTROLLER_PROTOCOLS = {"ADB": "Adb", "Win32-Front": "Win32"}


def _normalize_language(language: str) -> str:
    return (
        "zh_cn" if language.lower() == "system" else language.lower().replace("-", "_")
    )


def _load_maaend_interface(root_path: Path) -> tuple[Path, dict[str, Any]]:
    interface_path = root_path / "interface.json"
    interface = json5.loads(interface_path.read_text(encoding="utf-8"))
    return interface_path, interface


def _load_maaend_interface_i18n(
    interface_path: Path,
    interface: dict[str, Any],
    language: str,
) -> dict[str, str]:
    language = _normalize_language(language)
    try:
        locale_path = (
            interface_path.parent / interface["languages"][language]
        ).resolve()
    except KeyError as error:
        raise ValueError(f"MaaEnd 不支持语言 {language}: {interface_path}") from error
    return json5.loads(locale_path.read_text(encoding="utf-8"))


def load_maaend_interface_i18n(
    root_path: Path,
    language: str,
) -> dict[str, str]:
    """加载 MaaEnd Interface 本地化资源。"""

    interface_path, interface = _load_maaend_interface(root_path.resolve())
    return _load_maaend_interface_i18n(interface_path, interface, language)


def load_maaend_controller_protocol(root_path: Path, controller_name: str) -> str:
    """读取 MaaEnd 控制器协议。"""

    interface_path, interface = _load_maaend_interface(root_path.resolve())
    for controller in interface["controller"]:
        if controller["name"] == controller_name:
            protocol = controller["type"]
            if protocol not in SUPPORTED_CONTROLLER_PROTOCOLS:
                raise ValueError(f"MaaEnd 控制器协议不受支持: {protocol}")
            return protocol
    if controller_name in LEGACY_CONTROLLER_PROTOCOLS:
        return LEGACY_CONTROLLER_PROTOCOLS[controller_name]
    raise ValueError(f"MaaEnd 控制器不存在: {controller_name} ({interface_path})")


def load_maaend_options(root_path: Path) -> dict[str, Any]:
    """加载 MaaEnd 控制器与基质刷取选项。"""

    root_path = root_path.resolve()
    config_path = root_path / "config/mxu-MaaEnd.json"
    config = json5.loads(config_path.read_text(encoding="utf-8"))
    interface_path, interface = _load_maaend_interface(root_path)
    locale = _load_maaend_interface_i18n(
        interface_path,
        interface,
        str(config["settings"]["language"]),
    )

    def options(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
        result = []
        for case in cases:
            label = case.get("label")
            if isinstance(label, str) and label.startswith("$"):
                try:
                    label = locale[label[1:]]
                except KeyError as error:
                    raise ValueError(
                        f"MaaEnd 选项缺少本地化文本: {case['name']}"
                    ) from error
            result.append({"label": label or case["name"], "value": case["name"]})
        return result

    controller_cases = [
        controller
        for controller in interface["controller"]
        if controller["type"] in SUPPORTED_CONTROLLER_PROTOCOLS
    ]
    essence_location_cases: list[dict[str, Any]] = []
    task_path = next(
        (
            (interface_path.parent / path).resolve()
            for path in interface["import"]
            if Path(path).stem == "AutoEssence"
        ),
        None,
    )
    if task_path is not None:
        task = json5.loads(task_path.read_text(encoding="utf-8"))
        essence_option = task.get("option", {}).get("AutoEssenceChooseLocation")
        if essence_option is not None:
            essence_location_cases = essence_option["cases"]

    return {
        "controllers": options(controller_cases),
        "controllerTypes": {
            controller["name"]: controller["type"] for controller in controller_cases
        },
        "essenceLocations": options(essence_location_cases),
    }


def load_maaend_task_i18n(
    root_path: Path,
    language: str,
) -> dict[str, str]:
    """加载 MaaEnd 任务名称映射。"""

    root_path = root_path.resolve()
    interface_path, interface = _load_maaend_interface(root_path)
    locale = _load_maaend_interface_i18n(interface_path, interface, language)
    result = {}
    for path in interface["import"]:
        task_path = (interface_path.parent / path).resolve()
        tasks = json5.loads(task_path.read_text(encoding="utf-8")).get("task", [])
        for task in tasks:
            label = task["label"]
            if isinstance(label, str) and label.startswith("$"):
                try:
                    label = locale[label[1:]]
                except KeyError as error:
                    raise ValueError(
                        f"MaaEnd 任务缺少本地化文本: {task['name']}"
                    ) from error
            result[task["name"]] = label
    return result
