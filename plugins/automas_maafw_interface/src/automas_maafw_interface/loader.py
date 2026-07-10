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


import copy
import hashlib
import json
import logging
import time
from pathlib import Path
from threading import RLock
from typing import Any

import json5

from .models import MaaFWInterface, MaaFWOption, MaaFWOptionCase


IMPORTABLE_KEYS = {"task", "option", "preset", "import"}
logger = logging.getLogger("automas.maafw.interface.loader")

DISK_CACHE_VERSION = 1
DISK_CACHE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
DISK_CACHE_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
_interface_cache: dict[Path, tuple[tuple, MaaFWInterface, set[Path], set[tuple[Path, str]]]] = {}
_cache_lock = RLock()
_last_disk_cache_cleanup_at = 0.0


class MaaFWInterfaceLoadError(ValueError):
    """Raised when a MaaFW ProjectInterface cannot be loaded safely."""


class _MergeState:
    def __init__(self) -> None:
        self.task_names: dict[str, Path] = {}
        self.option_keys: dict[str, Path] = {}
        self.preset_names: dict[str, Path] = {}


class _LoadContext:
    def __init__(self) -> None:
        self.dependency_paths: set[Path] = set()
        self.scan_select_specs: set[tuple[Path, str]] = set()


def _read_json_dict(path: Path, context: _LoadContext | None = None) -> dict[str, Any]:
    if context is not None:
        context.dependency_paths.add(path.resolve())

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json5.load(file)
    except FileNotFoundError as exc:
        raise MaaFWInterfaceLoadError(f"找不到 interface 配置文件: {path}") from exc
    except Exception as exc:
        raise MaaFWInterfaceLoadError(f"解析 interface 配置失败: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise MaaFWInterfaceLoadError(f"interface 配置文件必须是 JSON 对象: {path}")
    return data


def _normalize_import_list(raw_value: Any, source_path: Path) -> list[str]:
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise MaaFWInterfaceLoadError(f"import 字段必须是字符串数组: {source_path}")
    if not all(isinstance(item, str) and item.strip() for item in raw_value):
        raise MaaFWInterfaceLoadError(f"import 字段必须是非空字符串数组: {source_path}")
    return raw_value


def _normalize_project_relative_path(raw_path: str, *, field_name: str) -> str:
    normalized_path = raw_path.strip().replace("\\", "/")
    if not normalized_path:
        raise MaaFWInterfaceLoadError(f"{field_name} 不能为空")

    candidate = Path(normalized_path)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise MaaFWInterfaceLoadError(f"{field_name} 不允许使用绝对路径: {raw_path}")

    parts: list[str] = []
    for part in normalized_path.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise MaaFWInterfaceLoadError(f"{field_name} 不允许包含 .. 路径段: {raw_path}")
        parts.append(part)

    if not parts:
        raise MaaFWInterfaceLoadError(f"{field_name} 不能为空")
    return "/".join(parts)


def _is_within_base_dir(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _resolve_project_relative_path(
    base_dir: Path,
    raw_path: str,
    *,
    field_name: str,
) -> Path:
    normalized_path = _normalize_project_relative_path(raw_path, field_name=field_name)
    resolved_path = (base_dir / normalized_path).resolve()
    if not _is_within_base_dir(resolved_path, base_dir):
        raise MaaFWInterfaceLoadError(
            f"{field_name} 越界，禁止访问 MaaFW 项目目录之外的路径: {raw_path}"
        )
    return resolved_path


def _resolve_interface_path(base_dir: Path) -> Path:
    for file_name in ("interface.json", "interface.jsonc"):
        interface_path = (base_dir / file_name).resolve()
        if interface_path.exists():
            if not _is_within_base_dir(interface_path, base_dir):
                raise MaaFWInterfaceLoadError(f"{file_name} 不在 MaaFW 项目目录内")
            return interface_path
    raise MaaFWInterfaceLoadError("请设置包含 interface.json 的 MaaFW 项目目录")


def _resolve_import_path(import_path: str, base_dir: Path) -> Path:
    resolved_path = _resolve_project_relative_path(
        base_dir,
        import_path,
        field_name="import",
    )
    if not resolved_path.exists() or not resolved_path.is_file():
        raise MaaFWInterfaceLoadError(f"import 文件不存在: {import_path}")
    return resolved_path


def _validate_importable_fragment(data: dict[str, Any], source_path: Path) -> None:
    invalid_keys = sorted(set(data) - IMPORTABLE_KEYS)
    if invalid_keys:
        raise MaaFWInterfaceLoadError(
            f"导入文件只允许包含 task、option、preset、import 字段: {source_path}; "
            f"发现非法字段 {', '.join(invalid_keys)}"
        )


def _raise_conflict(
    kind: str,
    key: str,
    source_path: Path,
    existing_path: Path,
) -> None:
    raise MaaFWInterfaceLoadError(
        f"{kind} 冲突: {key} 已在 {existing_path} 定义，无法再次从 {source_path} 导入"
    )


def _register_tasks(tasks: Any, source_path: Path, state: _MergeState) -> None:
    if tasks is None:
        return
    if not isinstance(tasks, list):
        raise MaaFWInterfaceLoadError(f"task 字段必须是数组: {source_path}")

    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise MaaFWInterfaceLoadError(f"task[{index}] 必须是对象: {source_path}")

        task_name = task.get("name")
        task_entry = task.get("entry")
        if not isinstance(task_name, str) or not task_name:
            raise MaaFWInterfaceLoadError(
                f"task[{index}].name 必须是非空字符串: {source_path}"
            )
        if not isinstance(task_entry, str) or not task_entry:
            raise MaaFWInterfaceLoadError(
                f"task[{index}].entry 必须是非空字符串: {source_path}"
            )

        existing_name = state.task_names.get(task_name)
        if existing_name is not None:
            _raise_conflict("task.name", task_name, source_path, existing_name)

        state.task_names[task_name] = source_path


def _register_options(options: Any, source_path: Path, state: _MergeState) -> None:
    if options is None:
        return
    if not isinstance(options, dict):
        raise MaaFWInterfaceLoadError(f"option 字段必须是对象: {source_path}")

    for option_key in options:
        if not isinstance(option_key, str) or not option_key:
            raise MaaFWInterfaceLoadError(f"option 键必须是非空字符串: {source_path}")

        existing_path = state.option_keys.get(option_key)
        if existing_path is not None:
            _raise_conflict("option", option_key, source_path, existing_path)
        state.option_keys[option_key] = source_path


def _register_presets(presets: Any, source_path: Path, state: _MergeState) -> None:
    if presets is None:
        return
    if not isinstance(presets, list):
        raise MaaFWInterfaceLoadError(f"preset 字段必须是数组: {source_path}")

    for index, preset in enumerate(presets):
        if not isinstance(preset, dict):
            raise MaaFWInterfaceLoadError(f"preset[{index}] 必须是对象: {source_path}")

        preset_name = preset.get("name")
        if not isinstance(preset_name, str) or not preset_name:
            raise MaaFWInterfaceLoadError(
                f"preset[{index}].name 必须是非空字符串: {source_path}"
            )

        existing_path = state.preset_names.get(preset_name)
        if existing_path is not None:
            _raise_conflict("preset", preset_name, source_path, existing_path)
        state.preset_names[preset_name] = source_path


def _seed_root_sections(
    root_data: dict[str, Any],
    source_path: Path,
    state: _MergeState,
) -> None:
    _register_tasks(root_data.get("task"), source_path, state)
    _register_options(root_data.get("option"), source_path, state)
    _register_presets(root_data.get("preset"), source_path, state)


def _merge_fragment_sections(
    target: dict[str, Any],
    fragment: dict[str, Any],
    source_path: Path,
    state: _MergeState,
) -> None:
    tasks = fragment.get("task")
    options = fragment.get("option")
    presets = fragment.get("preset")

    _register_tasks(tasks, source_path, state)
    _register_options(options, source_path, state)
    _register_presets(presets, source_path, state)

    if tasks:
        target.setdefault("task", [])
        target["task"].extend(copy.deepcopy(tasks))
    if options:
        target.setdefault("option", {})
        target["option"].update(copy.deepcopy(options))
    if presets:
        target.setdefault("preset", [])
        target["preset"].extend(copy.deepcopy(presets))


def _merge_imports_into_target(
    target: dict[str, Any],
    import_paths: list[str],
    base_dir: Path,
    state: _MergeState,
    stack: list[Path],
    context: _LoadContext | None = None,
) -> None:
    for import_path in import_paths:
        resolved_path = _resolve_import_path(import_path, base_dir)
        if resolved_path in stack:
            chain = " -> ".join(str(item) for item in [*stack, resolved_path])
            raise MaaFWInterfaceLoadError(f"检测到循环导入: {chain}")

        fragment = _read_json_dict(resolved_path, context)
        _validate_importable_fragment(fragment, resolved_path)

        child_imports = _normalize_import_list(fragment.get("import"), resolved_path)
        _merge_imports_into_target(
            target,
            child_imports,
            base_dir,
            state,
            [*stack, resolved_path],
            context,
        )
        _merge_fragment_sections(target, fragment, resolved_path, state)


def _scan_scan_select_cases(
    option_name: str,
    option_data: dict[str, Any],
    base_dir: Path,
    context: _LoadContext | None = None,
) -> list[dict[str, str]]:
    raw_cases = option_data.get("cases")
    if raw_cases is not None and (not isinstance(raw_cases, list) or raw_cases):
        raise MaaFWInterfaceLoadError(
            f"scan_select 选项 {option_name} 的 cases 必须省略或为空数组"
        )

    scan_dir = option_data.get("scan_dir")
    scan_filter = option_data.get("scan_filter")
    if not isinstance(scan_dir, str) or not scan_dir.strip():
        raise MaaFWInterfaceLoadError(
            f"scan_select 选项 {option_name} 的 scan_dir 必须是非空字符串"
        )
    if not isinstance(scan_filter, str) or not scan_filter.strip():
        raise MaaFWInterfaceLoadError(
            f"scan_select 选项 {option_name} 的 scan_filter 必须是非空字符串"
        )

    resolved_scan_dir = _resolve_project_relative_path(
        base_dir,
        scan_dir,
        field_name=f"scan_select 选项 {option_name} 的 scan_dir",
    )
    normalized_scan_filter = _normalize_project_relative_path(
        scan_filter,
        field_name=f"scan_select 选项 {option_name} 的 scan_filter",
    )
    if context is not None:
        context.scan_select_specs.add((resolved_scan_dir, normalized_scan_filter))

    if not resolved_scan_dir.exists() or not resolved_scan_dir.is_dir():
        raise MaaFWInterfaceLoadError(
            f"scan_select 选项 {option_name} 的 scan_dir 不存在或不是目录: {scan_dir}"
        )

    try:
        matched_paths = sorted(
            {
                file_path.relative_to(resolved_scan_dir).as_posix()
                for file_path in resolved_scan_dir.glob(normalized_scan_filter)
                if file_path.is_file()
            }
        )
    except Exception as exc:
        raise MaaFWInterfaceLoadError(
            f"scan_select 选项 {option_name} 扫描失败: {scan_filter}"
        ) from exc

    return [{"name": path, "label": path} for path in matched_paths]


def _expand_scan_select_options(
    data: dict[str, Any],
    base_dir: Path,
    context: _LoadContext | None = None,
) -> None:
    options = data.get("option")
    if not isinstance(options, dict):
        return

    for option_name, option_data in options.items():
        if not isinstance(option_data, dict):
            continue
        if option_data.get("type") != "scan_select":
            continue
        option_data["cases"] = _scan_scan_select_cases(
            option_name,
            option_data,
            base_dir,
            context,
        )


def _collect_reachable_option_names(
    option_names: list[str],
    option_map: dict[str, MaaFWOption],
    collected: set[str],
) -> None:
    for option_name in option_names:
        option = option_map.get(option_name)
        if option is None:
            raise MaaFWInterfaceLoadError(f"任务引用了不存在的选项: {option_name}")
        if option_name in collected:
            continue

        collected.add(option_name)
        for case_item in option.cases or []:
            if case_item.option:
                _collect_reachable_option_names(case_item.option, option_map, collected)


def _validate_option_name_list(
    option_names: list[str] | None,
    option_map: dict[str, MaaFWOption],
    *,
    location: str,
) -> None:
    for option_name in option_names or []:
        if option_name not in option_map:
            raise MaaFWInterfaceLoadError(f"{location} 引用了不存在的选项: {option_name}")


def _validate_option_case_values(
    option_name: str,
    option: MaaFWOption,
    value: Any,
    *,
    location: str,
) -> None:
    case_names = {case.name for case in option.cases or []}

    if option.type in {"select", "switch", "scan_select"}:
        if not isinstance(value, str):
            raise MaaFWInterfaceLoadError(f"{location}.{option_name} 必须是字符串")
        if value not in case_names:
            raise MaaFWInterfaceLoadError(
                f"{location}.{option_name} 引用了不存在的 case: {value}"
            )
        return

    if option.type == "checkbox":
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise MaaFWInterfaceLoadError(f"{location}.{option_name} 必须是字符串数组")
        invalid_cases = [item for item in value if item not in case_names]
        if invalid_cases:
            raise MaaFWInterfaceLoadError(
                f"{location}.{option_name} 引用了不存在的 case: {', '.join(invalid_cases)}"
            )
        return

    if option.type == "input":
        if not isinstance(value, dict):
            raise MaaFWInterfaceLoadError(f"{location}.{option_name} 必须是对象")
        input_names = {input_item.name for input_item in option.inputs or []}
        for input_name, input_value in value.items():
            if input_name not in input_names:
                raise MaaFWInterfaceLoadError(
                    f"{location}.{option_name} 引用了不存在的输入项: {input_name}"
                )
            if not isinstance(input_value, str):
                raise MaaFWInterfaceLoadError(
                    f"{location}.{option_name}.{input_name} 必须是字符串"
                )


def _validate_task_context_constraints(interface_model: MaaFWInterface) -> None:
    resource_names = {resource.name for resource in interface_model.resource}
    controller_names = {controller.name for controller in interface_model.controller}

    for resource in interface_model.resource:
        for controller_name in resource.controller or []:
            if controller_name not in controller_names:
                raise MaaFWInterfaceLoadError(
                    f"resource {resource.name} 引用了不存在的 controller: {controller_name}"
                )

    for task in interface_model.task:
        task_ref = f"{task.name}({task.entry})"
        for controller_name in task.controller or []:
            if controller_name not in controller_names:
                raise MaaFWInterfaceLoadError(
                    f"任务 {task_ref} 引用了不存在的 controller: {controller_name}"
                )
        for resource_name in task.resource or []:
            if resource_name not in resource_names:
                raise MaaFWInterfaceLoadError(
                    f"任务 {task_ref} 引用了不存在的 resource: {resource_name}"
                )


def _validate_option_references(interface_model: MaaFWInterface) -> None:
    option_map = interface_model.option
    _validate_option_name_list(
        interface_model.global_option,
        option_map,
        location="global_option",
    )

    for resource in interface_model.resource:
        _validate_option_name_list(
            resource.option,
            option_map,
            location=f"resource {resource.name}",
        )

    for controller in interface_model.controller:
        _validate_option_name_list(
            controller.option,
            option_map,
            location=f"controller {controller.name}",
        )

    for task in interface_model.task:
        _validate_option_name_list(
            task.option,
            option_map,
            location=f"task {task.name}",
        )


def _validate_presets(interface_model: MaaFWInterface) -> None:
    task_name_map = {task.name: task for task in interface_model.task}
    option_map = interface_model.option
    common_option_names = _build_common_option_names(interface_model)
    reachable_options_by_task: dict[str, set[str]] = {}

    for task in interface_model.task:
        collected: set[str] = set()
        _collect_reachable_option_names(common_option_names, option_map, collected)
        _collect_reachable_option_names(task.option or [], option_map, collected)
        reachable_options_by_task[task.name] = collected

    for preset in interface_model.preset:
        seen_task_names: set[str] = set()
        for preset_task in preset.task or []:
            if preset_task.name in seen_task_names:
                raise MaaFWInterfaceLoadError(
                    f"preset {preset.name} 中存在重复任务: {preset_task.name}"
                )
            seen_task_names.add(preset_task.name)

            task = task_name_map.get(preset_task.name)
            if task is None:
                continue

            reachable_options = reachable_options_by_task.get(task.name, set())
            for option_name, option_value in (preset_task.option or {}).items():
                if option_name not in reachable_options:
                    continue
                option = option_map.get(option_name)
                if option is None:
                    continue
                _validate_option_case_values(
                    option_name,
                    option,
                    option_value,
                    location=f"preset {preset.name}.task {task.name}",
                )


def _build_common_option_names(interface_model: MaaFWInterface) -> list[str]:
    option_names: list[str] = []
    option_names.extend(interface_model.global_option or [])
    for resource in interface_model.resource:
        option_names.extend(resource.option or [])
    for controller in interface_model.controller:
        option_names.extend(controller.option or [])
    return option_names


def rescan_scan_select_option(
    interface_model: MaaFWInterface,
    option_name: str,
    base_dir: str | Path,
) -> list[dict[str, str]]:
    option = interface_model.option.get(option_name)
    if option is None:
        raise MaaFWInterfaceLoadError(f"scan_select 选项不存在: {option_name}")
    if option.type != "scan_select":
        raise MaaFWInterfaceLoadError(f"选项不是 scan_select 类型: {option_name}")

    resolved_base_dir = Path(base_dir).resolve()
    option_data = option.model_dump(mode="json", exclude_none=True)
    option_data["cases"] = []
    scanned_cases = _scan_scan_select_cases(option_name, option_data, resolved_base_dir)
    option.cases = [MaaFWOptionCase.model_validate(item) for item in scanned_cases]
    return scanned_cases


def _load_interface_model_with_context(base_dir: str | Path) -> tuple[MaaFWInterface, _LoadContext]:
    resolved_base_dir = Path(base_dir).resolve()
    if not resolved_base_dir.exists() or not resolved_base_dir.is_dir():
        raise MaaFWInterfaceLoadError("请设置 MaaFW 项目目录")

    context = _LoadContext()
    root_path = _resolve_interface_path(resolved_base_dir)
    root_data = _read_json_dict(root_path, context)
    merged_data = copy.deepcopy(root_data)
    merge_state = _MergeState()

    _seed_root_sections(merged_data, root_path, merge_state)
    root_imports = _normalize_import_list(merged_data.get("import"), root_path)
    _merge_imports_into_target(
        merged_data,
        root_imports,
        resolved_base_dir,
        merge_state,
        [root_path],
        context,
    )
    _expand_scan_select_options(merged_data, resolved_base_dir, context)

    try:
        interface_model = MaaFWInterface.model_validate(merged_data)
    except Exception as exc:
        raise MaaFWInterfaceLoadError(f"校验 interface 配置失败: {exc}") from exc

    _validate_task_context_constraints(interface_model)
    _validate_option_references(interface_model)
    _validate_presets(interface_model)
    return interface_model, context


def load_interface_model(base_dir: str | Path) -> MaaFWInterface:
    interface_model, _ = _load_interface_model_with_context(base_dir)
    return interface_model


def load_interface_model_cached(
    base_dir: str | Path,
    *,
    force_reload: bool = False,
) -> MaaFWInterface:
    """Load MaaFW ProjectInterface with memory and disk cache."""
    resolved_base_dir = Path(base_dir).resolve()
    with _cache_lock:
        cache_path = _disk_cache_path(resolved_base_dir)
        _cleanup_expired_disk_cache(cache_path)

        cached = _interface_cache.get(resolved_base_dir)
        if cached and not force_reload:
            signature, interface_model, dependency_paths, scan_select_specs = cached
            current_signature = _build_signature(
                resolved_base_dir,
                dependency_paths,
                scan_select_specs,
            )
            if current_signature == signature:
                _touch_disk_cache(cache_path)
                logger.debug(f"复用 MaaFW interface 缓存：{resolved_base_dir}")
                return interface_model.model_copy(deep=False)
            logger.info(f"MaaFW interface 缓存已失效，重新加载：{resolved_base_dir}")

        if not force_reload:
            disk_cached = _load_from_disk_cache(resolved_base_dir)
            if disk_cached is not None:
                signature, interface_model, dependency_paths, scan_select_specs = disk_cached
                _interface_cache[resolved_base_dir] = (
                    signature,
                    interface_model,
                    dependency_paths,
                    scan_select_specs,
                )
                return interface_model.model_copy(deep=False)

        interface_model, context = _load_interface_model_with_context(resolved_base_dir)
        signature = _build_signature(
            resolved_base_dir,
            context.dependency_paths,
            context.scan_select_specs,
        )
        _interface_cache[resolved_base_dir] = (
            signature,
            interface_model,
            context.dependency_paths,
            context.scan_select_specs,
        )
        _save_disk_cache(
            resolved_base_dir,
            signature,
            interface_model,
            context.dependency_paths,
            context.scan_select_specs,
        )
        return interface_model.model_copy(deep=False)


def _disk_cache_dir() -> Path:
    return Path.cwd() / "data/cache/maafw_interface_loader"


def _disk_cache_path(root_path: Path) -> Path:
    cache_key = hashlib.sha256(str(root_path).casefold().encode("utf-8")).hexdigest()
    return _disk_cache_dir() / f"{cache_key}.json"


def _cleanup_expired_disk_cache(protected_cache_path: Path) -> None:
    global _last_disk_cache_cleanup_at
    now = time.time()
    if now - _last_disk_cache_cleanup_at < DISK_CACHE_CLEANUP_INTERVAL_SECONDS:
        return

    _last_disk_cache_cleanup_at = now
    cache_dir = _disk_cache_dir()
    if not cache_dir.is_dir():
        return

    cutoff = now - DISK_CACHE_MAX_AGE_SECONDS
    protected_cache_path = protected_cache_path.resolve()
    for cache_file in cache_dir.glob("*.json"):
        try:
            if cache_file.resolve() == protected_cache_path:
                continue
            if cache_file.stat().st_mtime < cutoff:
                cache_file.unlink()
                logger.info(f"已清理过期 MaaFW interface 缓存：{cache_file}")
        except Exception as exc:
            logger.warning(f"清理 MaaFW interface 缓存失败：{cache_file}，{exc}")


def _touch_disk_cache(cache_path: Path) -> None:
    try:
        if cache_path.is_file():
            cache_path.touch()
    except Exception as exc:
        logger.debug(f"更新 MaaFW interface 缓存使用时间失败：{exc}")


def _file_signature(path: Path) -> tuple:
    try:
        stat = path.stat()
    except OSError:
        return ("missing", str(path), 0, 0)
    return ("file", str(path), stat.st_mtime_ns, stat.st_size)


def _interface_candidates(root_path: Path) -> list[Path]:
    return [(root_path / file_name).resolve() for file_name in ("interface.json", "interface.jsonc")]


def _build_signature(
    root_path: Path,
    dependency_paths: set[Path],
    scan_select_specs: set[tuple[Path, str]],
) -> tuple:
    signature_parts = []
    candidate_paths = {path.resolve() for path in _interface_candidates(root_path)}

    for path in _interface_candidates(root_path):
        signature_parts.append(_file_signature(path))

    for path in sorted(dependency_paths, key=lambda item: str(item)):
        if path.resolve() not in candidate_paths:
            signature_parts.append(_file_signature(path))

    for scan_path, scan_filter in sorted(scan_select_specs, key=lambda item: (str(item[0]), item[1])):
        signature_parts.append(("scan", str(scan_path), scan_filter))
        signature_parts.append(_file_signature(scan_path))
        try:
            scan_files = sorted(scan_path.glob(scan_filter))
        except Exception as exc:
            signature_parts.append(("scan-error", str(scan_path), scan_filter, type(exc).__name__, str(exc)))
            continue

        for file in scan_files:
            if file.is_file():
                signature_parts.append(_file_signature(file.resolve()))

    return tuple(signature_parts)


def _signature_to_json(signature: tuple) -> list[list]:
    return [list(part) for part in signature]


def _is_valid_disk_cache_payload(payload: dict[str, Any]) -> bool:
    return (
        isinstance(payload.get("interface"), dict)
        and isinstance(payload.get("dependency_paths"), list)
        and isinstance(payload.get("scan_select_specs"), list)
        and isinstance(payload.get("signature"), list)
    )


def _load_from_disk_cache(
    root_path: Path,
) -> tuple[tuple, MaaFWInterface, set[Path], set[tuple[Path, str]]] | None:
    cache_path = _disk_cache_path(root_path)
    if not cache_path.is_file():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        if payload.get("version") != DISK_CACHE_VERSION:
            return None
        cached_root = payload.get("root_path")
        if not isinstance(cached_root, str) or Path(cached_root).resolve() != root_path.resolve():
            logger.info(f"MaaFW interface 缓存路径不匹配，重新加载：{root_path}")
            return None
        if not _is_valid_disk_cache_payload(payload):
            logger.info(f"MaaFW interface 缓存结构已过期：{root_path}")
            return None

        dependency_paths = {
            Path(path)
            for path in payload.get("dependency_paths", [])
            if isinstance(path, str)
        }
        scan_select_specs = {
            (Path(item[0]), item[1])
            for item in payload.get("scan_select_specs", [])
            if isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        }
        current_signature = _build_signature(
            root_path,
            dependency_paths,
            scan_select_specs,
        )
        if payload.get("signature") != _signature_to_json(current_signature):
            logger.info(f"MaaFW interface 缓存已失效：{root_path}")
            return None

        interface_model = MaaFWInterface.model_validate(payload["interface"])
        _touch_disk_cache(cache_path)
        logger.info(f"读取 MaaFW interface 缓存：{root_path}")
        return current_signature, interface_model, dependency_paths, scan_select_specs
    except Exception as exc:
        logger.warning(f"读取 MaaFW interface 缓存失败，回退实时解析：{exc}")
        return None


def _save_disk_cache(
    root_path: Path,
    signature: tuple,
    interface_model: MaaFWInterface,
    dependency_paths: set[Path],
    scan_select_specs: set[tuple[Path, str]],
) -> None:
    cache_path = _disk_cache_path(root_path)
    payload = {
        "version": DISK_CACHE_VERSION,
        "root_path": str(root_path),
        "dependency_paths": [
            str(path) for path in sorted(dependency_paths, key=lambda item: str(item))
        ],
        "scan_select_specs": [
            [str(path), scan_filter]
            for path, scan_filter in sorted(scan_select_specs, key=lambda item: (str(item[0]), item[1]))
        ],
        "signature": _signature_to_json(signature),
        "interface": interface_model.model_dump(mode="json", by_alias=True),
    }

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = cache_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(cache_path)
        logger.debug(f"已写入 MaaFW interface 缓存：{cache_path}")
    except Exception as exc:
        logger.warning(f"写入 MaaFW interface 缓存失败：{exc}")
