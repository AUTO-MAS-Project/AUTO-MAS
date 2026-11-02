"""MaaEnd 收尾 HDR 设置与阶段边界。"""

from types import SimpleNamespace

import pytest

from app.models.config import MaaEndConfig
from app.task.MaaEnd.AutoProxy import AutoProxyTask
from app.utils import MAAEND_RUN_MOOD_BOOK


@pytest.mark.parametrize("hdr", ["Enable", "Disable"])
def test_hdr_restore_without_resolution(hdr):
    stages = list(MAAEND_RUN_MOOD_BOOK)
    task = SimpleNamespace(
        script_config=SimpleNamespace(
            Game=MaaEndConfig.GameFields(
                RestoreAutoHDR=hdr,
                RestoreResolution="Off",
                CloseOnFinish=True,
            )
        ),
        emulator_manager=None,
        mode=stages[-1],
        run_book={stage: False for stage in stages},
        _maaend_task_supported=lambda name: True,
        _maaend_task_option_supported=lambda task, option: True,
    )
    tasks = []
    result = AutoProxyTask._configure_resolution_restore(task, tasks)
    assert result is tasks[-1]
    assert result["optionValues"]["CloseGamePCAutoHDR"]["caseName"] == hdr
    assert result["optionValues"]["CloseGamePCApplyGameSetting"]["value"] is True
    assert "CloseGamePCGameSettingResolution" not in result["optionValues"]

    task.mode = stages[0]
    if len(stages) > 1:
        assert AutoProxyTask._configure_resolution_restore(task, tasks) is None
        assert result["optionValues"]["CloseGamePCApplyGameSetting"]["value"] is False

    task.mode = stages[-1]
    task.script_config.Game.CloseOnFinish = False
    assert AutoProxyTask._configure_resolution_restore(task, []) is None


def test_hdr_restore_rejects_unsupported_version():
    stages = list(MAAEND_RUN_MOOD_BOOK)
    task = SimpleNamespace(
        script_config=SimpleNamespace(
            Game=MaaEndConfig.GameFields(
                RestoreAutoHDR="Enable",
                CloseOnFinish=True,
            )
        ),
        emulator_manager=None,
        mode=stages[-1],
        run_book={stage: False for stage in stages},
        _maaend_task_supported=lambda name: True,
        _maaend_task_option_supported=lambda task, option: (
            option != "CloseGamePCAutoHDR"
        ),
    )
    with pytest.raises(ValueError, match="更新 MaaEnd"):
        AutoProxyTask._configure_resolution_restore(task, [])
