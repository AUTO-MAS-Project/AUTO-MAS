"""养成执行目标和培养进展通知的回归验证。"""

import asyncio
import importlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core import Notify
from app.task.MAA.AutoProxy import AutoProxyTask, _build_auto_cultivate_task
from app.task.MAA.tools.cultivate.engine import select_auto_cultivate_targets
from app.task.MAA.tools.cultivate.types import (
    CultivateDataSet,
    Goal,
    OperatorTarget,
    Progression,
    ProgressionSnapshot,
)


@pytest.mark.parametrize(("level", "expected"), [(7, 0), (6, 7), (None, None)])
def test_mastery_plan_only_requests_missing_skill_prerequisite(level, expected):
    original = OperatorTarget("one", (Goal("mastery", "skill", 3),))
    snapshot = ProgressionSnapshot(
        source="skland",
        timestamp=1,
        data=Progression(
            elite=2, level=90, masteries={}, modules={}, skill_level=level
        ),
    )
    targets = select_auto_cultivate_targets(
        targets=(original,),
        snapshots={"one": snapshot},
        inventory={},
        data=CultivateDataSet(
            demands={}, drops=(), stages={}, recipes=(), material_class={}
        ),
    )
    if expected is None:
        assert targets == ()
        return
    task = _build_auto_cultivate_task(
        targets=targets,
        catalog=[
            {
                "value": "one",
                "label": "干员",
                "profession": "warrior",
                "skills": [{"value": "skill", "skillIndex": 2}],
            }
        ],
        source_task=None,
    )
    assert task["Plans"][0]["SkillLevel"] == expected
    assert task["Plans"][0]["SkillMastery"] == [0, 3, 0]
    assert original.goals == (Goal("mastery", "skill", 3),)


