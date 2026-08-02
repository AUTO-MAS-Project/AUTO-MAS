#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import json
import os
import re
import uuid
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .report import OkScriptReportHandler


_VERSION_SUFFIX_RE = re.compile(r"[-_ ]?v?\d+(?:\.\d+)+(?:[-_.a-z0-9]*)?$", re.I)
_PYAPPIFY_NAME_RE = re.compile(r"^\s*name\s*:\s*[\"']?([^\"'\r\n#]+)[\"']?", re.M)
_GAME_SEARCH_MAX_DEPTH = 10
_GAME_SEARCH_MAX_ENTRIES = 20_000
_GAME_SEARCH_PARENT_LEVELS = 8

GameLaunchMode = Literal[
    "direct",
    "launcher",
    "script-managed",
    "attach",
    "uri",
]
GameLaunchKind = Literal["executable", "uri", "none"]
GamePathRole = Literal["launch", "ready", "cleanup"]
GameAlreadyRunningPolicy = Literal["attach", "restart", "error"]
GameCleanupPolicy = Literal[
    "always",
    "success-and-failure",
    "manual-stop",
    "never",
]


@dataclass(frozen=True, slots=True)
class GamePathCandidate:
    """一个游戏程序路径候选及其在启动生命周期中的角色。"""

    relative_path: str
    role: GamePathRole
    source: str = "provider"
    confidence: str = "declared"

    @property
    def executable_name(self) -> str:
        return Path(self.relative_path).name

    def to_dict(self) -> dict[str, str]:
        return {
            "relativePath": self.relative_path,
            "role": self.role,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class GameLaunchDescriptor:
    """provider 声明的游戏启动、就绪和清理策略。"""

    mode: GameLaunchMode = "direct"
    launch_kind: GameLaunchKind = "executable"
    launch_uri: str = ""
    path_candidates: tuple[GamePathCandidate, ...] = ()
    ready_process_name: str = ""
    already_running_policy: GameAlreadyRunningPolicy = "attach"
    cleanup_policy: GameCleanupPolicy = "always"
    verification: str = "verified"

    def effective_mode(
        self,
        *,
        game_enabled: bool,
        launch_before_task: bool,
    ) -> GameLaunchMode:
        """根据历史 Game 开关返回本次运行实际采用的启动模式。"""

        if self.mode == "script-managed":
            return self.mode
        if not game_enabled or not launch_before_task:
            return "script-managed"
        return self.mode

    def with_effective_mode(
        self,
        *,
        game_enabled: bool,
        launch_before_task: bool,
    ) -> "GameLaunchDescriptor":
        """复制 descriptor，保留路径和清理策略并替换本轮启动模式。"""

        return replace(
            self,
            mode=self.effective_mode(
                game_enabled=game_enabled,
                launch_before_task=launch_before_task,
            ),
        )

    def candidates_for(self, role: GamePathRole) -> tuple[GamePathCandidate, ...]:
        return tuple(candidate for candidate in self.path_candidates if candidate.role == role)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "launchTarget": {
                "kind": self.launch_kind,
                "uri": self.launch_uri or None,
                "candidates": [
                    candidate.to_dict() for candidate in self.candidates_for("launch")
                ],
            },
            "readyTarget": {
                "processName": self.ready_process_name or None,
                "candidates": [
                    candidate.to_dict() for candidate in self.candidates_for("ready")
                ],
            },
            "cleanupTargets": [
                candidate.to_dict() for candidate in self.candidates_for("cleanup")
            ],
            "alreadyRunningPolicy": self.already_running_policy,
            "cleanupPolicy": self.cleanup_policy,
            "verification": self.verification,
        }


@dataclass(frozen=True, slots=True)
class ResolvedGamePathCandidate:
    """一个已落到本机文件系统的角色化游戏程序候选。"""

    path: Path
    role: GamePathRole
    source: str
    confidence: str
    matched_by: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path.as_posix(),
            "role": self.role,
            "source": self.source,
            "confidence": self.confidence,
            "matchedBy": self.matched_by,
        }


