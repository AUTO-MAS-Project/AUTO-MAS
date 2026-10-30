"""MuMu control launch 返回 -503 时的重试编排。"""

import time
from unittest.mock import Mock

import pytest

from app.utils.common.emulator import mumu as mumu_module
from app.utils.common.emulator.mumu import MumuManager, _launch_errcode
from app.utils.common.process_runner import ProcessResult

CONNECT_FAILED = '{"errcode": -503, "errmsg": "mainnx connect failed"}'
LAUNCH_OK = '{"errcode": 0, "errmsg": ""}'
OTHER_ERROR = '{"errcode": -500, "errmsg": "nemu-api init failed"}'


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    monkeypatch.setattr(mumu_module, "logger", Mock())


def _manager() -> MumuManager:
    """只验证重试编排，绕开 __init__ 对真实 MuMuManager.exe 路径的校验。"""

    return object.__new__(MumuManager)


def _fake_launch(monkeypatch, *results: ProcessResult) -> list[str]:
    calls: list[str] = []

    async def fake(self, idx: str, package_name: str) -> ProcessResult:
        calls.append(idx)
        index = min(len(calls), len(results)) - 1
        return results[index]

    monkeypatch.setattr(MumuManager, "_launch", fake)
    # 退避间隔置 0：次数不变，但测试不真的睡
    monkeypatch.setattr(
        mumu_module,
        "LAUNCH_RETRY_DELAYS",
        tuple(0.0 for _ in mumu_module.LAUNCH_RETRY_DELAYS),
    )
    return calls


def test_launch_errcode_reads_mumu_json():
    result = ProcessResult(stdout=CONNECT_FAILED, stderr="", returncode=1)

    assert _launch_errcode(result) == -503


def test_launch_errcode_returns_none_for_unparsable_output():
    assert _launch_errcode(ProcessResult(stdout="", stderr="", returncode=1)) is None
    assert _launch_errcode(ProcessResult(stdout="boom", stderr="", returncode=1)) is None
    assert _launch_errcode(ProcessResult(stdout="[-503]", stderr="", returncode=1)) is None
    assert (
        _launch_errcode(ProcessResult(stdout='{"errcode": "-503"}', stderr="", returncode=1))
        is None
    )


@pytest.mark.asyncio
async def test_launch_retries_until_mainnx_answers(monkeypatch):
    manager = _manager()
    calls = _fake_launch(
        monkeypatch,
        ProcessResult(stdout=CONNECT_FAILED, stderr="", returncode=1),
        ProcessResult(stdout=LAUNCH_OK, stderr="", returncode=0),
    )

    result = await manager._launch_with_retry("0", "com.hypergryph.arknights")

    assert calls == ["0", "0"]
    assert result.returncode == 0


@pytest.mark.asyncio
async def test_launch_does_not_retry_unlisted_errcode(monkeypatch):
    manager = _manager()
    calls = _fake_launch(
        monkeypatch,
        ProcessResult(stdout=OTHER_ERROR, stderr="", returncode=1),
    )

    result = await manager._launch_with_retry("0", "")

    assert calls == ["0"]
    assert result.returncode == 1


@pytest.mark.asyncio
async def test_launch_gives_up_after_retry_schedule_exhausted(monkeypatch):
    manager = _manager()
    failure = ProcessResult(stdout=CONNECT_FAILED, stderr="", returncode=1)
    calls = _fake_launch(monkeypatch, *([failure] * 10))

    result = await manager._launch_with_retry("1", "")

    # 首启 1 次 + 退避表长度决定的若干次
    assert len(calls) == 1 + len(mumu_module.LAUNCH_RETRY_DELAYS)
    assert result.returncode == 1


@pytest.mark.asyncio
async def test_launch_stops_when_budget_is_too_small(monkeypatch):
    manager = _manager()
    failure = ProcessResult(stdout=CONNECT_FAILED, stderr="", returncode=1)
    calls = _fake_launch(monkeypatch, *([failure] * 10))

    result = await manager._launch_with_retry(
        "0", "", deadline=time.monotonic() + 5
    )

    # 预算不足以再走完一次 launch，直接放弃
    assert calls == ["0"]
    assert result.returncode == 1