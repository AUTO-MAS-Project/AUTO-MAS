import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TASK_EVENT_TEXT = {
    "Tasker.Task.Starting": "任务开始",
    "Tasker.Task.Succeeded": "任务完成",
    "Tasker.Task.Failed": "任务失败",
}

RESOURCE_EVENT_TEXT = {
    "Resource.Loading.Starting": "正在加载资源",
    "Resource.Loading.Succeeded": "资源加载成功",
    "Resource.Loading.Failed": "资源加载失败",
}

CONTROLLER_EVENT_TEXT = {
    "Controller.Action.Starting": "正在连接窗口",
    "Controller.Action.Succeeded": "窗口连接成功",
    "Controller.Action.Failed": "窗口连接失败",
}

FULL_TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")
ISO_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})"
)
PANEL_TS_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*$")
NEXT_FULL_TS_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\]")
NEXT_PANEL_TS_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s*$")
AGENT_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})\s+([A-Z]+)\s+(.+)$"
)
THREAD_ID_RE = re.compile(r"\[Tx(\d+)\]")
SIMPLE_JSON_RE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]\s+(\{.+\})\s*$"
)
EVENT_RE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]"
    r"\[[A-Z]+\]"
    r"\[Px\d+\]"
    r"\[Tx\d+\]"
    r"\[Utils/EventDispatcher\.hpp\]"
    r"\[L\d+\]"
    r"\[[^\]]+\]\s*(?:!!!OnEventNotify!!!\s*)?"
    r"\[handle=[^\]]+\]\s+\[msg=([^\]]+)\]\s+\[details=(.+)\]\s*$"
)
WRAPPED_AGENT_RE = re.compile(
    r'^\s*\{.*?"instance_id"\s*:\s*"([^"]+)".*?"line"\s*:\s*"((?:\\.|[^"])*)".*\}\s*$'
)
INLINE_INSTANCE_RE = re.compile(
    r'(?:"instance_id"\s*:\s*"|instance_id\s*[:=]\s*)([A-Za-z0-9._-]+)'
)
TAURI_TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\]\[(\d{2}:\d{2}:\d{2})\]")
TAURI_INSTANCE_RE = re.compile(
    r"(?:instance_id|instance)\s*:\s*([A-Za-z0-9._-]+)|Instance found:\s*([A-Za-z0-9._-]+)"
)
TAURI_START_TASKS_RE = re.compile(r"\bmaa_start_tasks called\b")
TAURI_TASK_ENTRY_RE = re.compile(r'TaskConfig\s*\{\s*entry:\s*"([^"]+)"')
TAURI_POST_TASK_ID_RE = re.compile(r"post_task returned task_id:\s*([A-Za-z0-9._-]+)")
TEXT_TASK_ID_RE = re.compile(r"\btask_id\b\s*[:=]\s*\"?([A-Za-z0-9._-]+)\"?")
TEXT_TASK_ID_ALT_RE = re.compile(r"\btask_id_\b\s*[:=]\s*\"?([A-Za-z0-9._-]+)\"?")

ENTRY_TASK_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "VisitFriendsMain": ("VisitFriends",),
    "CreditShoppingMain": ("CreditShoppingN2", "CreditShopping"),
    "DeliveryJobsMain": ("DeliveryJobs",),
    "SellProductMain": ("SellProduct",),
    "DailyRewardStart": ("DailyRewards", "DailyReward"),
    "SeizeEntrustTaskMain": ("SeizeEntrustTask",),
    "ProtocolSpaceEntry": ("ProtocolSpace",),
    "MXU_KILLPROC": ("__MXU_KILLPROC__",),
}


@dataclass(frozen=True)
class SnapshotTask:
    """配置快照中的单个前端任务。"""

    id: str
    task_name: str
    enabled: bool


@dataclass(frozen=True)
class Snapshot:
    """一份可用于还原 selected_task_id 的任务快照。"""

    instance_id: str
    source: str
    closed_at: int | None
    tasks: tuple[SnapshotTask, ...]


@dataclass(frozen=True)
class BatchTask:
    """MXU 一次 start_tasks 批次中的单个运行时任务。"""

    task_index: int
    entry: str
    task_id: str | None
    posted_at: datetime | None


@dataclass(frozen=True)
class Batch:
    """来自 mxu-tauri.log 的一次权威任务批次。"""

    batch_id: int
    instance_id: str
    started_at: datetime | None
    tasks: tuple[BatchTask, ...]


@dataclass(frozen=True)
class AuxiliaryData:
    """固定文件解析得到的辅助上下文。"""

    snapshots: tuple[Snapshot, ...]
    batches: tuple[Batch, ...]
    task_id_to_entry: dict[str, str]


@dataclass(frozen=True)
class RunContext:
    """当前这一轮输入日志中能观察到的运行信息。"""

    first_timestamp: datetime | None
    last_timestamp: datetime | None
    task_ids: frozenset[str]
    entries: frozenset[str]


@dataclass(frozen=True)
class RuntimeTaskStart:
    """运行时顶层 Tasker.Task.Starting 事件。"""

    timestamp: datetime
    entry: str
    task_id: str


_AUX_CACHE_KEY: tuple[tuple[str, int, int], ...] | None = None
_AUX_CACHE_VALUE: AuxiliaryData | None = None


def _safe_load_json_dict(text: str) -> dict[str, Any] | None:
    """安全解析 JSON，仅当结果是对象时返回。"""

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _read_lines(path: Path) -> list[str]:
    """按 UTF-8 读取文本行，失败时返回空列表。"""

    try:
        return path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []


