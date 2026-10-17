"""MAA base defaults used when a managed configuration is first created."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from app.utils.io import ConfigCorruptedError, read_dict_file, read_file, write_file

MAA_BASE_PRESET_PATH = Path(__file__).with_name("base_preset.json")
MAA_STAMINA_LEGACY_FILENAME = "_mas_stamina_legacy.json"
"""已收起的活动优先原生任务原文；仅随 MAS owner 配置保存，不下发给 MAA。"""

_MAA_STAMINA_TASK_ALIASES = {
    ("DepotMaintain", "活动库存保持"): ("DepotMaintain", "活动关均衡理智"),
    ("DepotMaintain", ""): ("DepotMaintain", "库存保持与干员养成"),
    ("DepotMaintain", "库存保持"): ("DepotMaintain", "库存保持与干员养成"),
    ("Fight", "理智作战"): ("Fight", "理智任务"),
}


def _validate_maa_base_preset(payload: object) -> dict[str, Any]:
    """Validate the structure consumed by MAS before it reaches MAA."""

    if not isinstance(payload, dict):
        raise ValueError("MAA 预设根节点必须是对象")
    configurations = payload.get("Configurations")
    if not isinstance(configurations, dict):
        raise ValueError("MAA 预设缺少 Configurations 对象")
    default = configurations.get("Default")
    if not isinstance(default, dict):
        raise ValueError("MAA 预设缺少 Configurations.Default 对象")
    queue = default.get("TaskQueue")
    if not isinstance(queue, list) or not queue:
        raise ValueError("MAA 预设的 Default.TaskQueue 必须是非空数组")

    # 只校验 MAS 会硬索引的结构与任务身份，MAA 其余字段由上游解释。
    for index, task in enumerate(queue):
        if not isinstance(task, dict):
            raise ValueError(f"MAA 预设任务 {index + 1} 必须是对象")
        if not isinstance(task.get("$type"), str) or not task["$type"]:
            raise ValueError(f"MAA 预设任务 {index + 1} 缺少非空 $type")
        if not isinstance(task.get("TaskType"), str) or not task["TaskType"]:
            raise ValueError(f"MAA 预设任务 {index + 1} 缺少 TaskType")
        if not isinstance(task.get("Name"), str):
            raise ValueError(f"MAA 预设任务 {index + 1} 缺少 Name")
    return payload


def _load_maa_base_preset() -> dict[str, Any]:
    """Load and validate the checked-in MAA preset file."""

    payload = read_dict_file(MAA_BASE_PRESET_PATH)
    try:
        return _validate_maa_base_preset(payload)
    except ValueError as exc:
        raise ConfigCorruptedError(MAA_BASE_PRESET_PATH) from exc


_MAA_BASE_PRESET = {
    "gui.json": {
        "Current": "Default",
        "Global": {
            "GUI.Localization": "zh-cn",
            "GUI.UseTray": "False",
            "GUI.MinimizeToTray": "False",
            "Start.MinimizeDirectly": "False",
            **{f"Timer.Timer{index}": "False" for index in range(1, 9)},
        },
        "Configurations": {"Default": {}},
    },
    "gui.new.json": _load_maa_base_preset(),
}


def get_maa_base_preset(name: str) -> dict:
    """Return an independent copy of one MAA base configuration preset."""

    return deepcopy(_MAA_BASE_PRESET[name])


def update_maa_base_preset(payload: object) -> dict[str, Any]:
    """Persist and activate a new MAA base preset in the running process."""

    preset = deepcopy(_validate_maa_base_preset(payload))
    write_file(MAA_BASE_PRESET_PATH, preset)
    return reload_maa_base_preset()


def reload_maa_base_preset() -> dict[str, Any]:
    """Reload the checked-in preset into the running MAA defaults."""

    preset = _load_maa_base_preset()
    _MAA_BASE_PRESET["gui.new.json"] = deepcopy(preset)
    return deepcopy(preset)


def seed_maa_base_config(config_dir: Path) -> None:
    """Create missing managed MAA base files without replacing existing settings."""

    config_dir.mkdir(parents=True, exist_ok=True)
    for name, preset in _MAA_BASE_PRESET.items():
        path = config_dir / name
        if not path.exists():
            write_file(path, deepcopy(preset))


def capture_maa_legacy_activity_sources(
    config_dir: Path,
    gui_new_set: dict,
    *,
    current_configuration: str = "Default",
) -> None:
    """收起旧活动优先入口前，按配置方案保留其完整原生高级设置。"""

    configurations = gui_new_set.get("Configurations")
    if not isinstance(configurations, dict):
        return
    path = config_dir / MAA_STAMINA_LEGACY_FILENAME
    sources = read_file(path) if path.exists() else {}
    if not isinstance(sources, dict):
        sources = {}
    changed = False
    for name, configuration in configurations.items():
        if not isinstance(configuration, dict):
            continue
        queue = configuration.get("TaskQueue")
        if not isinstance(queue, list):
            continue
        source = next(
            (
                task
                for task in queue
                if maa_task_identity(task) == ("Fight", "活动关优先")
            ),
            None,
        )
        if source is not None and sources.get(name) != source:
            sources[name] = deepcopy(source)
            changed = True
    if current_configuration != "Default" and isinstance(
        configurations.get(current_configuration), dict
    ):
        # 当前方案会折叠成 Default；保留来源也必须随之对齐，不能继承旧 Default。
        selected = sources.get(current_configuration)
        if selected is not None and sources.get("Default") != selected:
            sources["Default"] = deepcopy(selected)
            changed = True
        elif selected is None and "Default" in sources:
            del sources["Default"]
            changed = True
    if changed:
        write_file(path, sources)


def load_maa_stamina_legacy_task(
    config_dir: Path, configuration: str = "Default"
) -> dict | None:
    """从当前 MAS owner 读取已收起的活动优先来源，不读取安装目录残留。"""

    path = config_dir / MAA_STAMINA_LEGACY_FILENAME
    if not path.exists():
        return None
    sources = read_file(path)
    if not isinstance(sources, dict):
        return None
    task = sources.get(configuration)
    return (
        deepcopy(task) if maa_task_identity(task) == ("Fight", "活动关优先") else None
    )


def ensure_maa_default_configuration(gui_set: dict, gui_new_set: dict) -> None:
    """Fold the current configuration into ``Default`` and guarantee both sides.

    MAA's native files are not guaranteed to ship ``Default``: direct control and
    "source directory missing, keep the configuration in the install directory"
    both copy the user's own gui.json / gui.new.json in as-is, and ``Current`` may
    already be ``Default``. Folding and the fallback must therefore run
    unconditionally, or the later hard indexing of ``Global`` /
    ``Configurations["Default"]`` raises ``KeyError``.
    """

    if not isinstance(gui_set.get("Global"), dict):
        gui_set["Global"] = {}

    gui_configurations = gui_set.get("Configurations")
    if not isinstance(gui_configurations, dict):
        gui_configurations = gui_set["Configurations"] = {}
    configurations = gui_new_set.get("Configurations")
    if not isinstance(configurations, dict):
        configurations = gui_new_set["Configurations"] = {}
    gui_configurations.setdefault("Default", {})
    configurations.setdefault("Default", {})
    gui_set.setdefault("Current", "Default")

    if gui_set["Current"] != "Default":
        # The current configuration itself may be missing (hand-edited third-party
        # files): fold it only when present, as the older verified AutoProxy /
        # ScriptConfig code did, and otherwise keep each side's own Default.
        current = gui_set["Current"]
        if current in gui_configurations:
            gui_configurations["Default"] = gui_configurations[current]
        if current in configurations:
            configurations["Default"] = configurations[current]
        gui_set["Current"] = "Default"


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
