"""MAA base defaults used when a managed configuration is first created."""

import json
from copy import deepcopy
from pathlib import Path

from app.utils import io as _utils_io

MAA_STAMINA_LEGACY_FILENAME = "_mas_stamina_legacy.json"
"""历史活动优先侧车文件；保留时不复制到 MAA 运行目录。"""

_MAA_STAMINA_TASK_ALIASES = {
    ("DepotMaintain", "活动库存保持"): ("DepotMaintain", "活动关均衡理智"),
    ("DepotMaintain", ""): ("DepotMaintain", "库存保持与干员养成"),
    ("DepotMaintain", "库存保持"): ("DepotMaintain", "库存保持与干员养成"),
    ("Fight", "理智作战"): ("Fight", "理智任务"),
}

_MAA_BASE_PRESET = json.loads(
    Path(__file__).with_name("base_preset.json").read_text(encoding="utf-8")
)


def get_maa_base_preset() -> dict:
    """Return an independent copy of the MAA base configuration preset."""

    return deepcopy(_MAA_BASE_PRESET)


def seed_maa_base_config(config_dir: Path) -> None:
    """Create the managed MAA configuration without replacing existing settings."""

    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "gui.new.json"
    if not path.exists():
        _utils_io.write_file(path, deepcopy(_MAA_BASE_PRESET))


def _fill_missing(target: dict, defaults: dict) -> None:
    """把 ``defaults`` 里 ``target`` 缺失的键补进去；已有值一律不动。"""

    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(target[key], dict) and isinstance(value, dict):
            _fill_missing(target[key], value)


# 随包预设里由 MAA 自己维护、MAS 不该代填的根级键：配置版本与迁移元数据一旦写错
# 会触发 MAA 的旧格式迁移器，反而把整份配置判成不可解析。
_MAA_ROOT_KEYS_NOT_FILLED = frozenset({"Configurations", "Current", "ConfigVersion"})


def _ensure_mapping(parent: dict, key: str) -> dict:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = parent[key] = {}
    return value


def _normalize_root_gui(doc: dict) -> None:
    """把旧版根级 ``GUI`` 合并进 ``Gui``，之后只写 ``Gui``。

    旧版 MAA 的根级 ``GUI`` 只应出现一次。MAS 自己完成这次重命名，
    不再依赖 MAA 的迁移器，也不在废弃字段上写运行期配置。
    """

    legacy = doc.pop("GUI", None)
    gui = _ensure_mapping(doc, "Gui")
    if isinstance(legacy, dict):
        # 已有 Gui 优先，旧 GUI 只补缺键，避免反过来覆盖新配置。
        _fill_missing(gui, legacy)

    guide_step = gui.get("GuideStep")
    if (
        isinstance(guide_step, bool)
        or not isinstance(guide_step, int)
        or guide_step <= 0
    ):
        gui["GuideStep"] = 7


def ensure_maa_default_configuration(gui_new_set: dict) -> None:
    """Fold the active configuration into ``Default`` and guarantee its containers.

    MAA's native file is not guaranteed to ship ``Default``: direct control and
    "source directory missing, keep the configuration in the install directory"
    both copy the user's own gui.new.json in as-is, and ``Current`` may already be
    ``Default``. Folding and the fallback must therefore run unconditionally, or
    the later hard indexing of ``Configurations["Default"]`` raises ``KeyError``.

    根级 ``Gui`` / ``Timers`` 也按随包预设补齐缺键：存档是用户自己那份 MAA 配置的
    副本，MAA 后来新增的字段（尤其 ``Gui.GuideStep``）在里面根本不存在，下发后
    MAA 每次都按首次运行处理，直接把新手引导弹出来。只补缺失键，不覆盖用户值；
    旧版根级 ``GUI`` 先合并进 ``Gui`` 并删除，后续只认 ``Gui``；折叠方案后
    再补 ``Default.Gui`` 的运行期容器，直接索引不会落空。
    """

    _normalize_root_gui(gui_new_set)

    configurations = _ensure_mapping(gui_new_set, "Configurations")
    configurations.setdefault("Default", {})

    current = gui_new_set.get("Current")
    if isinstance(current, str) and current not in ("", "Default"):
        # 当前方案可能不存在（手改过的第三方文件）：只在存在时折叠，
        # 否则保留文件自己的 Default。
        source = configurations.get(current)
        if isinstance(source, dict):
            configurations["Default"] = source
    gui_new_set["Current"] = "Default"

    # 折叠当前方案后再补 Default.Gui 的容器，避免刚补好的 Default 被覆盖。
    default_gui = _ensure_mapping(_ensure_mapping(configurations, "Default"), "Gui")
    for key in ("ConnectSettings", "RuntimeSettings", "StartUpSettings"):
        _ensure_mapping(default_gui, key)

    preset = get_maa_base_preset()
    for key, value in preset.items():
        if key in _MAA_ROOT_KEYS_NOT_FILLED:
            continue
        _fill_missing(gui_new_set, {key: value})


