#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""官方安装阶段的临时配置日志：先记原值再写盘，退出后或下轮启动时撤销。"""

from copy import deepcopy
from pathlib import Path

from app.utils import io as _utils_io

from .update_errors import MaaUpdateUnsafeError


def _journal_path(snapshot_path: Path) -> Path:
    return snapshot_path.with_name(f"{snapshot_path.name}.maa-update.json")


def write_maa_update_config(
    root: Path, config: dict, *, snapshot_path: Path, script_id: str
) -> None:
    """先保存安装配置修改的归属与原值，再原子写入；中途退出也可恢复。"""
    journal = _journal_path(snapshot_path)
    if journal.exists():
        raise MaaUpdateUnsafeError("上次 MAA 安装配置尚未恢复，请重新运行后重试")
    original = _utils_io.read_dict_file(root / "config/gui.new.json")
    _utils_io.write_file(
        journal,
        {
            "script_id": script_id,
            "root": str(root.resolve()),
            "original": original,
            "injected": config,
        },
    )
    _utils_io.write_file(root / "config/gui.new.json", config)


def _restore_values(current: dict, original: dict, injected: dict) -> None:
    """按注入前后差异撤销仍由 MAS 持有的值；未知修改不覆盖。"""
    missing = object()
    for key in original.keys() | injected.keys():
        before = original.get(key, missing)
        after = injected.get(key, missing)
        if before == after:
            continue
        actual = current.get(key, missing)
        if (
            isinstance(actual, dict)
            and isinstance(after, dict)
            and (before is missing or isinstance(before, dict))
        ):
            _restore_values(actual, {} if before is missing else before, after)
            if before is missing and not actual:
                current.pop(key, None)
        elif actual == after:
            if before is missing:
                current.pop(key, None)
            else:
                current[key] = deepcopy(before)


def restore_maa_update_config(
    root: Path, *, snapshot_path: Path, script_id: str
) -> None:
    """仅在确认更新器已退出后调用；撤销安装覆盖，保留官方写回与用户修改。"""
    journal = _journal_path(snapshot_path)
    if not journal.exists():
        return
    state = _utils_io.read_dict_file(journal)
    if (
        state.get("script_id") != script_id
        or state.get("root") != str(root.resolve())
        or not isinstance(state.get("original"), dict)
        or not isinstance(state.get("injected"), dict)
    ):
        raise MaaUpdateUnsafeError("MAA 安装配置恢复记录无效，已保留现场和恢复记录")
    path = root / "config/gui.new.json"
    current = _utils_io.read_dict_file(path)
    restored = deepcopy(current)
    _restore_values(restored, state["original"], state["injected"])
    if restored != current:
        _utils_io.write_file(path, restored)
    # 写回成功才移除日志；崩溃后重复恢复是幂等的。
    journal.unlink()