@dataclass(frozen=True, slots=True)
class GamePathResolution:
    """游戏路径检测结果，保留启动、就绪和清理的独立角色。"""

    selected_input: str
    descriptor: GameLaunchDescriptor
    launch_path: Path | None
    ready_path: Path | None
    cleanup_paths: tuple[Path, ...]
    candidates: tuple[ResolvedGamePathCandidate, ...]
    diagnostics: tuple[str, ...] = ()
    ambiguous: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "selectedInput": self.selected_input,
            "launchTarget": {
                "kind": self.descriptor.launch_kind,
                "path": self.launch_path.as_posix() if self.launch_path else None,
                "uri": self.descriptor.launch_uri or None,
            },
            "readyTarget": {
                "processName": self.descriptor.ready_process_name or None,
                "path": self.ready_path.as_posix() if self.ready_path else None,
            },
            "cleanupTargets": [path.as_posix() for path in self.cleanup_paths],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "diagnostics": list(self.diagnostics),
            "ambiguous": self.ambiguous,
        }


@dataclass(frozen=True)
class OkScriptTaskOption:
    """ok-script 一次性任务元数据。"""

    index: int
    label: str


@dataclass(frozen=True)
class OkScriptAccountConfig:
    """脚本本体中可由 MAS 注入的多账号字段。"""

    enabled_key: str
    independent_key: str
    account_list_key: str


@dataclass(frozen=True)
class OkScriptRuntimeConfigOverride:
    """仅在 MAS 托管运行期间生效的项目配置覆盖。"""

    file_name: str
    key: str
    value: Any


@dataclass(frozen=True)
class OkScriptProvider:
    """ok-script 项目差异描述。

    这里只放可由具体项目决定的路径、进程和日志判态，不承载 MAS 的运行流程。
    """

    resource_name: str
    display_name: str
    exe_name: str
    config_dir: str
    log_file: str
    pythonw_path: str
    track_process_name: str
    game_process_name: str
    running_status: str
    fatal_patterns: tuple[tuple[str, str], ...]
    success_patterns: tuple[str, ...]
    max_task_index: int
    task_options: tuple[OkScriptTaskOption, ...]
    config_schema_module: str
    config_info_loader: str
    game_path_candidates: tuple[str, ...] = ()
    config_info_uses_directory: bool = False
    account_config: OkScriptAccountConfig | None = None
    report_handler_factory: Callable[[], "OkScriptReportHandler"] | None = None
    runtime_config_overrides: tuple[OkScriptRuntimeConfigOverride, ...] = ()
    runtime_verified: bool = True
    runtime_block_reason: str = ""
    log_time_start: int = 1
    log_time_end: int = 23
    log_time_format: str = "%Y-%m-%d %H:%M:%S,%f"
    event_log_name: str = "mas-events.jsonl"
    game_launch: GameLaunchDescriptor | None = None

    @property
    def log_time_range(self) -> tuple[int, int]:
        return (self.log_time_start - 1, self.log_time_end)

    @property
    def game_launch_descriptor(self) -> GameLaunchDescriptor:
        """返回 provider 声明或历史字段推导的游戏启动策略。"""

        if self.game_launch is not None:
            return self.game_launch
        return _legacy_game_launch_descriptor(self)

    @property
    def app_json_file(self) -> str:
        return f"data/apps/{self.resource_name}/app.json"

    def app_json_path(self, root_path: Path) -> Path:
        return root_path / self.app_json_file

    def exe_path(self, root_path: Path) -> Path:
        return root_path / self.exe_name

    def config_path(self, root_path: Path) -> Path:
        return root_path / self.config_dir

    def log_path(self, root_path: Path) -> Path:
        return root_path / self.log_file

    def event_log_path(self, root_path: Path) -> Path:
        """返回 MAS 接管 ok-script 结构化运行事件的固定 JSONL 路径。"""

        return self.log_path(root_path).with_name(self.event_log_name)

    def track_process_path(self, root_path: Path) -> Path:
        return root_path / self.pythonw_path

    def build_task_args(self, task_index: int) -> list[str]:
        return ["-t", str(task_index), "-e"]

    def is_supported_task_index(self, task_index: int) -> bool:
        """判断任务序号是否属于当前脚本项目。"""

        return any(option.index == task_index for option in self.task_options)

    def task_label(self, task_index: int) -> str:
        """返回任务序号对应的项目内名称。"""

        for option in self.task_options:
            if option.index == task_index:
                return option.label
        return f"任务 {task_index}"

    def build_client_metadata(self) -> dict[str, Any]:
        """构建供 ok-script 前端消费的项目隔离元数据。"""

        account_fields = None
        if self.account_config is not None:
            account_fields = {
                "enabledKey": self.account_config.enabled_key,
                "independentKey": self.account_config.independent_key,
                "accountListKey": self.account_config.account_list_key,
            }

        return {
            "resourceName": self.resource_name,
            "displayName": self.display_name,
            "taskOptions": [
                {"value": option.index, "label": option.label}
                for option in self.task_options
            ],
            "accountFields": account_fields,
            "runtimeVerified": self.runtime_verified,
            "runtimeBlockReason": self.runtime_block_reason,
            "gameProcessName": self.game_process_name,
            "gameLaunch": self.game_launch_descriptor.to_dict(),
        }