def _decode_wrapped_line(match: re.Match[str]) -> str:
    """还原被 JSON 包裹的一层 agent 日志。"""

    try:
        return json.loads('"' + match.group(2) + '"')
    except json.JSONDecodeError:
        return (
            match.group(2)
            .encode("utf-8", errors="replace")
            .decode("unicode_escape", errors="replace")
        )


def _extract_task_id(details: dict[str, Any], raw_text: str) -> str:
    """优先从结构化字段提取 task_id，失败后回退到正则。"""

    task_id_value = details.get("task_id")
    if isinstance(task_id_value, (int, str)):
        return str(task_id_value).strip()

    task_id_alt_value = details.get("task_id_")
    if isinstance(task_id_alt_value, (int, str)):
        return str(task_id_alt_value).strip()

    task_id_match = TEXT_TASK_ID_RE.search(raw_text)
    if task_id_match:
        return task_id_match.group(1).strip()

    task_id_alt_match = TEXT_TASK_ID_ALT_RE.search(raw_text)
    if task_id_alt_match:
        return task_id_alt_match.group(1).strip()

    return ""


def _extract_entry(details: dict[str, Any], raw_text: str) -> str:
    """提取运行时 entry 名称。"""

    entry_value = details.get("entry")
    if isinstance(entry_value, str):
        return entry_value.strip()

    entry_match = re.search(r'\bentry\b\s*[:=]\s*"([A-Za-z0-9._-]+)"', raw_text)
    if entry_match:
        return entry_match.group(1).strip()

    return ""


def _parse_tauri_timestamp(line: str) -> datetime | None:
    """解析 mxu-tauri.log 的时间戳。"""

    match = TAURI_TS_RE.match(line)
    if match is None:
        return None

    try:
        return datetime.strptime(
            f"{match.group(1)} {match.group(2)}.000", "%Y-%m-%d %H:%M:%S.%f"
        )
    except ValueError:
        return None


