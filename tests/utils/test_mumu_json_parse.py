"""MuMu 设备状态字段的解析。"""

import pytest

from app.models.emulator import DeviceStatus
from app.utils import emulator as _utils_emulator

status_of = _utils_emulator.mumu.MumuManager._get_status_from_data


@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            {
                "is_android_started": False,
                "is_process_started": True,
                "player_state": "start_finished",
            },
            DeviceStatus.ONLINE,
        ),
        (
            {
                "is_android_started": False,
                "is_process_started": True,
                "player_state": "start_finished",
                "launch_err_code": -32218,
            },
            DeviceStatus.STARTING,
        ),
        (
            {
                "is_android_started": False,
                "is_process_started": True,
                "player_state": "starting_rom",
            },
            DeviceStatus.STARTING,
        ),
        (
            {
                "is_android_started": False,
                "is_process_started": False,
                "player_state": "start_finished",
            },
            DeviceStatus.OFFLINE,
        ),
    ],
)
def test_status_respects_player_state_and_launch_failure(payload, expected):
    """非管理员启动靠 player_state 判就绪，但启动错误和陈旧状态不能冒充在线。"""
    assert status_of(payload) == expected
