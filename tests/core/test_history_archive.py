"""历史附件的文件所有权、故障恢复和取消边界。"""

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

import app.core.history as history_module
from app.models.schema import HistoryAttachmentInput, HistoryWrite
from app.task.history_core import UserHistoryDependencies, save_user_history


@pytest_asyncio.fixture
async def store(isolated_app_paths):
    storage = history_module.HistoryStore()
    await storage.initialize(video_limit_bytes=1024 * 1024)
    try:
        yield storage
    finally:
        await storage.close()


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
@pytest.mark.parametrize("mode", ["copy", "move"])
async def test_archive_ownership_and_persisted_content(store, tmp_path, mode):
    source = tmp_path / "source.png"
    source.write_bytes(b"synthetic image payload")
    result = await store.record(record_for(source, mode))
    attachment = result.attachments[0]
    assert attachment.available and attachment.saved_via == mode
    assert not result.storage_errors
    assert source.exists() == (mode == "copy")
    assert (
        store.root / attachment.relative_path
    ).read_bytes() == b"synthetic image payload"
    detail = await store.get_detail(record_id=result.id)
    assert detail.attachments[0].available
    assert not detail.storage_errors
    assert not list(store.root.rglob("*.temp"))


@pytest.mark.asyncio
async def test_copy_never_attempts_to_move_original(store, tmp_path, monkeypatch):
    source = tmp_path / "upstream.png"
    source.write_bytes(b"upstream data")
    rename = Path.rename

    def forbid_source_move(path, target):
        assert path != source, "copy archival must not move upstream files"
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", forbid_source_move)
    result = await store.record(record_for(source, "copy"))
    assert source.read_bytes() == b"upstream data"
    assert result.attachments[0].saved_via == "copy"


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
@pytest.mark.parametrize("fault", ["read", "write", "fsync", "rename"])
async def test_copy_failure_preserves_source_and_reports_failure(
    store, tmp_path, monkeypatch, fault
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

    monkeypatch.setattr(Path, "open", broken_open)
    monkeypatch.setattr(Path, "rename", broken_rename)
    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(history_module.HistorySaveError) as raised:
        await store.record(record_for(source, "copy"))
    error = raised.value
    assert error.record_saved
    assert any(issue.stage == "copy" and not issue.recovered for issue in error.errors)
    assert not any(issue.stage == "move" for issue in error.errors)
    monkeypatch.setattr(Path, "open", open_file)
    detail = await store.get_detail(record_id=error.record_id)
    assert not detail.attachments[0].available
    assert source.read_bytes() == b"keep original"
    assert not list(store.root.rglob("*.temp"))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["copy", "move"])
async def test_missing_source_still_fails(store, tmp_path, mode):
    with pytest.raises(history_module.HistorySaveError) as raised:
        await store.record(record_for(tmp_path / "missing.png", mode))
    assert raised.value.record_saved
    assert any(not issue.recovered for issue in raised.value.errors)


@pytest.mark.asyncio
async def test_cancelled_copy_cleans_partial_file(store, tmp_path, monkeypatch):
    source = tmp_path / "original.png"
    source.write_bytes(b"original data")
    cancel = threading.Event()
    fsync = os.fsync

    def cancel_after_flush(fd):
        fsync(fd)
        cancel.set()

    monkeypatch.setattr(os, "fsync", cancel_after_flush)
    with pytest.raises(history_module.HistorySaveError) as raised:
        store._save(record_for(source, "copy"), cancel)
    assert not raised.value.record_saved
    assert source.exists()
    assert not list(store.root.rglob("*.temp"))
    assert not list(store.root.rglob("1.png"))


@pytest.mark.asyncio
async def test_copy_respects_video_quota(store, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"large video")
    store._video_limit = 1
    with pytest.raises(history_module.HistorySaveError) as raised:
        await store.record(record_for(source, "copy", kind="video"))
    assert any(issue.stage == "quota" for issue in raised.value.errors)
    assert source.read_bytes() == b"large video"


@pytest.mark.asyncio
async def test_unrecovered_error_still_notifies_and_cleans_up(store, tmp_path):
    failures, discarded = AsyncMock(), AsyncMock()
    warnings = []
    await save_user_history(
        [record_for(tmp_path / "missing.png", "copy")],
        dependencies=UserHistoryDependencies(
            record=store.record,
            collect_attachments=AsyncMock(return_value=[]),
            discard_capture=discarded,
            report_failure=failures,
            log_warning=warnings.append,
        ),
    )
    failures.assert_awaited_once()
    discarded.assert_awaited_once()
    assert len(warnings) == 1
