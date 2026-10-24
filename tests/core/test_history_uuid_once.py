"""一次性验证历史 UUID 改造；按仓库约定仅留本地，不提交。"""

import asyncio
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.history import HistorySaveError, HistoryStore
from app.models.schema import HistoryAttachmentInput, HistoryWrite


def test_legacy_history_cleanup_runs_during_config_upgrade(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.core.config import _clear_legacy_history

    for directory in (tmp_path / "history", tmp_path / "data" / "replays"):
        directory.mkdir(parents=True)
        (directory / "old.txt").write_text("old", encoding="utf-8")
    (tmp_path / "data" / "history-storage.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "history.db").write_bytes(b"legacy database")

    _clear_legacy_history()

    assert not (tmp_path / "history").exists()
    assert not (tmp_path / "data" / "replays").exists()
    assert not (tmp_path / "data" / "history-storage.json").exists()
    assert not (tmp_path / "data" / "history.db").exists()


def test_history_uuid_save_failure_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def verify():
        store = HistoryStore()
        await store.initialize(video_limit_bytes=1024 * 1024)
        try:
            with sqlite3.connect(store.database) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                assert "sequences" not in tables
                assert "pending_files" not in tables

            source = tmp_path / "attachment.txt"
            source.write_text("attachment", encoding="utf-8")
            record = await store.record(
                HistoryWrite(
                    time=datetime.now(timezone.utc),
                    username="tester",
                    script_name="local",
                    status="success",
                    message="saved",
                    logs="log text",
                    attachments=[
                        HistoryAttachmentInput(
                            path=source,
                            kind="diagnostic",
                            role="evidence",
                            display_name=source.name,
                        )
                    ],
                )
            )
            assert isinstance(record.id, uuid.UUID)
            attachment = record.attachments[0]
            assert isinstance(attachment.id, uuid.UUID)
            assert attachment.record_id == record.id
            assert attachment.relative_path.split("/")[1] == str(record.id)
            assert (store.root / attachment.relative_path).is_file()
            assert (await store.get_detail(record_id=record.id)).id == record.id

            copy_source = tmp_path / "copy.txt"
            copy_source.write_text("copied", encoding="utf-8")
            original_rename = Path.rename

            def reject_source_move(path, target):
                if path == copy_source:
                    raise PermissionError("forced move failure")
                return original_rename(path, target)

            with pytest.raises(HistorySaveError) as captured:
                with patch.object(Path, "rename", reject_source_move):
                    await store.record(
                        HistoryWrite(
                            time=datetime.now(timezone.utc),
                            username="tester",
                            script_name="local",
                            status="success",
                            message="copied",
                            logs="copy log",
                            attachments=[
                                HistoryAttachmentInput(
                                    path=copy_source,
                                    kind="diagnostic",
                                    role="evidence",
                                    display_name=copy_source.name,
                                )
                            ],
                        )
                    )
            assert captured.value.record_saved
            copied = await store.get_detail(record_id=captured.value.record_id)
            assert copied.attachments[0].saved_via == "copy"
            assert any(issue.recovered for issue in copied.storage_errors)

            with pytest.raises(HistorySaveError) as captured:
                await store.record(
                    HistoryWrite(
                        time=datetime.now(timezone.utc),
                        username="tester",
                        script_name="local",
                        status="error",
                        message="missing attachment",
                        logs="fallback log",
                        attachments=[
                            HistoryAttachmentInput(
                                path=tmp_path / "missing.txt",
                                kind="diagnostic",
                                role="evidence",
                                display_name="missing.txt",
                            )
                        ],
                    )
                )
            assert captured.value.record_saved
            missing = await store.get_detail(record_id=captured.value.record_id)
            assert missing.storage_error_count >= 2
            assert not missing.attachments[0].available

            snapshot = await store.export_snapshot(destination=tmp_path / "snapshot")
            assert snapshot.database.is_file()
            assert (snapshot.history / attachment.relative_path).is_file()
        finally:
            await store.close()

    asyncio.run(verify())
