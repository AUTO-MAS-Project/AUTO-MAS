"""MAA base defaults used when a managed configuration is first created."""

import json
from copy import deepcopy
from pathlib import Path

from app.utils.io import write_file

MAA_STAMINA_LEGACY_FILENAME = "_mas_stamina_legacy.json"
"""历史活动优先侧车文件；保留时不复制到 MAA 运行目录。"""

_MAA_STAMINA_TASK_ALIASES = {
    ("DepotMaintain", "活动库存保持"): ("DepotMaintain", "活动关均衡理智"),
    ("DepotMaintain", ""): ("DepotMaintain", "库存保持与干员养成"),
    ("DepotMaintain", "库存保持"): ("DepotMaintain", "库存保持与干员养成"),
    ("Fight", "理智作战"): ("Fight", "理智任务"),
}

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
    "gui.new.json": {
        **json.loads(
            Path(__file__).with_name("base_preset.json").read_text(encoding="utf-8")
        ),
    },
}


def get_maa_base_preset(name: str) -> dict:
    """Return an independent copy of one MAA base configuration preset."""

    return deepcopy(_MAA_BASE_PRESET[name])


def seed_maa_base_config(config_dir: Path) -> None:
    """Create missing managed MAA base files without replacing existing settings."""

    config_dir.mkdir(parents=True, exist_ok=True)
    for name, preset in _MAA_BASE_PRESET.items():
        path = config_dir / name
        if not path.exists():
            write_file(path, deepcopy(preset))


def _fill_missing(target: dict, defaults: dict) -> None:
    """把 ``defaults`` 里 ``target`` 缺失的键补进去；已有值一律不动。"""

    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(target[key], dict) and isinstance(value, dict):
            _fill_missing(target[key], value)


def _migrate_legacy_root_gui(gui_new_set: dict, base_gui: dict) -> None:
    """
    一次性将根级 GUI（旧格式）迁移到 Gui（新格式）

    检测到根级 ``GUI`` 时立即升级为 ``Gui`` 并删除旧键，避免后续代码需要处理兼容。
    迁移时会补充缺失的字段（如 ``GuideStep``），确保 MAA 不会弹新手引导。

    Args:
        gui_new_set: gui.new.json 配置对象
        base_gui: base_preset.json 中的 Gui 默认值
    """

    if "GUI" not in gui_new_set:
        return

    # 情况 1: 同时有 GUI 和 Gui（理论上不应该出现）
    # 优先保留 Gui（新格式），直接删除 GUI
    if "Gui" in gui_new_set:
        del gui_new_set["GUI"]
        return

    # 情况 2: 只有 GUI（旧格式），执行一次性迁移
    legacy_gui = gui_new_set["GUI"]
    gui_new_set["Gui"] = legacy_gui.copy()

    # 补充缺失的字段（如 GuideStep = 7）
    _fill_missing(gui_new_set["Gui"], base_gui)

    # 删除旧的根级 GUI
    del gui_new_set["GUI"]


# 随包预设里由 MAA 自己维护、MAS 不该代填的根级键：配置版本与迁移元数据一旦写错
# 会触发 MAA 的旧格式迁移器，反而把整份配置判成不可解析。
_MAA_ROOT_KEYS_NOT_FILLED = frozenset({"Configurations", "Current", "ConfigVersion"})


def ensure_maa_default_configuration(gui_set: dict, gui_new_set: dict) -> None:
    """Fold the current configuration into ``Default`` and guarantee both sides.

    MAA's native files are not guaranteed to ship ``Default``: direct control and
    "source directory missing, keep the configuration in the install directory"
    both copy the user's own gui.json / gui.new.json in as-is, and ``Current`` may
    already be ``Default``. Folding and the fallback must therefore run
    unconditionally, or the later hard indexing of ``Global`` /
    ``Configurations["Default"]`` raises ``KeyError``.

    根级 ``Gui` / ``Timers`` 也按随包预设补齐缺键：存档是用户自己那份 MAA 配置的
    副本，MAA 后来新增的字段（尤其 ``Gui.GuideStep``）在里面根本不存在，下发后
    MAA 每次都按首次运行处理，直接把新手引导弹出来。只补缺失键，不覆盖用户值。
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

    # 一次性迁移：将根级 GUI（旧格式）升级到 Gui（新格式）
    # 检测到旧格式立即升级并清理，后续代码只处理新格式
    _migrate_legacy_root_gui(gui_new_set, get_maa_base_preset("gui.new.json").get("Gui", {}))

    for name, doc in (("gui.json", gui_set), ("gui.new.json", gui_new_set)):
        preset = get_maa_base_preset(name)
        for key, value in preset.items():
            if key in _MAA_ROOT_KEYS_NOT_FILLED:
                continue
            _fill_missing(doc, {key: value})


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
