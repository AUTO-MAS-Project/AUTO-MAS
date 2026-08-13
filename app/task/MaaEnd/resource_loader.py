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
from _thread import LockType
from pathlib import Path
from threading import Lock
from typing import Any

import json5


FileSignature = tuple[tuple[str, int, int], ...]
_options_cache: dict[Path, tuple[FileSignature, tuple[Path, ...], dict[str, Any]]] = {}
_task_i18n_cache: dict[tuple[Path, str], tuple[FileSignature, dict[str, str]]] = {}
_interface_i18n_cache: dict[
    tuple[Path, str], tuple[FileSignature, dict[str, str]]
] = {}
_root_locks: dict[Path, LockType] = {}
_locks_guard = Lock()


def _signature(paths: tuple[Path, ...]) -> FileSignature:
    signature = []
    for path in paths:
        stat = path.stat()
        signature.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def _root_lock(root_path: Path) -> LockType:
    with _locks_guard:
        return _root_locks.setdefault(root_path, Lock())


def _normalize_language(language: str) -> str:
    return (
        "zh_cn"
        if language.lower() == "system"
        else language.lower().replace("-", "_")
    )


def _load_maaend_interface_i18n(
    root_path: Path,
    language: str,
) -> tuple[Path, dict[str, str]]:
    locale_path = root_path / f"locales/interface/{language}.json"
    paths = (locale_path,)
    signature = _signature(paths)
    cache_key = (root_path, language)
    cached = _interface_i18n_cache.get(cache_key)
    if cached is not None and cached[0] == signature:
        return locale_path, cached[1]

    locale = json.loads(locale_path.read_text(encoding="utf-8"))
    _interface_i18n_cache[cache_key] = (signature, locale)
    return locale_path, locale


def load_maaend_interface_i18n(
    root_path: Path,
    language: str,
) -> dict[str, str]:
    """加载并缓存 MaaEnd Interface 本地化资源。"""

    root_path = root_path.resolve()
    language = _normalize_language(language)
    with _root_lock(root_path):
        return _load_maaend_interface_i18n(root_path, language)[1]


def load_maaend_options(root_path: Path) -> dict[str, Any]:
    """加载并缓存 MaaEnd 控制器与基质刷取选项。"""

    root_path = root_path.resolve()
    with _root_lock(root_path):
        cached = _options_cache.get(root_path)
        if cached is not None:
            signature, paths, data = cached
            try:
                if _signature(paths) == signature:
                    return data
            except OSError:
                pass

        config_path = root_path / "config/mxu-MaaEnd.json"
        interface_path = root_path / "interface.json"
        config = json5.loads(config_path.read_text(encoding="utf-8"))
        interface = json5.loads(interface_path.read_text(encoding="utf-8"))
        language = str(config["settings"]["language"])
        language = (
            "zh_cn"
            if language.lower() == "system"
            else language.lower().replace("-", "_")
        )
        locale_path = (
            interface_path.parent / interface["languages"][language]
        ).resolve()
        locale = json5.loads(locale_path.read_text(encoding="utf-8"))

        def options(cases: list[dict[str, str]]) -> list[dict[str, str]]:
            return [
                {
                    "label": locale.get(case["label"][1:], case["name"])
                    if (case.get("label") or "").startswith("$")
                    else case.get("label") or case["name"],
                    "value": case["name"],
                }
                for case in cases
            ]

        task_path = next(
            (
                (interface_path.parent / path).resolve()
                for path in interface["import"]
                if Path(path).stem == "AutoEssence"
            ),
            None,
        )
        if task_path is None:
            raise ValueError(
                f"MaaEnd Interface 未导入 AutoEssence 任务: {interface_path}"
            )

        task = json5.loads(task_path.read_text(encoding="utf-8"))
        data = {
            "controllers": options(interface["controller"]),
            "controllerTypes": {
                case["name"]: case["type"] for case in interface["controller"]
            },
            "essenceLocations": options(
                task["option"]["AutoEssenceChooseLocation"]["cases"]
            ),
        }
        paths = (config_path, interface_path, locale_path, task_path)
        _options_cache[root_path] = (_signature(paths), paths, data)
        return data


def load_maaend_task_i18n(root_path: Path, language: str) -> dict[str, str]:
    """加载并缓存 MaaEnd 任务名称的本地化映射。"""

    root_path = root_path.resolve()
    language = _normalize_language(language)
    cache_key = (root_path, language)

    with _root_lock(root_path):
        locale_path, locale = _load_maaend_interface_i18n(root_path, language)
        task_paths = tuple(sorted(root_path.glob("tasks/*.json")))
        paths = (locale_path, *task_paths)
        signature = _signature(paths)
        cached = _task_i18n_cache.get(cache_key)
        if cached is not None and cached[0] == signature:
            return cached[1]

        data: dict[str, str] = {}
        for task_path in task_paths:
            task = json5.loads(task_path.read_text(encoding="utf-8"))["task"][0]
            label = task["label"]
            if label.startswith("$"):
                label = locale.get(label.lstrip("$"))
                if label is None:
                    raise RuntimeError("MaaEnd 文件不完整，卸载后重新安装MaaEnd")
            data[task["name"]] = label

        _task_i18n_cache[cache_key] = (signature, data)
        return data
