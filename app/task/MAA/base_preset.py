"""MAA base defaults used when a managed configuration is first created."""

import json
from copy import deepcopy
from pathlib import Path

from app.utils.io import write_file

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
        "Configurations": {
            "Default": {
            }
        },
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
    if (
        not isinstance(task_type, str)
        or not task_type
        or not isinstance(name, str)
    ):
        return None
    return task_type, name


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


def maa_task_queue_signature(queue: object) -> tuple[tuple, ...] | None:
    """Return the queue structure while ignoring each task's advanced settings."""

    if not isinstance(queue, list):
        return None

    signature = []
    for task in queue:
        identity = maa_task_identity(task)
        if identity is None:
            return None
        enabled = task.get("IsEnable", True)
        if enabled is not None and not isinstance(enabled, bool):
            return None
        signature.append((*identity, enabled))
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
            identity = maa_task_identity(task)
            if identity is not None:
                existing_tasks.setdefault(identity, task)

    structural_keys = {"$type", "Name", "IsEnable", "TaskType"}
    restored_queue = []
    for default_task in default_queue:
        task = deepcopy(default_task)
        identity = maa_task_identity(task)
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
    """Allow task-setting edits only when the queue structure is unchanged."""

    expected_signature = maa_task_queue_signature(expected)
    return (
        expected_signature is not None
        and maa_task_queue_signature(current) == expected_signature
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
