#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""官方安装阶段的临时配置日志：先记原值再写盘，退出后或下轮启动时撤销。"""

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


def restore_maa_update_config(
    root: Path, *, snapshot_path: Path, script_id: str
) -> None:
    """仅在确认更新器已退出后调用；撤销安装覆盖，保留官方写回与用户修改。"""
    journal = _journal_path(snapshot_path)
    if not journal.exists():
        return
    try:
        _utils_io.restore_config_injection_journal(
            journal,
            root / "config/gui.new.json",
            identity={"script_id": script_id, "root": str(root.resolve())},
        )
    except (ValueError, OSError) as error:
        raise MaaUpdateUnsafeError(
            "MAA 安装配置恢复失败，已保留现场和恢复记录"
        ) from error
