"""MaaEnd 关闭更新接管后的外部更新恢复边界。"""

import json
import threading
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import script_install
from app.task.MaaEnd.tools import script_update
from app.task.MaaEnd.tools.managed_recovery import MaaEndInstallAdapter


def write_completed_transaction(
    root: Path,
    *,
    phase: str = "installed",
    files: dict[str, str] | None = None,
    with_previous: bool = True,
) -> Path:
    directory = script_install.workspace(root)
    directory.mkdir(parents=True, exist_ok=True)
    if with_previous:
        previous = directory / "previous"
        previous.mkdir(parents=True)
        (previous / "old-program.exe").write_bytes(b"old")
    state = {
        "root": str(root.resolve()),
        "phase": phase,
        "files": files or {"program.exe": "0" * 64},
    }
    (directory / "transaction.json").write_text(json.dumps(state))
    return directory


@pytest.mark.asyncio
async def test_completed_external_update_archives_workspace_without_touching_it(
    tmp_path, monkeypatch
):
    root = tmp_path / "MaaEnd"
    root.mkdir()
    (root / "program.exe").write_bytes(b"external-update")
    directory = write_completed_transaction(root)
    transaction = (directory / "transaction.json").read_bytes()
    previous = (directory / "previous" / "old-program.exe").read_bytes()
    monkeypatch.setattr(script_update, "assert_idle", lambda root: None)
    verify = AsyncMock()
    monkeypatch.setattr(script_update, "verify_current_install_integrity", verify)
    adapter = MaaEndInstallAdapter(root, Mock(), takeover_enabled=False)

    archived = await adapter.archive_completed_external_update()

    assert archived is not None
    assert not directory.exists()
    assert archived.name.startswith(f"{directory.name}-archived-")
    assert (archived / "transaction.json").read_bytes() == transaction
    assert (archived / "previous" / "old-program.exe").read_bytes() == previous
    assert (root / "program.exe").read_bytes() == b"external-update"
    verify.assert_awaited_once_with(root)


@pytest.mark.asyncio
async def test_completed_external_update_can_archive_after_backup_cleanup(
    tmp_path, monkeypatch
):
    root = tmp_path / "MaaEnd"
    root.mkdir()
    (root / "program.exe").write_bytes(b"external-update")
    directory = write_completed_transaction(root, with_previous=False)
    monkeypatch.setattr(script_update, "assert_idle", lambda root: None)
    monkeypatch.setattr(script_update, "verify_current_install_integrity", AsyncMock())
    adapter = MaaEndInstallAdapter(root, Mock(), takeover_enabled=False)

    archived = await adapter.archive_completed_external_update()

    assert archived is not None
    assert not directory.exists()
    assert (archived / "transaction.json").is_file()
    assert not (archived / "previous").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["takeover", "interrupted", "ready", "matching"])
async def test_external_update_archive_rejects_any_unproven_state(
    tmp_path, monkeypatch, condition
):
    root = tmp_path / "MaaEnd"
    root.mkdir()
    (root / "program.exe").write_bytes(b"external-update")
    files = (
        script_install.tree_hashes(root, threading.Event())
        if condition == "matching"
        else None
    )
    directory = write_completed_transaction(
        root,
        phase="installing" if condition == "interrupted" else "installed",
        files=files,
    )
    if condition == "ready":
        (directory / "ready").mkdir()
    monkeypatch.setattr(script_update, "assert_idle", lambda root: None)
    verify = AsyncMock()
    monkeypatch.setattr(script_update, "verify_current_install_integrity", verify)
    adapter = MaaEndInstallAdapter(
        root, Mock(), takeover_enabled=condition == "takeover"
    )

    assert await adapter.archive_completed_external_update() is None
    assert directory.exists()
    assert (directory / "transaction.json").is_file()


@pytest.mark.asyncio
async def test_external_update_archive_propagates_integrity_failure(
    tmp_path, monkeypatch
):
    root = tmp_path / "MaaEnd"
    root.mkdir()
    (root / "program.exe").write_bytes(b"partial")
    directory = write_completed_transaction(root)
    monkeypatch.setattr(script_update, "assert_idle", lambda root: None)
    verify = AsyncMock(
        side_effect=script_install.InstallUnsafeError("安装完整性未确认")
    )
    monkeypatch.setattr(script_update, "verify_current_install_integrity", verify)
    adapter = MaaEndInstallAdapter(root, Mock(), takeover_enabled=False)

    with pytest.raises(script_install.InstallUnsafeError, match="完整性未确认"):
        await adapter.archive_completed_external_update()

    assert directory.exists()
    assert (directory / "transaction.json").is_file()