def _legacy_game_launch_descriptor(
    provider: OkScriptProvider,
) -> GameLaunchDescriptor:
    """将历史单一路径字段兼容映射为 direct 启动策略。"""

    relative_paths: list[str] = []
    for raw_path in (provider.game_process_name, *provider.game_path_candidates):
        relative_path = str(raw_path).strip()
        if relative_path and relative_path not in relative_paths:
            relative_paths.append(relative_path)

    if not relative_paths:
        return GameLaunchDescriptor(
            mode="script-managed",
            launch_kind="none",
            cleanup_policy="never",
            verification="unverified",
        )

    candidates = tuple(
        GamePathCandidate(relative_path=relative_path, role=role)
        for role in ("launch", "ready", "cleanup")
        for relative_path in relative_paths
    )
    return GameLaunchDescriptor(
        mode="direct",
        launch_kind="executable",
        path_candidates=candidates,
        ready_process_name=provider.game_process_name,
        verification=("verified" if provider.runtime_verified else "unverified"),
    )


def _matching_game_executable(path: Path, executable_name: str) -> Path | None:
    try:
        if path.is_file() and path.name.casefold() == executable_name.casefold():
            return path.resolve()
    except OSError:
        return None
    return None


def _game_search_bases(path: Path) -> list[Path]:
    start = path if path.is_dir() else path.parent
    bases: list[Path] = []
    current = start
    for _ in range(_GAME_SEARCH_PARENT_LEVELS + 1):
        if current in bases:
            break
        bases.append(current)
        if current.parent == current:
            break
        current = current.parent
    return bases


def _append_resolved_candidate(
    matches: list[ResolvedGamePathCandidate],
    seen: set[tuple[GamePathRole, Path]],
    candidate: GamePathCandidate,
    path: Path,
    *,
    matched_by: str,
) -> None:
    key = (candidate.role, path)
    if key in seen:
        return
    seen.add(key)
    matches.append(
        ResolvedGamePathCandidate(
            path=path,
            role=candidate.role,
            source=candidate.source,
            confidence=candidate.confidence,
            matched_by=matched_by,
        )
    )


