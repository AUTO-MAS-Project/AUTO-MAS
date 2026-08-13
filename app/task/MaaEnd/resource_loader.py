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


import hashlib
import json
from _thread import LockType
from pathlib import Path
from threading import Lock
from typing import Any

import json5

from app.utils import get_logger


FileSignature = tuple[tuple[str, int, int], ...]
_options_cache: dict[Path, tuple[FileSignature, tuple[Path, ...], dict[str, Any]]] = {}
_task_i18n_cache: dict[tuple[Path, str], tuple[FileSignature, dict[str, str]]] = {}
_interface_i18n_cache: dict[
    tuple[Path, str], tuple[FileSignature, dict[str, str]]
] = {}
_root_locks: dict[Path, LockType] = {}
_locks_guard = Lock()
SUPPORTED_CONTROLLER_PROTOCOLS = frozenset({"Adb", "Win32"})
_OPTIONS_DISK_CACHE_VERSION = 1
logger = get_logger("MaaEnd 资源加载器")


def _signature(paths: tuple[Path, ...]) -> FileSignature:
    signature = []
    for path in paths:
        stat = path.stat()
        signature.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def _root_lock(root_path: Path) -> LockType:
    with _locks_guard:
        return _root_locks.setdefault(root_path, Lock())


def _options_disk_cache_dir() -> Path:
    return Path.cwd() / "data/cache/maaend_options"


def _options_disk_cache_path(root_path: Path) -> Path:
    cache_key = hashlib.sha256(
        str(root_path).casefold().encode("utf-8")
    ).hexdigest()
    return _options_disk_cache_dir() / f"{cache_key}.json"


def _signature_to_json(signature: FileSignature) -> list[list[str | int]]:
    return [list(part) for part in signature]


def _signature_from_json(value: Any) -> FileSignature | None:
    if not isinstance(value, list):
        return None

    signature: list[tuple[str, int, int]] = []
    for part in value:
        if (
            not isinstance(part, list)
            or len(part) != 3
            or not isinstance(part[0], str)
            or not isinstance(part[1], int)
            or not isinstance(part[2], int)
        ):
            return None
        signature.append((part[0], part[1], part[2]))
    return tuple(signature)


def _load_options_from_disk_cache(
    root_path: Path,
) -> tuple[FileSignature, tuple[Path, ...], dict[str, Any]] | None:
    cache_path = _options_disk_cache_path(root_path)
    if not cache_path.is_file():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        if payload.get("version") != _OPTIONS_DISK_CACHE_VERSION:
            return None

        raw_paths = payload.get("paths")
        signature = _signature_from_json(payload.get("signature"))
        data = payload.get("data")
        if (
            not isinstance(raw_paths, list)
            or signature is None
            or not isinstance(data, dict)
            or len(raw_paths) != len(signature)
            or not all(isinstance(path, str) for path in raw_paths)
            or not isinstance(data.get("controllers"), list)
            or not isinstance(data.get("controllerTypes"), dict)
            or not isinstance(data.get("essenceLocations"), list)
        ):
            return None

        paths = tuple(Path(path) for path in raw_paths)
        if _signature(paths) != signature:
            return None

        logger.debug(f"读取 MaaEnd 选项磁盘缓存：{root_path}")
        return signature, paths, data
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        logger.debug(f"读取 MaaEnd 选项磁盘缓存失败，回退实时解析：{error}")
        return None


def _save_options_to_disk_cache(
    root_path: Path,
    signature: FileSignature,
    paths: tuple[Path, ...],
    data: dict[str, Any],
) -> None:
    cache_path = _options_disk_cache_path(root_path)
    payload = {
        "version": _OPTIONS_DISK_CACHE_VERSION,
        "root_path": str(root_path),
        "paths": [str(path) for path in paths],
        "signature": _signature_to_json(signature),
        "data": data,
    }

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = cache_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(cache_path)
        logger.debug(f"写入 MaaEnd 选项磁盘缓存：{cache_path}")
    except (OSError, TypeError, ValueError) as error:
        logger.debug(f"写入 MaaEnd 选项磁盘缓存失败：{error}")


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

        disk_cached = _load_options_from_disk_cache(root_path)
        if disk_cached is not None:
            _options_cache[root_path] = disk_cached
            return disk_cached[2]

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
        controller_cases = [
            case
            for case in interface["controller"]
            if case["type"] in SUPPORTED_CONTROLLER_PROTOCOLS
        ]
        data = {
            "controllers": options(controller_cases),
            "controllerTypes": {
                case["name"]: case["type"] for case in controller_cases
            },
            "essenceLocations": options(
                task["option"]["AutoEssenceChooseLocation"]["cases"]
            ),
        }
        paths = (config_path, interface_path, locale_path, task_path)
        signature = _signature(paths)
        _options_cache[root_path] = (signature, paths, data)
        _save_options_to_disk_cache(root_path, signature, paths, data)
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