@pytest.fixture
def finalizer(monkeypatch, tmp_path):
    module = importlib.import_module("app.task.MAA.AutoProxy")
    monkeypatch.setattr(module.System, "kill_process", AsyncMock())
    monkeypatch.setattr(module, "agree_bilibili", AsyncMock())
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(module.Notify, "push_statistics_report", AsyncMock())
    monkeypatch.setattr(module.Notify, "send_notice", AsyncMock())
    return SimpleNamespace(
        check_result="Pass",
        user_start_time=now,
        log_start_time=now,
        cur_user_uid="user",
        cur_user_item=SimpleNamespace(
            name="user", log_record={}, iter_history_logs=lambda: [], result="failed"
        ),
        cur_user_config=SimpleNamespace(
            Info=SimpleNamespace(IfQuickConfig=True, RemainedDay=-1),
            Task=SimpleNamespace(IfCultivate=True, CultivateTargets="[]"),
            Data=SimpleNamespace(ProxyTimes=0),
            commit=AsyncMock(),
        ),
        task_info=SimpleNamespace(
            begin_user_history_capture=Mock(),
            save_user_history=AsyncMock(),
        ),
        script_info=SimpleNamespace(name="MAA", current_index=0),
        run_book={"Annihilation": True, "Routine": True},
        stopped_manually=False,
        maa_log_monitor=SimpleNamespace(stop=AsyncMock()),
        maa_process_manager=SimpleNamespace(kill=AsyncMock()),
        maa_exe_path=tmp_path / "maa.exe",
        maa_tasks_path=tmp_path,
        maa_root_path=None,
        _remember_pending_update=Mock(),
        _finish_cultivate_round=AsyncMock(),
        _failure_shot=None,
        _take_failure_shot=AsyncMock(return_value=None),
        script_config=SimpleNamespace(Run=SimpleNamespace(TaskTransitionMethod="None")),
        run_user_scripts_after=AsyncMock(),
        _cultivate_achievement_summary=[],
        _cultivate_progress_synced=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("synced", [True, False])
async def test_report_counts_saved_targets_after_final_refresh(finalizer, synced):
    async def refresh():
        finalizer._cultivate_progress_synced = synced
        finalizer.cur_user_config.Task.CultivateTargets = json.dumps(
            [
                {
                    "operator_id": "one",
                    "goals": [
                        {
                            "kind": "mastery",
                            "target_id": "s",
                            "to_level": 3,
                            "state": "pending_confirm",
                        }
                    ],
                },
                {
                    "operator_id": "two",
                    "goals": [
                        {"kind": "module", "target_id": "m", "to_level": 3},
                        {"kind": "elite", "to_level": 2},
                    ],
                },
            ]
        )

    finalizer._finish_cultivate_round = refresh
    await AutoProxyTask.final_task(finalizer)
    sender = Notify.push_statistics_report
    sender.assert_awaited_once()
    payload = sender.await_args.kwargs["payload"]
    assert "培养进展: 剩余：2 名干员，3 个目标" in payload.text
    assert ("练度未同步" in payload.text) is (not synced)
    assert "剩余：2 名干员，3 个目标" in payload.html.resolve()


@pytest.mark.asyncio
async def test_count_alone_does_not_trigger_report(finalizer):
    finalizer.run_book = {"Annihilation": False, "Routine": False}
    await AutoProxyTask.final_task(finalizer)
    Notify.push_statistics_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_cultivation_does_not_add_counts(finalizer):
    finalizer.cur_user_config.Task.IfCultivate = False
    await AutoProxyTask.final_task(finalizer)
    payload = Notify.push_statistics_report.await_args.kwargs["payload"]
    assert "剩余：" not in payload.text


@pytest.mark.asyncio
async def test_completed_plan_reports_zero(finalizer):
    finalizer._cultivate_progress_synced = False
    await AutoProxyTask.final_task(finalizer)
    payload = Notify.push_statistics_report.await_args.kwargs["payload"]
    assert "剩余：0 名干员，0 个目标" in payload.text
    assert "练度未同步" not in payload.text


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, "success", "cancel", "local"])
async def test_progress_refresh_preserves_targets_until_confirmed(
    monkeypatch, tmp_path, result
):
    module = importlib.import_module("app.task.MAA.AutoProxy")
    raw = '[{"operator_id":"one","goals":[{"kind":"skill","to_level":7}]}]'
    bound = "" if result == "local" else "bound"
    config = SimpleNamespace(
        Task=SimpleNamespace(
            CultivateTargets=raw, CultivateSklandAccount=bound, CultivateSklandUid=bound
        ),
        commit=AsyncMock(),
    )
    task = SimpleNamespace(
        _cultivate_auto_raise_injected=True,
        _cultivate_collected_depot=False,
        _cultivate_collected_oper_box=False,
        _cultivate_progress_synced=True,
        cur_user_config=config,
        script_info=SimpleNamespace(script_id="script"),
        cur_user_uid="user",
        cur_user_item=SimpleNamespace(name="user"),
        _cultivate_archive_dir=lambda: tmp_path,
        _set_cultivate_notice=AsyncMock(),
        _cultivate_achievement_summary=[],
    )
    progression = Progression(
        elite=2, level=90, masteries={}, modules={}, skill_level=7
    )
    fetch = AsyncMock(
        return_value=({"one": progression}, 1) if result == "success" else None
    )
    if result == "cancel":
        fetch.side_effect = asyncio.CancelledError
    monkeypatch.setattr(module.maa_api, "get_cultivate_skland_progression", fetch)
    monkeypatch.setattr(module, "load_oper_box_names", lambda _: {"one": "干员"})
    if result == "local":
        resolver = Mock()
        monkeypatch.setattr(module, "resolve_progression", resolver)
    if result == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await AutoProxyTask._finish_cultivate_round(task)
        assert task._cultivate_auto_raise_injected is True
    else:
        await AutoProxyTask._finish_cultivate_round(task)
    if result == "local":
        resolver.assert_not_called()
    assert task._cultivate_progress_synced is (result == "success")
    assert json.loads(config.Task.CultivateTargets) == (
        [] if result == "success" else json.loads(raw)
    )
