"""MuMu 命令输出的 JSON 解析容错。

MuMu 会把埋点与 C++ 日志混进同一份 stdout，对整段裸调 ``json.loads`` 会失败，
而其中那份设备 JSON 本身是完整可用的。这里只测纯解析逻辑，不起进程。
"""

import json
from pathlib import Path

import pytest

from app.utils import emulator as _utils_emulator

decode = _utils_emulator.mumu.MumuManager._decode_polluted_json
has_devices = _utils_emulator.mumu.MumuManager._has_device_entries
_errcode = _utils_emulator.mumu._errcode
_low_integrity_hint = _utils_emulator.mumu._low_integrity_hint

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


def test_errcode_reads_mainnx_failure():
    assert _errcode('{"errcode": -503, "errmsg": "mainnx connect failed"}') == -503


def test_errcode_absent_returns_none():
    assert _errcode("no json here") is None


def test_low_integrity_hint_ignores_other_errcodes():
    """只有 -503 才谈安装目录的完整性标签，别的失败码不往这上面归因。"""
    assert (
        _low_integrity_hint(Path("C:/nonexistent/MuMuManager.exe"), '{"errcode": -100}')
        == ""
    )


def test_low_integrity_hint_skips_path_without_low_label(tmp_path):
    """目录没有低完整性标签时不多说一句，免得把无关的 -503 也引到改标签上。"""
    exe = tmp_path / "nx_main" / "MuMuManager.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    assert _low_integrity_hint(exe, '{"errcode": -503}') == ""
