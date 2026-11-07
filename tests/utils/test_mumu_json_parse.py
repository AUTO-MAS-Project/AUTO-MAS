"""MuMu 命令输出的 JSON 解析容错。

MuMu 会把埋点与 C++ 日志混进同一份 stdout，对整段裸调 ``json.loads`` 会失败，
而其中那份设备 JSON 本身是完整可用的。这里只测纯解析逻辑，不起进程。
"""

import json

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


def test_status_falls_back_to_player_state_when_android_flag_is_missing():
    """非管理员运行时 MuMu 打不开自己的内部管道，``is_android_started`` 恒为 false，
    只能靠实例状态判断，否则实例已经起来了还在一直等。"""
    assert (
        status_of(
            {
                "is_android_started": False,
                "is_process_started": True,
                "player_state": "start_finished",
            }
        )
        == DeviceStatus.ONLINE
    )


def test_status_starting_when_launch_reports_error():
    """启动命令自己报错（如 -32218 VERR_VIRTUALBOX_ACCESSDENIED）时实例状态同样是
    start_finished，这时不能当在线，否则会把没起来的实例报成已就绪。"""
    assert (
        status_of(
            {
                "is_android_started": False,
                "is_process_started": True,
                "player_state": "start_finished",
                "launch_err_code": -32218,
            }
        )
        == DeviceStatus.STARTING
    )


def test_status_starting_before_player_state_finishes():
    assert (
        status_of(
            {
                "is_android_started": False,
                "is_process_started": True,
                "player_state": "starting_rom",
            }
        )
        == DeviceStatus.STARTING
    )


def test_status_offline_ignores_leftover_player_state():
    assert (
        status_of(
            {
                "is_android_started": False,
                "is_process_started": False,
                "player_state": "start_finished",
            }
        )
        == DeviceStatus.OFFLINE
    )
