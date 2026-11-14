"""MaaEnd 收尾 HDR 设置与阶段边界。"""

from types import SimpleNamespace

import pytest

from app.models.config import MaaEndConfig
from app.task.MaaEnd.AutoProxy import AutoProxyTask
from app.utils import MAAEND_RUN_MOOD_BOOK


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