def maa_task_identity(task: object) -> tuple[str, str] | None:
    """Return the stable business identity of one MAA task.

    ``$type`` is serialization metadata and is intentionally excluded: old and new
    MAA versions may spell it differently while ``TaskType`` and ``Name`` remain
    the task identity exposed by the queue.
    """

    if not isinstance(task, dict):
        return None
    task_type = task.get("TaskType")
    name = task.get("Name", "")
    if not isinstance(task_type, str) or not task_type or not isinstance(name, str):
        return None
    return task_type, name


def canonical_maa_task_identity(task: object) -> tuple[str, str] | None:
    """对齐三段理智流程的新旧任务名；结构校验仍使用原始身份。"""

    identity = maa_task_identity(task)
    return _MAA_STAMINA_TASK_ALIASES.get(identity, identity) if identity else None


def maa_task_queue_layout_signature(queue: object) -> tuple[tuple, ...] | None:
    """Return task identities in queue order, ignoring task settings."""

    if not isinstance(queue, list):
        return None
    signature = []
    for task in queue:
        identity = maa_task_identity(task)
        if identity is None:
            return None
        signature.append(identity)
    return tuple(signature)


def restore_maa_default_task_queue(
    queue: object, default_queue: list[dict]
) -> tuple[list[dict], bool]:
    """Restore default queue layout, carrying settings over by task identity."""

    default_layout = maa_task_queue_layout_signature(default_queue)
    if default_layout is None:
        raise ValueError("MAA default TaskQueue is invalid")
    if (
        isinstance(queue, list)
        and maa_task_queue_layout_signature(queue) == default_layout
    ):
        return deepcopy(queue), False

    existing_tasks: dict[tuple[str, str], dict] = {}
    if isinstance(queue, list):
        for task in queue:
            identity = canonical_maa_task_identity(task)
            if identity is not None:
                existing = existing_tasks.get(identity)
                # 新身份优先；旧库存同时有空名与有名来源时选有名项，不串用设置。
                if (
                    existing is None
                    or maa_task_identity(task) == identity
                    or (not existing.get("Name") and task.get("Name"))
                ):
                    existing_tasks[identity] = task

    # 补齐新预设时保留已有任务的勾选；只有新增任务使用预设的默认开关。
    structural_keys = {"$type", "Name", "TaskType"}
    restored_queue = []
    for default_task in default_queue:
        task = deepcopy(default_task)
        identity = canonical_maa_task_identity(task)
        existing = existing_tasks.get(identity) if identity is not None else None
        if existing is not None:
            task.update(
                {
                    key: deepcopy(value)
                    for key, value in existing.items()
                    if key not in structural_keys
                }
            )
        restored_queue.append(task)
    return restored_queue, True


def is_valid_maa_task_queue(expected: object, current: object) -> bool:
    """Allow task-setting edits only when the queue layout is unchanged.

    IsEnable 是用户在原界面里最常动的任务开关，属于任务设置而不是队列结构：
    算进签名会把「取消勾选一个任务」判成结构变化，整次会话的改动（含高级
    设置）一起丢弃。这里只比对身份序列。
    """

    expected_layout = maa_task_queue_layout_signature(expected)
    return (
        expected_layout is not None
        and maa_task_queue_layout_signature(current) == expected_layout
    )


def is_valid_maa_task_queues(expected: object, current: object) -> bool:
    """Validate queue structure for every configuration in a GUI document."""

    if not isinstance(expected, dict) or not isinstance(current, dict):
        return False
    if expected.keys() != current.keys():
        return False
    for name, expected_config in expected.items():
        current_config = current[name]
        if not isinstance(expected_config, dict) or not isinstance(
            current_config, dict
        ):
            return False
        if not is_valid_maa_task_queue(
            expected_config.get("TaskQueue"), current_config.get("TaskQueue")
        ):
            return False
    return True