def _safe_candidate_path(base: Path, candidate: GamePathCandidate) -> Path | None:
    relative_path = Path(candidate.relative_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    return _matching_game_executable(
        base / relative_path,
        candidate.executable_name,
    )


def _search_game_executables(
    root: Path,
    candidates: tuple[GamePathCandidate, ...],
) -> list[tuple[GamePathCandidate, Path]]:
    candidate_names: dict[str, list[GamePathCandidate]] = {}
    for candidate in candidates:
        executable_name = candidate.executable_name.strip()
        if executable_name:
            candidate_names.setdefault(executable_name.casefold(), []).append(candidate)

    if not candidate_names:
        return []

    queue: deque[tuple[Path, int]] = deque([(root, 0)])
    scanned_entries = 0
    matches: list[tuple[GamePathCandidate, Path]] = []

    while queue and scanned_entries < _GAME_SEARCH_MAX_ENTRIES:
        current, depth = queue.popleft()
        try:
            entries = os.scandir(current)
        except OSError:
            continue

        with entries:
            for entry in entries:
                scanned_entries += 1
                if scanned_entries > _GAME_SEARCH_MAX_ENTRIES:
                    break
                try:
                    if entry.is_file(follow_symlinks=False):
                        matching_candidates = candidate_names.get(entry.name.casefold())
                        if matching_candidates:
                            resolved_path = Path(entry.path).resolve()
                            matches.extend(
                                (candidate, resolved_path)
                                for candidate in matching_candidates
                            )
                    elif depth < _GAME_SEARCH_MAX_DEPTH and entry.is_dir(
                        follow_symlinks=False
                    ):
                        queue.append((Path(entry.path), depth + 1))
                except OSError:
                    continue
    return matches


def _role_paths(
    matches: tuple[ResolvedGamePathCandidate, ...],
    role: GamePathRole,
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for match in matches:
        if match.role == role and match.path not in paths:
            paths.append(match.path)
    return tuple(paths)


def resolve_game_path(
    provider: OkScriptProvider,
    selected_path: str | Path,
    *,
    descriptor: GameLaunchDescriptor | None = None,
) -> GamePathResolution:
    """按角色解析游戏的启动、就绪和清理目标，不启动任何进程。"""

    launch_descriptor = descriptor or provider.game_launch_descriptor
    raw_selected_path = str(selected_path).strip()
    diagnostics: list[str] = []
    matches: list[ResolvedGamePathCandidate] = []
    seen: set[tuple[GamePathRole, Path]] = set()

    if not raw_selected_path:
        if launch_descriptor.path_candidates:
            diagnostics.append("未选择游戏目录或游戏程序")
        return GamePathResolution(
            selected_input="",
            descriptor=launch_descriptor,
            launch_path=None,
            ready_path=None,
            cleanup_paths=(),
            candidates=(),
            diagnostics=tuple(diagnostics),
        )

    selected = Path(raw_selected_path).expanduser()
    try:
        if not selected.exists():
            diagnostics.append("所选游戏目录或程序不存在")
            return GamePathResolution(
                selected_input=raw_selected_path,
                descriptor=launch_descriptor,
                launch_path=None,
                ready_path=None,
                cleanup_paths=(),
                candidates=(),
                diagnostics=tuple(diagnostics),
            )
    except OSError:
        diagnostics.append("无法读取所选游戏目录或程序")
        return GamePathResolution(
            selected_input=raw_selected_path,
            descriptor=launch_descriptor,
            launch_path=None,
            ready_path=None,
            cleanup_paths=(),
            candidates=(),
            diagnostics=tuple(diagnostics),
        )

    candidates = tuple(
        candidate
        for candidate in launch_descriptor.path_candidates
        if candidate.executable_name.strip()
    )
    if not candidates:
        return GamePathResolution(
            selected_input=raw_selected_path,
            descriptor=launch_descriptor,
            launch_path=None,
            ready_path=None,
            cleanup_paths=(),
            candidates=(),
            diagnostics=("当前项目未声明可检测的游戏程序路径",),
        )

    explicit_roles: set[GamePathRole] = set()
    if selected.is_file():
        for candidate in candidates:
            direct_match = _matching_game_executable(
                selected,
                candidate.executable_name,
            )
            if direct_match is None:
                continue
            explicit_roles.add(candidate.role)
            _append_resolved_candidate(
                matches,
                seen,
                candidate,
                direct_match,
                matched_by="selected-file",
            )

    candidates_to_search = tuple(
        candidate for candidate in candidates if candidate.role not in explicit_roles
    )
    for base in _game_search_bases(selected):
        for candidate in candidates_to_search:
            matched_path = _safe_candidate_path(base, candidate)
            if matched_path is None:
                continue
            _append_resolved_candidate(
                matches,
                seen,
                candidate,
                matched_path,
                matched_by="declared-relative-path",
            )

    search_root = selected if selected.is_dir() else selected.parent
    for candidate, matched_path in _search_game_executables(
        search_root,
        candidates_to_search,
    ):
        _append_resolved_candidate(
            matches,
            seen,
            candidate,
            matched_path,
            matched_by="bounded-search",
        )

    resolved_matches = tuple(matches)
    launch_paths = _role_paths(resolved_matches, "launch")
    ready_paths = _role_paths(resolved_matches, "ready")
    cleanup_paths = _role_paths(resolved_matches, "cleanup")
    ambiguous_roles = [
        role
        for role, paths in (("launch", launch_paths), ("ready", ready_paths))
        if len(paths) > 1
    ]
    if ambiguous_roles:
        diagnostics.append(
            "检测到多个 " + "、".join(ambiguous_roles) + " 目标，请选择具体程序文件"
        )
    if (
        launch_descriptor.launch_kind == "executable"
        and launch_descriptor.mode in ("direct", "launcher")
        and not launch_paths
    ):
        diagnostics.append("未找到游戏启动程序")
    if launch_descriptor.candidates_for("ready") and not ready_paths:
        diagnostics.append("未找到游戏就绪目标")
    if launch_descriptor.candidates_for("cleanup") and not cleanup_paths:
        diagnostics.append("未找到游戏清理目标")

    return GamePathResolution(
        selected_input=raw_selected_path,
        descriptor=launch_descriptor,
        launch_path=launch_paths[0] if len(launch_paths) == 1 else None,
        ready_path=ready_paths[0] if len(ready_paths) == 1 else None,
        cleanup_paths=cleanup_paths,
        candidates=resolved_matches,
        diagnostics=tuple(diagnostics),
        ambiguous=bool(ambiguous_roles),
    )


def resolve_game_executable_path(
    provider: OkScriptProvider,
    selected_path: str | Path,
) -> Path | None:
    """兼容旧调用方，返回角色化解析中唯一的启动程序路径。"""

    resolution = resolve_game_path(provider, selected_path)
    return None if resolution.ambiguous else resolution.launch_path


def normalize_ok_script_resource_name(value: Any) -> str:
    """把 pyappify/app.json 中的资源名规整为 provider 可匹配的 key。"""

    text = str(value or "").strip().strip("\"'")
    if not text:
        return ""
    normalized = _VERSION_SUFFIX_RE.sub("", text).strip()
    return normalized or text


def read_pyappify_resource_name(root_path: Path) -> str:
    pyappify_path = root_path / "pyappify.yml"
    if not pyappify_path.is_file():
        return ""

    try:
        content = pyappify_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""

    match = _PYAPPIFY_NAME_RE.search(content)
    return normalize_ok_script_resource_name(match.group(1) if match else "")


def read_app_json_resource_name(app_json_path: Path) -> str:
    if not app_json_path.is_file():
        return ""

    try:
        data = json.loads(app_json_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ""

    if not isinstance(data, dict):
        return ""
    return normalize_ok_script_resource_name(data.get("name"))


def ok_script_mas_config_dir(
    script_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
) -> Path:
    """返回 MAS 侧保存的 ok-script 用户配置目录。"""

    try:
        script_uid = uuid.UUID(str(script_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("script_id 不是有效 UUID") from exc
    try:
        user_uid = uuid.UUID(str(user_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("user_id 不是有效 UUID") from exc

    data_root = (Path.cwd() / "data").resolve()
    target = (
        data_root / str(script_uid) / str(user_uid) / "ConfigFile"
    ).resolve()
    try:
        target.relative_to(data_root)
    except ValueError as exc:
        raise ValueError("非法 ok-script 用户配置目录") from exc
    return target
