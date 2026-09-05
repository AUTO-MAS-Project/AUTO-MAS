#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import hashlib
import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

import json5

from app.utils import get_logger
from app.utils.io import atomic_write

logger = get_logger("MaaEnd 资源加载器")

SUPPORTED_CONTROLLER_PROTOCOLS = frozenset({"Adb", "Win32"})
LEGACY_CONTROLLER_PROTOCOLS = {"ADB": "Adb", "Win32-Front": "Win32"}


def _normalize_language(language: str) -> str:
    return (
        "zh_cn" if language.lower() == "system" else language.lower().replace("-", "_")
    )


class MaaEndResourceLoader:
    """按 MaaEnd 根目录缓存解析后的动态资源。"""

    _disk_cache_version = 3
    _loader_cache: dict[Path, "MaaEndResourceLoader"] = {}
    _cache_lock = RLock()

    def __init__(
        self,
        root_path: Path,
        file_cache: dict[Path, tuple[tuple, Any]] | None = None,
    ):
        self.root_path = root_path.resolve()
        self._file_cache = dict(file_cache or {})
        self._cache_dirty = False
        self._interface: dict[str, Any] = {}
        self._locales: dict[str, dict[str, str]] = {}
        self._tasks: list[dict[str, Any]] = []
        self._task_options: dict[str, dict[str, Any]] = {}
        self._options: dict[str, Any] = {}
        self._tasks_loaded = False
        self._load_all_resources()

    @classmethod
    def get_cached(
        cls,
        root_path: Path,
        force_reload: bool = False,
    ) -> "MaaEndResourceLoader":
        """校验资源指纹，并读取磁盘缓存或重新解析资源。"""

        root_path = root_path.resolve()
        with cls._cache_lock:
            cached = cls._loader_cache.get(root_path)
            if cached is not None and not force_reload:
                return cached

            if force_reload:
                cls._loader_cache.pop(root_path, None)

            if not force_reload:
                loader = cls._load_from_disk_cache(root_path)
                if loader is not None:
                    cls._loader_cache[root_path] = loader
                    return loader

            try:
                loader = cls(root_path)
            except Exception as error:
                raise ValueError(f"MaaEnd 文件不完整: {error}") from error
            cls._loader_cache[root_path] = loader
            loader._save_disk_cache()
            return loader

    @classmethod
    def get_loaded(cls, root_path: Path) -> "MaaEndResourceLoader":
        """直接读取已经载入进程内存的资源。"""

        root_path = root_path.resolve()
        with cls._cache_lock:
            loader = cls._loader_cache.get(root_path)
        if loader is None:
            return cls.get_cached(root_path)
        return loader

    @classmethod
    def _disk_cache_path(cls, root_path: Path) -> Path:
        cache_key = hashlib.sha256(
            str(root_path).casefold().encode("utf-8")
        ).hexdigest()
        return Path.cwd() / "data/cache/maaend_resource_loader" / f"{cache_key}.json"

    @staticmethod
    def _file_signature(path: Path) -> tuple:
        try:
            stat = path.stat()
        except OSError:
            return ("missing", str(path), 0, 0)
        return ("file", str(path), stat.st_mtime_ns, stat.st_size)

    @classmethod
    def _load_from_disk_cache(
        cls,
        root_path: Path,
    ) -> "MaaEndResourceLoader | None":
        cache_path = cls._disk_cache_path(root_path)
        if not cache_path.is_file():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("version") != cls._disk_cache_version
            ):
                return None

            file_cache: dict[Path, tuple[tuple, Any]] = {}
            for raw_path, entry in payload["files"].items():
                signature = tuple(entry["signature"])
                path = Path(raw_path)
                if cls._file_signature(path) == signature:
                    file_cache[path] = (signature, entry["data"])

            loader = cls(root_path, file_cache=file_cache)
            loader._save_disk_cache()
            logger.info(f"读取 MaaEnd 源文件资源缓存：{root_path}")
            return loader
        except Exception as error:
            logger.warning(f"读取 MaaEnd 源文件资源缓存失败，重新解析资源：{error}")
            return None

    def _save_disk_cache(self) -> None:
        if not self._cache_dirty:
            return

        cache_path = self._disk_cache_path(self.root_path)
        try:
            payload = {
                "version": self._disk_cache_version,
                "files": {
                    str(path): {
                        "signature": list(signature),
                        "data": data,
                    }
                    for path, (signature, data) in self._file_cache.items()
                },
            }
            atomic_write(
                cache_path,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            self._cache_dirty = False
            logger.debug(f"已更新 MaaEnd 源文件资源缓存：{cache_path}")
        except Exception as error:
            logger.warning(f"写入 MaaEnd 源文件资源缓存失败：{error}")

    def _read_json5(self, path: Path) -> Any:
        path = path.resolve()
        signature = self._file_signature(path)

        cached = self._file_cache.get(path)
        if cached is not None and cached[0] == signature:
            return deepcopy(cached[1])

        data = json5.loads(path.read_text(encoding="utf-8"))
        self._file_cache[path] = (signature, deepcopy(data))
        self._cache_dirty = True
        return data

    def _load_all_resources(self) -> None:
        interface_path = self.root_path / "interface.json"
        interface = self._read_json5(interface_path)
        if not isinstance(interface, dict):
            raise ValueError("MaaEnd interface 不是 JSON 对象")

        self._interface = interface
        active_paths = {interface_path.resolve()}
        for language, relative_path in interface["languages"].items():
            locale_path = (interface_path.parent / relative_path).resolve()
            active_paths.add(locale_path)
            locale = self._read_json5(locale_path)
            if not isinstance(locale, dict):
                raise ValueError(f"MaaEnd 本地化资源不是 JSON 对象: {relative_path}")
            self._locales[_normalize_language(str(language))] = locale

        active_paths.update(
            (interface_path.parent / relative_path).resolve()
            for relative_path in interface["import"]
        )

        essence_resource = next(
            (
                relative_path
                for relative_path in interface["import"]
                if Path(relative_path).stem == "AutoEssence"
            ),
            None,
        )
        if essence_resource is not None:
            task_data = self._read_json5(interface_path.parent / essence_resource)
            if not isinstance(task_data, dict):
                raise ValueError(f"MaaEnd 任务资源不是 JSON 对象: {essence_resource}")
            options = task_data.get("option", {})
            if not isinstance(options, dict):
                raise ValueError(f"MaaEnd 任务选项格式错误: {essence_resource}")
            self._task_options[Path(essence_resource).stem] = options

        self._options = self._build_options("zh_cn")
        stale_paths = set(self._file_cache) - active_paths
        for path in stale_paths:
            self._file_cache.pop(path, None)
        self._cache_dirty = self._cache_dirty or bool(stale_paths)

    def _load_task_resources(self) -> None:
        with self._cache_lock:
            if self._tasks_loaded:
                return

            interface_path = self.root_path / "interface.json"
            for relative_path in self._interface["import"]:
                try:
                    task_data = self._read_json5(interface_path.parent / relative_path)
                except (OSError, ValueError) as error:
                    logger.warning(
                        f"MaaEnd 任务资源读取失败，已跳过 {relative_path}: {error}"
                    )
                    continue
                if not isinstance(task_data, dict):
                    logger.warning(f"MaaEnd 任务资源格式错误，已跳过: {relative_path}")
                    continue
                tasks = task_data.get("task", [])
                if not isinstance(tasks, list):
                    logger.warning(f"MaaEnd 任务列表格式错误，已跳过: {relative_path}")
                    continue
                self._tasks.extend(task for task in tasks if isinstance(task, dict))

            self._tasks_loaded = True
            self._save_disk_cache()

    def _get_locale(self, language: str) -> dict[str, str]:
        language = _normalize_language(language)
        try:
            return self._locales[language]
        except KeyError as error:
            raise ValueError(
                f"MaaEnd 不支持语言 {language}: {self.root_path / 'interface.json'}"
            ) from error

    @staticmethod
    def _localize_options(
        cases: list[dict[str, Any]],
        locale: dict[str, str],
    ) -> list[dict[str, str]]:
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

    def _build_options(self, language: str) -> dict[str, Any]:
        locale = self._get_locale(language)
        controller_cases = [
            controller
            for controller in self._interface["controller"]
            if controller["type"] in SUPPORTED_CONTROLLER_PROTOCOLS
        ]
        essence_location_cases: list[dict[str, Any]] = []
        essence_option = self._task_options.get("AutoEssence", {}).get(
            "AutoEssenceChooseLocation"
        )
        if essence_option is not None:
            essence_location_cases = essence_option["cases"]

        return {
            "controllers": self._localize_options(controller_cases, locale),
            "controllerTypes": {
                controller["name"]: controller["type"]
                for controller in controller_cases
            },
            "essenceLocations": self._localize_options(essence_location_cases, locale),
        }

    def get_options(self) -> dict[str, Any]:
        return deepcopy(self._options)

    def get_interface_i18n(self, language: str) -> dict[str, str]:
        return deepcopy(self._get_locale(language))

    def get_controller_protocol(self, controller_name: str) -> str:
        for controller in self._interface["controller"]:
            if controller["name"] == controller_name:
                protocol = controller["type"]
                if protocol not in SUPPORTED_CONTROLLER_PROTOCOLS:
                    raise ValueError(f"MaaEnd 控制器协议不受支持: {protocol}")
                return protocol
        if controller_name in LEGACY_CONTROLLER_PROTOCOLS:
            return LEGACY_CONTROLLER_PROTOCOLS[controller_name]
        raise ValueError(
            f"MaaEnd 控制器不存在: {controller_name} ({self.root_path / 'interface.json'})"
        )

    def get_task_i18n(self, language: str) -> dict[str, str]:
        self._load_task_resources()
        locale = self._get_locale(language)
        result = {}
        for task in self._tasks:
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


def load_maaend_interface_i18n(root_path: Path, language: str) -> dict[str, str]:
    """从内存资源加载 MaaEnd Interface 本地化文本。"""

    return MaaEndResourceLoader.get_loaded(root_path).get_interface_i18n(language)


def load_maaend_controller_protocol(root_path: Path, controller_name: str) -> str:
    """从内存资源读取 MaaEnd 控制器协议。"""

    return MaaEndResourceLoader.get_loaded(root_path).get_controller_protocol(
        controller_name
    )


def load_maaend_options(root_path: Path, force_reload: bool = False) -> dict[str, Any]:
    """校验缓存并加载 MaaEnd 控制器与基质刷取选项。"""

    return MaaEndResourceLoader.get_cached(
        root_path,
        force_reload=force_reload,
    ).get_options()


def try_load_maaend_options(root_path: Path) -> dict[str, Any] | None:
    """尝试预加载 MaaEnd 动态选项，失败时记录原因并跳过。"""

    try:
        return load_maaend_options(root_path)
    except Exception as error:
        logger.warning(f"MaaEnd 动态资源加载失败: {error}")
        return None


def get_loaded_maaend_options(root_path: Path) -> dict[str, Any]:
    """直接读取进程内存中的 MaaEnd 动态选项。"""

    return MaaEndResourceLoader.get_loaded(root_path).get_options()


def load_maaend_task_i18n(root_path: Path, language: str) -> dict[str, str]:
    """从内存资源加载 MaaEnd 任务名称映射。"""

    return MaaEndResourceLoader.get_loaded(root_path).get_task_i18n(language)
