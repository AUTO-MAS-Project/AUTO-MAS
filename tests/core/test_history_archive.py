"""历史附件的文件所有权、故障恢复和取消边界。"""

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import app.core.history as history_module
from app.models.schema import HistoryAttachmentInput, HistoryWrite
from app.task.history_core import UserHistoryDependencies, save_user_history
from tests.support.history import store as store


def record_for(path, mode="move", *, kind="image"):
    return HistoryWrite(
        time=datetime.now(timezone.utc),
        username="synthetic-user",
        script_name="synthetic-script",
        status="error",
        message="synthetic failure",
        logs="synthetic log",
        attachments=[
            HistoryAttachmentInput(
                path=path,
                kind=kind,
                role="failure_screenshot",
                display_name="screenshot",
                archive_mode=mode,
            )
        ],
    )


@pytest.mark.asyncio
async def test_cross_drive_fallback_is_success_and_retains_diagnostic(
    store, tmp_path, monkeypatch
):
    source = tmp_path / "temporary.png"
    source.write_bytes(b"original bytes")
    rename = Path.rename

    def cross_drive(path, target):
        if path == source:
            raise OSError(0, "cross-drive move", str(source), 17)
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", cross_drive)
    failures = AsyncMock()
    discarded = AsyncMock()
    warnings = []
    saved = []

    async def save(record):
        result = await store.record(record)
        saved.append(result)
        return result

    await save_user_history(
        [record_for(source)],
        dependencies=UserHistoryDependencies(
            record=save,
            collect_attachments=AsyncMock(return_value=[]),
            discard_capture=discarded,
            report_failure=failures,
            log_warning=warnings.append,
        ),
    )
    failures.assert_not_awaited()
    discarded.assert_awaited_once()
    assert not warnings
    result = saved[0]
    assert result.attachments[0].available
    assert result.attachments[0].saved_via == "copy"
    assert len(result.storage_errors) == 1
    assert result.storage_errors[0].stage == "move"
    assert result.storage_errors[0].recovered
    detail = await store.get_detail(record_id=result.id)
    assert detail.storage_errors[0].recovered
    assert (
        store.root / detail.attachments[0].relative_path
    ).read_bytes() == source.read_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,fault",
    [
        ("copy", None),
        ("move", None),
        *[("copy", fault) for fault in ("read", "write", "fsync", "rename")],
    ],
)
async def test_attachment_archive_preserves_content_and_reports_incomplete_writes(
    store, tmp_path, monkeypatch, mode, fault
):
    source = tmp_path / "original.png"
    source.write_bytes(b"keep original")
    open_file, rename, fsync = Path.open, Path.rename, os.fsync

    def broken_open(path, mode="r", *args, **kwargs):
        if (fault == "read" and path == source and mode == "rb") or (
            fault == "write" and path.name.endswith(".temp") and mode == "xb"
        ):
            raise OSError("injected copy failure")
        return open_file(path, mode, *args, **kwargs)

    def broken_rename(path, target):
        if fault == "rename" and path.name.endswith(".temp"):
            raise OSError("injected rename failure")
        return rename(path, target)

    def broken_fsync(fd):
        if fault == "fsync":
            raise OSError("injected flush failure")
        return fsync(fd)

    with monkeypatch.context() as filesystem:
        filesystem.setattr(Path, "open", broken_open)
        filesystem.setattr(Path, "rename", broken_rename)
        filesystem.setattr(os, "fsync", broken_fsync)
        if fault is not None:
            with pytest.raises(history_module.HistorySaveError) as raised:
                await store.record(record_for(source, mode))
            error = raised.value
            assert error.record_saved
            assert any(
                issue.stage == "copy" and not issue.recovered for issue in error.errors
            )
            assert not any(issue.stage == "move" for issue in error.errors)
            record_id = error.record_id
        else:
            result = await store.record(record_for(source, mode))
            assert result.attachments[0].available
            assert result.attachments[0].saved_via == mode
            assert not result.storage_errors
            record_id = result.id
    detail = await store.get_detail(record_id=record_id)
    if fault is not None:
        assert not detail.attachments[0].available
        assert source.read_bytes() == b"keep original"
    else:
        assert detail.attachments[0].available
        assert not detail.storage_errors
        assert source.exists() == (mode == "copy")
        assert (
            store.root / detail.attachments[0].relative_path
        ).read_bytes() == b"keep original"
    assert not list(store.root.rglob("*.temp"))
