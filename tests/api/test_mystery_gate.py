"""后端读取神秘入口解锁记录时的判据。

守的是：
- 记录缺失、日期不是今天、指纹与当前设备/源码不符时都按未解锁处理；
- 三项同时成立才算解锁，与入口页面使用同一套判据；
- 申请信息取不到时不影响进程，只按未解锁处理。

破坏方式：把任一条件改成或关系、或跳过指纹比对，下面的用例随即变红。
"""

import json

import pytest

import app.mystery.gate as gate
from app.mystery.access import MysteryContextError

DEVICE = "a" * 64
BACKEND = "b" * 64
FINGERPRINT = f"{DEVICE}:{BACKEND}"


@pytest.fixture
def record(isolated_app_paths, monkeypatch):
    """把配置目录指向临时目录，并按需写入解锁记录。"""
    gate_path = isolated_app_paths.config_path / gate.CONFIG_FILE_NAME

    def write(payload) -> None:
        gate_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            gate_path.write_text(payload, encoding="utf-8")
        else:
            gate_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

    monkeypatch.setattr(gate, "get_access_context", lambda: (DEVICE, BACKEND))
    return write


def _today() -> str:
    from datetime import datetime

    from app.utils import UTC8

    return datetime.now(UTC8).strftime("%Y-%m-%d")


def test_missing_record_means_locked(isolated_app_paths):
    """入口页面从未解锁时没有记录文件，门禁不得放行。"""
    assert gate.is_unlocked() is False


def test_today_record_unlocks(record):
    """日期与指纹同时对上才放行。"""
    record({"mysteryUnlockedDate": _today(), "mysteryUnlockedFingerprint": FINGERPRINT})
    assert gate.is_unlocked() is True


def test_other_day_locks_again(record):
    """跨日自动锁回，不依赖前端再写一次。"""
    record(
        {"mysteryUnlockedDate": "2000-01-01", "mysteryUnlockedFingerprint": FINGERPRINT}
    )
    assert gate.is_unlocked() is False


def test_other_fingerprint_locks_again(record):
    """换设备或源码变动后旧记录失效。"""
    record(
        {
            "mysteryUnlockedDate": _today(),
            "mysteryUnlockedFingerprint": f"{DEVICE}:{'c' * 64}",
        }
    )
    assert gate.is_unlocked() is False


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not-json",
        "[]",
        '{"mysteryUnlockedDate": 1, "mysteryUnlockedFingerprint": 2}',
    ],
)
def test_broken_record_means_locked(record, payload):
    """文件损坏或字段类型不符时按未解锁处理，不抛给调用方。"""
    record(payload)
    assert gate.is_unlocked() is False


def test_context_unavailable_means_locked(record, monkeypatch):
    """申请信息不可用时入口页面本身也进不去，门禁按未解锁处理。"""

    def broken() -> tuple[str, str]:
        raise MysteryContextError("DEVICE_UNAVAILABLE")

    record({"mysteryUnlockedDate": _today(), "mysteryUnlockedFingerprint": FINGERPRINT})
    monkeypatch.setattr(gate, "get_access_context", broken)
    assert gate.is_unlocked() is False
