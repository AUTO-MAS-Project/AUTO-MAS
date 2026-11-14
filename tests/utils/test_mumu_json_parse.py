"""MuMu 命令输出的 JSON 解析容错。

MuMu 会把埋点与 C++ 日志混进同一份 stdout，对整段裸调 ``json.loads`` 会失败，
而其中那份设备 JSON 本身是完整可用的。这里只测纯解析逻辑，不起进程。
"""

import json

import pytest

from app.models.emulator import DeviceStatus
from app.utils import emulator as _utils_emulator

decode = _utils_emulator.mumu.MumuManager._decode_polluted_json
has_devices = _utils_emulator.mumu.MumuManager._has_device_entries
status_of = _utils_emulator.mumu.MumuManager._get_status_from_data

DEVICE_JSON = """{
    "0": {"index": 0, "name": "MuMu模拟器12", "is_android_started": true},
    "1": {"index": 1, "name": "MuMu模拟器12-1", "is_android_started": false}
}"""

# MuMu 自己的 C++ 日志写进了 stdout，跟在完整 JSON 后面
CPP_LOG_TAIL = (
    "\n[*** LOG ERROR #0001 ***] [2026-09-07 20:11:03] [mumu] {bad_weak_ptr}\n"
)

# MuMu 的埋点，出现在设备 JSON 之前，本身也是一段合法 JSON
TELEMETRY_HEAD = (
    'add record:{"_track_id":123456789,"event":"$SignUp",'
    '"properties":{"$lib":"cpp","index":"not-a-device"}}\n'
)


def test_device_payload_wins_over_telemetry():
    """埋点也是合法 JSON，不能因为它排在前面就把它当成设备信息返回。"""
    polluted = TELEMETRY_HEAD + DEVICE_JSON + CPP_LOG_TAIL
    result = decode(polluted, has_devices)
    assert result == json.loads(DEVICE_JSON)
    assert "_track_id" not in result


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
