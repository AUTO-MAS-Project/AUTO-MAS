"""MuMu 命令输出的 JSON 解析容错。

MuMu 会把埋点与 C++ 日志混进同一份 stdout，对整段裸调 ``json.loads`` 会失败，
而其中那份设备 JSON 本身是完整可用的。这里只测纯解析逻辑，不起进程。
"""

import json

import pytest

from app.utils.emulator.mumu import MumuManager

decode = MumuManager._decode_polluted_json
has_devices = MumuManager._has_device_entries

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


def test_clean_json_unchanged():
    assert decode(DEVICE_JSON, has_devices) == json.loads(DEVICE_JSON)


def test_trailing_cpp_log_is_ignored():
    """对应 Sentry 的 `Extra data: line 12 column 1`。"""
    assert decode(DEVICE_JSON + CPP_LOG_TAIL, has_devices) == json.loads(DEVICE_JSON)


def test_leading_telemetry_is_ignored():
    """对应 Sentry 的 `Expecting value: line 1 column 1`。"""
    assert decode(TELEMETRY_HEAD + DEVICE_JSON, has_devices) == json.loads(DEVICE_JSON)


def test_device_payload_wins_over_telemetry():
    """埋点也是合法 JSON，不能因为它排在前面就把它当成设备信息返回。"""
    polluted = TELEMETRY_HEAD + DEVICE_JSON + CPP_LOG_TAIL
    result = decode(polluted, has_devices)
    assert result == json.loads(DEVICE_JSON)
    assert "_track_id" not in result


def test_single_device_payload():
    single = '{"index": 2, "name": "MuMu模拟器12-2", "is_android_started": true}'
    assert decode(TELEMETRY_HEAD + single, has_devices) == json.loads(single)


def test_falls_back_to_first_value_when_nothing_preferred():
    """没有任何候选命中 prefer 时退回第一个，而不是直接报错。"""
    payload = '{"state": "running"}'
    assert decode(payload, has_devices) == {"state": "running"}


def test_prefer_none_takes_first_value():
    assert decode(TELEMETRY_HEAD + DEVICE_JSON) == json.loads(
        TELEMETRY_HEAD[len("add record:") :]
    )


def test_no_json_at_all_raises():
    with pytest.raises(json.JSONDecodeError):
        decode("[*** LOG ERROR #0001 ***] mumu failed to start\n", has_devices)


def test_empty_output_raises():
    with pytest.raises(json.JSONDecodeError):
        decode("", has_devices)
