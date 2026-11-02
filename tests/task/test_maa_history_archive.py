"""MAA 收尾归档保留原始失败截图并正常发送通知。"""

import importlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from app.core.history import HistoryStore
from app.models.task import LogRecord
from app.task.history_core import UserHistoryDependencies, save_user_history


@pytest.mark.asyncio
async def test_maa_finalizer_archives_original_without_system_temp(
    tmp_path, monkeypatch, isolated_app_paths
):
    monkeypatch.chdir(tmp_path)
    module = importlib.import_module("app.task.MAA.AutoProxy")
    monkeypatch.setattr(module.Notify, "push_statistics_report", AsyncMock())
    monkeypatch.setattr(module.System, "kill_process", AsyncMock())
    monkeypatch.setattr(module, "agree_bilibili", AsyncMock())
    monkeypatch.setattr(
        module.log_statistics, "parse_maa_statistics", lambda lines: ({}, False)
    )
    monkeypatch.setattr(
        module.log_statistics, "parse_cultivate_progress", lambda lines: []
    )
    shot = tmp_path / "upstream" / "debug" / "interface" / "failure_raw.png"
    shot.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), "red").save(shot)
    original = shot.read_bytes()
    now = datetime.now(timezone.utc)
    log = LogRecord(status="synthetic failure", content=["synthetic log"])
    user = SimpleNamespace(
        name="synthetic user",
        result="synthetic failure",
        status="running",
        log_record={now: log},
        iter_history_logs=lambda: [(now, log)],
    )
    storage = HistoryStore()
    await storage.initialize(video_limit_bytes=1024)
    saved, submitted = [], []
    failures, discarded = AsyncMock(), AsyncMock()

    async def record(item):
        submitted.append(item)
        result = await storage.record(item)
        saved.append(result)
        return result

    async def save(records, **kwargs):
        await save_user_history(
            records,
            dependencies=UserHistoryDependencies(
                record=record,
                collect_attachments=AsyncMock(return_value=[]),
                discard_capture=discarded,
                report_failure=failures,
                log_warning=kwargs["log_warning"],
            ),
        )

    task = SimpleNamespace(
        check_result="Pass",
        task_info=SimpleNamespace(
            begin_user_history_capture=Mock(),
            save_user_history=save,
        ),
        script_info=SimpleNamespace(name="MAA", current_index=0),
        cur_user_item=user,
        cur_user_config=SimpleNamespace(Info=SimpleNamespace(IfQuickConfig=False)),
        run_book={"Annihilation": False, "Routine": False},
        stopped_manually=False,
        maa_log_monitor=SimpleNamespace(stop=AsyncMock()),
        maa_process_manager=SimpleNamespace(kill=AsyncMock()),
        maa_exe_path=tmp_path / "synthetic.exe",
        _remember_pending_update=Mock(),
        _finish_cultivate_round=AsyncMock(),
        log_start_time=now,
        maa_tasks_path=tmp_path,
        _failure_shot=shot,
        script_config=SimpleNamespace(Run=SimpleNamespace(TaskTransitionMethod="None")),
        run_user_scripts_after=AsyncMock(),
        maa_root_path=None,
        user_start_time=now,
        _cultivate_achievement_summary=[],
        cur_user_uid="synthetic",
    )
    try:
        await module.AutoProxyTask.final_task(task)
        assert len(submitted) == len(saved) == 1
        assert submitted[0].attachments[0].path == shot
        assert submitted[0].attachments[0].archive_mode == "copy"
        assert shot.read_bytes() == original
        assert (
            storage.root / saved[0].attachments[0].relative_path
        ).read_bytes() == original
        assert not saved[0].storage_errors
        failures.assert_not_awaited()
        discarded.assert_awaited_once()
        module.Notify.push_statistics_report.assert_awaited_once()
    finally:
        await storage.close()