def _extract_timestamp(line: str) -> datetime | None:
    """从任意支持的日志格式中抽取完整时间。"""

    full_match = FULL_TS_RE.match(line)
    if full_match is not None:
        try:
            return datetime.strptime(full_match.group(1), "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            return None

    iso_match = ISO_TS_RE.match(line)
    if iso_match is not None:
        try:
            return datetime.strptime(
                f"{iso_match.group(1)} {iso_match.group(2)}.000",
                "%Y-%m-%d %H:%M:%S.%f",
            )
        except ValueError:
            return None

    simple_json_match = SIMPLE_JSON_RE.match(line)
    if simple_json_match is not None:
        try:
            return datetime.strptime(simple_json_match.group(1), "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            return None

    if line.startswith("{") and '"time"' in line:
        data = _safe_load_json_dict(line)
        if data is not None and isinstance(data.get("time"), str):
            return _extract_timestamp(data["time"])

    return None


def _emit_log_line(
    result: list[str],
    timestamp: str,
    log_prefix: str,
    message: str,
    last_emit_key: str,
    last_emit_time: datetime | None,
) -> tuple[str, datetime | None]:
    """写入去重后的日志行，避免极短时间内的重复刷屏。"""

    emit_key = f"{log_prefix}|{message}"
    emit_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
    if (
        emit_key == last_emit_key
        and last_emit_time is not None
        and abs((emit_time - last_emit_time).total_seconds()) <= 0.02
    ):
        return last_emit_key, last_emit_time

    result.append(f"[{timestamp}] {log_prefix} - {message}\n")
    return emit_key, emit_time


def _normalize_name(name: str) -> str:
    """统一名字比较口径，便于 entry 和 taskName 做模糊比对。"""

    return "".join(ch.lower() for ch in name if ch.isalnum())


def _entry_candidates(entry: str) -> tuple[str, ...]:
    """把运行时 entry 扩展成一组可能的前端 taskName。"""

    candidates: list[str] = [entry]

    aliases = ENTRY_TASK_NAME_ALIASES.get(entry)
    if aliases is not None:
        candidates.extend(aliases)

    for suffix in ("Main", "Start", "Sub"):
        if entry.endswith(suffix) and len(entry) > len(suffix):
            candidates.append(entry[: -len(suffix)])

    if entry.endswith("Rewards") and len(entry) > len("Rewards"):
        candidates.append(entry[: -len("Rewards")] + "Reward")
    if entry.endswith("Reward") and len(entry) > len("Reward"):
        candidates.append(entry[: -len("Reward")] + "Rewards")

    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            unique_candidates.append(candidate)
            seen.add(candidate)
    return tuple(unique_candidates)


def _task_name_matches(task_name: str, entry: str) -> bool:
    """判断前端 taskName 和运行时 entry 是否可认为是同一个任务。"""

    normalized_task_name = _normalize_name(task_name)
    return any(
        normalized_task_name == _normalize_name(candidate)
        for candidate in _entry_candidates(entry)
    )


def _build_snapshot_tasks(raw_tasks: Any) -> tuple[SnapshotTask, ...]:
    """从配置文件中抽取快照任务列表。"""

    if not isinstance(raw_tasks, list):
        return ()

    tasks: list[SnapshotTask] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            continue
        task_id = raw_task.get("id")
        task_name = raw_task.get("taskName")
        enabled = raw_task.get("enabled")
        if isinstance(task_id, str) and isinstance(task_name, str):
            tasks.append(
                SnapshotTask(
                    id=task_id,
                    task_name=task_name,
                    enabled=bool(enabled),
                )
            )
    return tuple(tasks)


def _load_snapshots(config_data: dict[str, Any]) -> tuple[Snapshot, ...]:
    """读取当前实例和 recentlyClosed 中的任务快照。"""

    snapshots: list[Snapshot] = []

    raw_instances = config_data.get("instances")
    if isinstance(raw_instances, list):
        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                continue
            instance_id = raw_instance.get("id")
            if not isinstance(instance_id, str):
                continue
            snapshots.append(
                Snapshot(
                    instance_id=instance_id,
                    source="instance",
                    closed_at=None,
                    tasks=_build_snapshot_tasks(raw_instance.get("tasks")),
                )
            )

    raw_recently_closed = config_data.get("recentlyClosed")
    if isinstance(raw_recently_closed, list):
        for raw_snapshot in raw_recently_closed:
            if not isinstance(raw_snapshot, dict):
                continue
            instance_id = raw_snapshot.get("id")
            closed_at = raw_snapshot.get("closedAt")
            if not isinstance(instance_id, str):
                continue
            snapshots.append(
                Snapshot(
                    instance_id=instance_id,
                    source="recently_closed",
                    closed_at=closed_at if isinstance(closed_at, int) else None,
                    tasks=_build_snapshot_tasks(raw_snapshot.get("tasks")),
                )
            )

    return tuple(snapshots)


def _parse_tauri_batches(lines: list[str]) -> tuple[Batch, ...]:
    """从 mxu-tauri.log 构造权威批次列表。"""

    batches: list[Batch] = []
    current_instance_id = ""
    current_batch_id = 0
    open_started_at: datetime | None = None
    open_instance_id = ""
    open_entries: list[str] = []
    open_task_ids: list[str] = []
    open_posted_ats: list[datetime | None] = []

    def flush_batch() -> None:
        if not open_entries and not open_task_ids:
            return

        tasks: list[BatchTask] = []
        max_length = max(len(open_entries), len(open_task_ids))
        for index in range(max_length):
            entry = open_entries[index] if index < len(open_entries) else ""
            task_id = open_task_ids[index] if index < len(open_task_ids) else None
            posted_at = open_posted_ats[index] if index < len(open_posted_ats) else None
            tasks.append(
                BatchTask(
                    task_index=index,
                    entry=entry,
                    task_id=task_id,
                    posted_at=posted_at,
                )
            )

        batches.append(
            Batch(
                batch_id=current_batch_id,
                instance_id=open_instance_id or current_instance_id,
                started_at=open_started_at,
                tasks=tuple(tasks),
            )
        )

    for line in lines:
        line_timestamp = _parse_tauri_timestamp(line)

        instance_match = TAURI_INSTANCE_RE.search(line)
        if instance_match is not None:
            current_instance_id = (
                instance_match.group(1) or instance_match.group(2) or ""
            ).strip()
            if not open_instance_id:
                open_instance_id = current_instance_id

        if TAURI_START_TASKS_RE.search(line):
            flush_batch()
            current_batch_id += 1
            open_started_at = line_timestamp
            open_instance_id = current_instance_id
            open_entries = []
            open_task_ids = []
            open_posted_ats = []
            continue

        if current_batch_id == 0:
            if "tasks:" not in line:
                continue

        if "tasks:" in line:
            if current_batch_id == 0:
                current_batch_id += 1
                open_started_at = line_timestamp
                open_instance_id = current_instance_id
                open_entries = []
                open_task_ids = []
                open_posted_ats = []
            open_entries = TAURI_TASK_ENTRY_RE.findall(line)
            if not open_instance_id:
                open_instance_id = current_instance_id
            continue

        post_task_match = TAURI_POST_TASK_ID_RE.search(line)
        if post_task_match is not None:
            open_task_ids.append(post_task_match.group(1).strip())
            open_posted_ats.append(line_timestamp)

    flush_batch()
    return tuple(batches)


def _load_go_service_mapping(lines: list[str]) -> dict[str, str]:
    """从 go-service.log 中补充 task_id -> entry 显式映射。"""

    mapping: dict[str, str] = {}
    for line in lines:
        data = _safe_load_json_dict(line)
        if data is None:
            continue
        task_id_value = data.get("task_id")
        entry_value = data.get("entry")
        if isinstance(task_id_value, (int, str)) and isinstance(entry_value, str):
            mapping[str(task_id_value).strip()] = entry_value.strip()
    return mapping


def _build_auxiliary_data(root_dir: Path) -> AuxiliaryData:
    """读取固定文件，并缓存批次/快照等不会频繁变化的上下文。"""

    global _AUX_CACHE_KEY, _AUX_CACHE_VALUE

    config_path = root_dir / "config" / "mxu-MaaEnd.json"
    tauri_path = root_dir / "debug" / "mxu-tauri.log"
    go_service_path = root_dir / "debug" / "go-service.log"

    cache_key_parts: list[tuple[str, int, int]] = []
    for path in (config_path, tauri_path, go_service_path):
        if path.is_file():
            stat = path.stat()
            cache_key_parts.append(
                (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
            )
        else:
            cache_key_parts.append((str(path.resolve()), -1, -1))
    cache_key = tuple(cache_key_parts)

    if _AUX_CACHE_KEY == cache_key and _AUX_CACHE_VALUE is not None:
        return _AUX_CACHE_VALUE

    config_data: dict[str, Any] | None = None
    if config_path.is_file():
        try:
            config_data = _safe_load_json_dict(config_path.read_text(encoding="utf-8"))
        except Exception:
            config_data = None
    if config_data is None:
        config_data = {}

    auxiliary_data = AuxiliaryData(
        snapshots=_load_snapshots(config_data),
        batches=_parse_tauri_batches(_read_lines(tauri_path)),
        task_id_to_entry=_load_go_service_mapping(_read_lines(go_service_path)),
    )

    _AUX_CACHE_KEY = cache_key
    _AUX_CACHE_VALUE = auxiliary_data
    return auxiliary_data


def _collect_run_context(lines: list[str]) -> RunContext:
    """从本次输入日志中收集时间范围、task_id 和 entry。"""

    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    task_ids: set[str] = set()
    entries: set[str] = set()

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        thread_id = _extract_thread_id(line)

        wrapped_agent_match = WRAPPED_AGENT_RE.match(line)
        if wrapped_agent_match is not None:
            line = _decode_wrapped_line(wrapped_agent_match)

        timestamp = _extract_timestamp(line)
        if timestamp is not None:
            if first_timestamp is None or timestamp < first_timestamp:
                first_timestamp = timestamp
            if last_timestamp is None or timestamp > last_timestamp:
                last_timestamp = timestamp

        task_id_match = TEXT_TASK_ID_RE.search(line)
        if task_id_match is not None:
            task_ids.add(task_id_match.group(1).strip())

        task_id_alt_match = TEXT_TASK_ID_ALT_RE.search(line)
        if task_id_alt_match is not None:
            task_ids.add(task_id_alt_match.group(1).strip())

        simple_json_match = SIMPLE_JSON_RE.match(line)
        if simple_json_match is not None:
            details = _safe_load_json_dict(simple_json_match.group(2))
            if details is not None:
                entry = _extract_entry(details, simple_json_match.group(2))
                if entry:
                    entries.add(entry)
            continue

        if line.startswith("{") and '"time"' in line and '"message"' in line:
            data = _safe_load_json_dict(line)
            if data is not None:
                entry = _extract_entry(data, line)
                if entry:
                    entries.add(entry)
            continue

        event_match = EVENT_RE.match(line)
        if event_match is not None:
            details = _safe_load_json_dict(event_match.group(3))
            if details is not None:
                entry = _extract_entry(details, event_match.group(3))
                if entry:
                    entries.add(entry)

    return RunContext(
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
        task_ids=frozenset(task_ids),
        entries=frozenset(entries),
    )


def _collect_runtime_task_starts(lines: list[str]) -> tuple[RuntimeTaskStart, ...]:
    """从运行期日志中抽取顶层任务启动顺序。"""

    task_starts: list[RuntimeTaskStart] = []

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        match = EVENT_RE.match(line)
        if match is None or match.group(2) != "Tasker.Task.Starting":
            continue

        details = _safe_load_json_dict(match.group(3))
        if details is None:
            continue

        entry = _extract_entry(details, match.group(3))
        task_id = _extract_task_id(details, match.group(3))
        if not entry or not task_id:
            continue

        try:
            timestamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            continue

        task_starts.append(
            RuntimeTaskStart(timestamp=timestamp, entry=entry, task_id=task_id)
        )

    return tuple(task_starts)


def _score_batch(
    batch: Batch, run_context: RunContext, task_id_to_entry: dict[str, str]
) -> float:
    """综合 task_id、entry 和时间，找出最像本次运行的批次。"""

    batch_task_ids = {task.task_id for task in batch.tasks if task.task_id}
    batch_entries = {task.entry for task in batch.tasks if task.entry}

    overlap_task_ids = len(run_context.task_ids & batch_task_ids)
    overlap_entries = len(run_context.entries & batch_entries)

    score = float(overlap_task_ids * 1000 + overlap_entries * 100)

    if overlap_task_ids == 0 and run_context.task_ids:
        for task_id in run_context.task_ids:
            entry = task_id_to_entry.get(task_id)
            if entry and entry in batch_entries:
                score += 60.0

    if run_context.first_timestamp is not None and batch.started_at is not None:
        delta_seconds = abs(
            (batch.started_at - run_context.first_timestamp).total_seconds()
        )
        score -= min(delta_seconds / 60.0, 500.0)
        if batch.started_at <= run_context.first_timestamp:
            score += 3.0

    score += batch.batch_id / 1000.0
    return score


def _select_best_batch(
    batches: tuple[Batch, ...],
    run_context: RunContext,
    task_id_to_entry: dict[str, str],
) -> Batch | None:
    """选择与当前输入日志最匹配的一次 start_tasks 批次。"""

    best_batch: Batch | None = None
    best_score: float | None = None

    for batch in batches:
        score = _score_batch(batch, run_context, task_id_to_entry)
        if best_score is None or score > best_score:
            best_batch = batch
            best_score = score

    return best_batch


def _score_snapshot(snapshot: Snapshot, batch: Batch) -> tuple[int, int, int]:
    """根据任务顺序匹配度给配置快照打分。"""

    enabled_tasks = [task for task in snapshot.tasks if task.enabled]
    if not enabled_tasks:
        return (-10_000, -10_000, -10_000)

    batch_entries = [task.entry for task in batch.tasks if task.entry]
    matched_positions = 0
    limit = min(len(enabled_tasks), len(batch_entries))
    for index in range(limit):
        if _task_name_matches(enabled_tasks[index].task_name, batch_entries[index]):
            matched_positions += 1

    score = matched_positions * 100
    if len(enabled_tasks) == len(batch_entries):
        score += 25
    score -= abs(len(enabled_tasks) - len(batch_entries)) * 20

    if batch.instance_id and snapshot.instance_id == batch.instance_id:
        score += 18
        if snapshot.source == "instance":
            score += 8

    recency = snapshot.closed_at if snapshot.closed_at is not None else -1
    source_rank = 1 if snapshot.source == "instance" else 0
    return (score, source_rank, recency)


def _select_best_snapshot(
    batch: Batch, snapshots: tuple[Snapshot, ...]
) -> Snapshot | None:
    """选择最能解释本批次 entry 顺序的配置快照。"""

    best_snapshot: Snapshot | None = None
    best_score: tuple[int, int, int] | None = None

    for snapshot in snapshots:
        score = _score_snapshot(snapshot, batch)
        if best_score is None or score > best_score:
            best_snapshot = snapshot
            best_score = score

    return best_snapshot


def _build_selected_task_mapping(
    batch: Batch | None,
    snapshot: Snapshot | None,
    task_id_to_entry: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """构建 task_id -> selected_task_id 和 entry -> selected_task_id 映射。"""

    task_id_to_selected_task_id: dict[str, str] = {}
    entry_to_selected_candidates: dict[str, list[str]] = {}

    if batch is None or snapshot is None:
        return task_id_to_selected_task_id, {}

    enabled_tasks = [task for task in snapshot.tasks if task.enabled]
    limit = min(len(enabled_tasks), len(batch.tasks))

    for index in range(limit):
        selected_task_id = enabled_tasks[index].id
        batch_task = batch.tasks[index]
        if batch_task.entry:
            entry_to_selected_candidates.setdefault(batch_task.entry, []).append(
                selected_task_id
            )
        if batch_task.task_id:
            task_id_to_selected_task_id[batch_task.task_id] = selected_task_id

    entry_to_selected_unique = {
        entry: selected_ids[0]
        for entry, selected_ids in entry_to_selected_candidates.items()
        if len(selected_ids) == 1
    }

    for task_id, entry in task_id_to_entry.items():
        if task_id in task_id_to_selected_task_id:
            continue
        selected_task_id = entry_to_selected_unique.get(entry)
        if selected_task_id:
            task_id_to_selected_task_id[task_id] = selected_task_id

    return task_id_to_selected_task_id, entry_to_selected_unique


def _build_global_task_id_mapping(
    batches: tuple[Batch, ...],
    snapshots: tuple[Snapshot, ...],
    task_id_to_entry: dict[str, str],
) -> dict[str, str]:
    """为所有批次建立全局 task_id -> selected_task_id 映射。"""

    task_id_to_selected_task_id: dict[str, str] = {}

    for batch in batches:
        snapshot = _select_best_snapshot(batch, snapshots)
        batch_mapping, _ = _build_selected_task_mapping(
            batch, snapshot, task_id_to_entry
        )
        for task_id, selected_task_id in batch_mapping.items():
            task_id_to_selected_task_id.setdefault(task_id, selected_task_id)

    return task_id_to_selected_task_id


def _build_selected_task_name_mapping(
    snapshots: tuple[Snapshot, ...],
) -> dict[str, str]:
    """构建 selected_task_id -> taskName 映射，优先使用当前实例快照。"""

    selected_task_name_mapping: dict[str, str] = {}

    for snapshot in snapshots:
        if snapshot.source != "instance":
            continue
        for task in snapshot.tasks:
            selected_task_name_mapping[task.id] = task.task_name

    for snapshot in snapshots:
        if snapshot.source == "instance":
            continue
        for task in snapshot.tasks:
            selected_task_name_mapping.setdefault(task.id, task.task_name)

    return selected_task_name_mapping


def _build_runtime_start_fallback_mapping(
    runtime_task_starts: tuple[RuntimeTaskStart, ...],
    snapshots: tuple[Snapshot, ...],
) -> dict[str, str]:
    """当 tauri 批次日志不完整时，用顶层任务启动顺序回填映射。"""

    if not runtime_task_starts:
        return {}

    instance_snapshots = [
        snapshot for snapshot in snapshots if snapshot.source == "instance"
    ]
    candidate_snapshots = instance_snapshots if instance_snapshots else list(snapshots)

    best_snapshot: Snapshot | None = None
    best_score: tuple[int, int, int] | None = None

    for snapshot in candidate_snapshots:
        enabled_tasks = [task for task in snapshot.tasks if task.enabled]
        if not enabled_tasks:
            continue

        start_index = 0
        matched = 0
        for task in enabled_tasks:
            while start_index < len(runtime_task_starts):
                start = runtime_task_starts[start_index]
                if _task_name_matches(task.task_name, start.entry):
                    matched += 1
                    start_index += 1
                    break
                start_index += 1

        if matched == 0:
            continue

        score = (
            matched * 100 - abs(len(enabled_tasks) - matched) * 20,
            1 if snapshot.source == "instance" else 0,
            snapshot.closed_at if snapshot.closed_at is not None else -1,
        )
        if best_score is None or score > best_score:
            best_snapshot = snapshot
            best_score = score

    if best_snapshot is None:
        return {}

    mapping: dict[str, str] = {}
    enabled_tasks = [task for task in best_snapshot.tasks if task.enabled]
    start_index = 0
    for task in enabled_tasks:
        while start_index < len(runtime_task_starts):
            start = runtime_task_starts[start_index]
            start_index += 1
            if _task_name_matches(task.task_name, start.entry):
                mapping[start.task_id] = task.id
                break

    return mapping


def _resolve_selected_task_id(
    task_id: str,
    current_selected_task_id: str,
    task_id_to_selected_task_id: dict[str, str],
) -> str:
    """仅使用显式 task_id 映射还原 selected_task_id。"""

    if task_id:
        selected_task_id = task_id_to_selected_task_id.get(task_id)
        if selected_task_id:
            return selected_task_id

    return current_selected_task_id


def _timestamp_text_to_datetime(timestamp_text: str) -> datetime | None:
    """把标准展示时间转回 datetime，失败时返回空。"""

    try:
        return datetime.strptime(timestamp_text, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None


def _extract_thread_id(line: str) -> str:
    """提取 MaaFramework 日志中的线程 ID。"""

    match = THREAD_ID_RE.search(line)
    return match.group(1) if match is not None else ""


def _inherit_task_mapping_from_thread(
    task_id: str,
    thread_id: str,
    current_selected_task_id: str,
    task_id_to_selected_task_id: dict[str, str],
    thread_selected_task_id: dict[str, str],
) -> str:
    """当子任务 ID 未出现在固定批次映射中时，尝试继承同线程父任务归属。"""

    if not task_id:
        return current_selected_task_id

    selected_task_id = task_id_to_selected_task_id.get(task_id, "")
    if selected_task_id:
        if thread_id:
            thread_selected_task_id[thread_id] = selected_task_id
        return selected_task_id

    inherited_selected_task_id = ""
    if thread_id:
        inherited_selected_task_id = thread_selected_task_id.get(thread_id, "")
    if not inherited_selected_task_id:
        inherited_selected_task_id = current_selected_task_id

    if inherited_selected_task_id:
        task_id_to_selected_task_id[task_id] = inherited_selected_task_id
        if thread_id:
            thread_selected_task_id[thread_id] = inherited_selected_task_id
        return inherited_selected_task_id

    return current_selected_task_id


def _append_unresolved_diagnosis(
    message: str,
    timestamp_text: str,
    task_id: str,
    current_selected_task_id: str,
    known_task_ids: set[str],
    earliest_post_task_time: datetime | None,
    should_diagnose: bool,
) -> str:
    """为未解析到任务 ID 的日志追加诊断信息。"""

    if current_selected_task_id or not should_diagnose:
        return message

    reason = ""
    if task_id:
        if task_id not in known_task_ids:
            reason = f"未解析原因: task_id={task_id} 未出现在固定批次映射中"
        else:
            reason = f"未解析原因: task_id={task_id} 已出现但未成功落到前端任务"
    else:
        current_time = _timestamp_text_to_datetime(timestamp_text)
        if (
            current_time is not None
            and earliest_post_task_time is not None
            and current_time <= earliest_post_task_time
        ):
            reason = "未解析原因: 当前日志早于或紧邻 post_task，尚未建立 task_id 映射"
        else:
            reason = "未解析原因: 当前日志未携带 task_id"

    return f"{message} [{reason}]"


def parse_log(root_dir: Path, lines: list[str]) -> list[str]:
    """解析 MaaEnd 日志，并尽量稳定还原前端任务 ID。"""

    auxiliary_data = _build_auxiliary_data(root_dir)
    run_context = _collect_run_context(lines)
    runtime_task_starts = _collect_runtime_task_starts(lines)
    task_id_to_selected_task_id = _build_global_task_id_mapping(
        auxiliary_data.batches,
        auxiliary_data.snapshots,
        auxiliary_data.task_id_to_entry,
    )
    selected_task_name_mapping = _build_selected_task_name_mapping(
        auxiliary_data.snapshots
    )
    for task_id, selected_task_id in _build_runtime_start_fallback_mapping(
        runtime_task_starts,
        auxiliary_data.snapshots,
    ).items():
        task_id_to_selected_task_id.setdefault(task_id, selected_task_id)
    known_task_ids = set(task_id_to_selected_task_id)
    earliest_post_task_time = min(
        (
            task.posted_at
            for batch in auxiliary_data.batches
            for task in batch.tasks
            if task.posted_at is not None
        ),
        default=None,
    )
    result: list[str] = []
    undated_indices: list[int] = []
    current_date = (
        run_context.first_timestamp.strftime("%Y-%m-%d")
        if run_context.first_timestamp is not None
        else ""
    )
    current_selected_task_id = ""
    current_maa_task_id = ""
    thread_selected_task_id: dict[str, str] = {}
    pending_panel_time = ""
    pending_panel_lines: list[str] = []
    last_emit_key = ""
    last_emit_time: datetime | None = None

    def flush_panel() -> None:
        nonlocal pending_panel_time, pending_panel_lines
        if not pending_panel_time or not pending_panel_lines:
            pending_panel_time = ""
            pending_panel_lines = []
            return

        panel_line = (
            f"[{current_date} {pending_panel_time}.000] {current_selected_task_id} - "
            + "\n".join(pending_panel_lines)
            + "\n"
        )
        if not current_date:
            undated_indices.append(len(result))
            panel_line = panel_line.replace(f"[{current_date} ", "[ ", 1)
        result.append(panel_line)
        pending_panel_time = ""
        pending_panel_lines = []

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        thread_id = _extract_thread_id(line)

        wrapped_agent_match = WRAPPED_AGENT_RE.match(line)
        if wrapped_agent_match is not None:
            line = _decode_wrapped_line(wrapped_agent_match)
        elif INLINE_INSTANCE_RE.search(line) is not None and not (
            FULL_TS_RE.match(line)
            or ISO_TS_RE.match(line)
            or SIMPLE_JSON_RE.match(line)
            or EVENT_RE.match(line)
            or PANEL_TS_RE.match(line)
        ):
            # 纯实例包装行不直接参与展示，但不要误伤带业务内容的行。
            continue

        timestamp = _extract_timestamp(line)
        if timestamp is not None:
            current_date = timestamp.strftime("%Y-%m-%d")
            if undated_indices:
                for index in undated_indices:
                    result[index] = result[index].replace("[ ", f"[{current_date} ", 1)
                undated_indices = []

        panel_ts_match = PANEL_TS_RE.match(line)
        if panel_ts_match is not None:
            flush_panel()
            pending_panel_time = panel_ts_match.group(1)
            pending_panel_lines = []
            continue

        if pending_panel_time:
            if NEXT_FULL_TS_RE.match(line) or NEXT_PANEL_TS_RE.match(line):
                flush_panel()
            else:
                pending_panel_lines.append(line)
                continue

        agent_log_match = AGENT_LOG_RE.match(line)
        if agent_log_match is not None:
            timestamp_text = (
                f"{agent_log_match.group(1)} {agent_log_match.group(2)}.000"
            )
            message = f"{agent_log_match.group(3)} {agent_log_match.group(4)}"
            task_id_match = TEXT_TASK_ID_RE.search(message)
            task_id_alt_match = TEXT_TASK_ID_ALT_RE.search(message)
            task_id = ""
            if task_id_match is not None:
                task_id = task_id_match.group(1).strip()
            elif task_id_alt_match is not None:
                task_id = task_id_alt_match.group(1).strip()

            if task_id:
                current_maa_task_id = task_id
            current_selected_task_id = _inherit_task_mapping_from_thread(
                task_id=current_maa_task_id,
                thread_id=thread_id,
                current_selected_task_id=_resolve_selected_task_id(
                    task_id=current_maa_task_id,
                    current_selected_task_id=current_selected_task_id,
                    task_id_to_selected_task_id=task_id_to_selected_task_id,
                ),
                task_id_to_selected_task_id=task_id_to_selected_task_id,
                thread_selected_task_id=thread_selected_task_id,
            )
            message = _append_unresolved_diagnosis(
                message=message,
                timestamp_text=timestamp_text,
                task_id=current_maa_task_id,
                current_selected_task_id=current_selected_task_id,
                known_task_ids=known_task_ids,
                earliest_post_task_time=earliest_post_task_time,
                should_diagnose=bool(current_maa_task_id),
            )
            last_emit_key, last_emit_time = _emit_log_line(
                result,
                timestamp_text,
                current_selected_task_id,
                message,
                last_emit_key,
                last_emit_time,
            )
            continue

        simple_json_match = SIMPLE_JSON_RE.match(line)
        if simple_json_match is not None:
            timestamp_text = simple_json_match.group(1)
            details = _safe_load_json_dict(simple_json_match.group(2))
            if details is None:
                continue

            event_name = (
                details.get("event") if isinstance(details.get("event"), str) else ""
            )
            task_id = _extract_task_id(details, simple_json_match.group(2))
            entry = _extract_entry(details, simple_json_match.group(2))
            if task_id:
                current_maa_task_id = task_id
            current_selected_task_id = _inherit_task_mapping_from_thread(
                task_id=current_maa_task_id,
                thread_id=thread_id,
                current_selected_task_id=_resolve_selected_task_id(
                    task_id=current_maa_task_id,
                    current_selected_task_id=current_selected_task_id,
                    task_id_to_selected_task_id=task_id_to_selected_task_id,
                ),
                task_id_to_selected_task_id=task_id_to_selected_task_id,
                thread_selected_task_id=thread_selected_task_id,
            )

            if event_name in TASK_EVENT_TEXT:
                message = TASK_EVENT_TEXT[event_name]
                display_task_name = selected_task_name_mapping.get(
                    current_selected_task_id, ""
                )
                if display_task_name:
                    message += f": {display_task_name}"
                elif entry:
                    message += f": {entry}"
                message = _append_unresolved_diagnosis(
                    message=message,
                    timestamp_text=timestamp_text,
                    task_id=current_maa_task_id,
                    current_selected_task_id=current_selected_task_id,
                    known_task_ids=known_task_ids,
                    earliest_post_task_time=earliest_post_task_time,
                    should_diagnose=True,
                )
                last_emit_key, last_emit_time = _emit_log_line(
                    result,
                    timestamp_text,
                    current_selected_task_id,
                    message,
                    last_emit_key,
                    last_emit_time,
                )
            continue

        if line.startswith("{") and '"time"' in line and '"message"' in line:
            json_line = _safe_load_json_dict(line)
            if json_line is None:
                continue

            json_time = json_line.get("time")
            json_message = json_line.get("message")
            if not isinstance(json_time, str) or not isinstance(json_message, str):
                continue

            json_time_match = ISO_TS_RE.match(json_time)
            if json_time_match is None:
                continue

            timestamp_text = (
                f"{json_time_match.group(1)} {json_time_match.group(2)}.000"
            )
            task_id = _extract_task_id(json_line, line)
            entry = _extract_entry(json_line, line)
            if task_id:
                current_maa_task_id = task_id
            current_selected_task_id = _inherit_task_mapping_from_thread(
                task_id=current_maa_task_id,
                thread_id=thread_id,
                current_selected_task_id=_resolve_selected_task_id(
                    task_id=current_maa_task_id,
                    current_selected_task_id=current_selected_task_id,
                    task_id_to_selected_task_id=task_id_to_selected_task_id,
                ),
                task_id_to_selected_task_id=task_id_to_selected_task_id,
                thread_selected_task_id=thread_selected_task_id,
            )

            level_text = (
                json_line["level"].upper()
                if isinstance(json_line.get("level"), str)
                else ""
            )
            message = f"{level_text} {json_message}" if level_text else json_message
            message = _append_unresolved_diagnosis(
                message=message,
                timestamp_text=timestamp_text,
                task_id=current_maa_task_id,
                current_selected_task_id=current_selected_task_id,
                known_task_ids=known_task_ids,
                earliest_post_task_time=earliest_post_task_time,
                should_diagnose=bool(task_id or entry),
            )
            last_emit_key, last_emit_time = _emit_log_line(
                result,
                timestamp_text,
                current_selected_task_id,
                message,
                last_emit_key,
                last_emit_time,
            )
            continue

        event_match = EVENT_RE.match(line)
        if event_match is None:
            continue

        timestamp_text = event_match.group(1)
        event_name = event_match.group(2)
        details = _safe_load_json_dict(event_match.group(3))
        if details is None:
            continue

        task_id = _extract_task_id(details, event_match.group(3))
        entry = _extract_entry(details, event_match.group(3))
        if task_id:
            current_maa_task_id = task_id
        current_selected_task_id = _inherit_task_mapping_from_thread(
            task_id=current_maa_task_id,
            thread_id=thread_id,
            current_selected_task_id=_resolve_selected_task_id(
                task_id=current_maa_task_id,
                current_selected_task_id=current_selected_task_id,
                task_id_to_selected_task_id=task_id_to_selected_task_id,
            ),
            task_id_to_selected_task_id=task_id_to_selected_task_id,
            thread_selected_task_id=thread_selected_task_id,
        )

        message = ""
        if event_name in TASK_EVENT_TEXT:
            message = TASK_EVENT_TEXT[event_name]
            display_task_name = selected_task_name_mapping.get(
                current_selected_task_id, ""
            )
            if display_task_name:
                message += f": {display_task_name}"
            elif entry:
                message += f": {entry}"
        elif event_name in RESOURCE_EVENT_TEXT:
            if event_name == "Resource.Loading.Starting":
                current_selected_task_id = ""
            path_text = (
                details.get("path") if isinstance(details.get("path"), str) else ""
            )
            message = RESOURCE_EVENT_TEXT[event_name]
            if path_text:
                message += f": {path_text}"
        elif event_name in CONTROLLER_EVENT_TEXT:
            action_text = (
                details.get("action") if isinstance(details.get("action"), str) else ""
            )
            param_action_text = ""
            if isinstance(details.get("param"), dict):
                param_action = details["param"].get("action")
                if isinstance(param_action, str):
                    param_action_text = param_action
            if (
                str(action_text).lower() != "connect"
                and param_action_text.lower() != "connect"
            ):
                continue
            message = CONTROLLER_EVENT_TEXT[event_name]
            target_text = (
                details.get("target") if isinstance(details.get("target"), str) else ""
            )
            if target_text:
                message += f": {target_text}"
        else:
            focus = details.get("focus")
            if not isinstance(focus, dict):
                continue
            focus_entry = focus.get(event_name)
            if isinstance(focus_entry, str):
                message = focus_entry
            elif isinstance(focus_entry, dict):
                content = focus_entry.get("content")
                if not isinstance(content, str) or not content:
                    continue
                display = focus_entry.get("display")
                display_list: list[str] = []
                if isinstance(display, str):
                    display_list = [display]
                elif isinstance(display, list):
                    display_list = [item for item in display if isinstance(item, str)]
                if display_list and not any(
                    item in ("log", "dialog", "modal") for item in display_list
                ):
                    continue
                message = content
            else:
                continue

            for key, value in details.items():
                if key == "focus" or value is None:
                    continue
                if isinstance(value, (str, int, float, bool)):
                    message = message.replace("{" + key + "}", str(value))
            message = message.replace("{image}", "").strip()
            if not message:
                continue

        message = _append_unresolved_diagnosis(
            message=message,
            timestamp_text=timestamp_text,
            task_id=current_maa_task_id,
            current_selected_task_id=current_selected_task_id,
            known_task_ids=known_task_ids,
            earliest_post_task_time=earliest_post_task_time,
            should_diagnose=event_name not in RESOURCE_EVENT_TEXT
            and event_name not in CONTROLLER_EVENT_TEXT,
        )

        last_emit_key, last_emit_time = _emit_log_line(
            result,
            timestamp_text,
            current_selected_task_id,
            message,
            last_emit_key,
            last_emit_time,
        )

    flush_panel()

    if current_date and undated_indices:
        for index in undated_indices:
            result[index] = result[index].replace("[ ", f"[{current_date} ", 1)

    return result
