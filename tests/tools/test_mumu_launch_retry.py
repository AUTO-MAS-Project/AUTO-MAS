"""MuMu control launch 返回 -503 时的重试编排。"""

from unittest.mock import Mock

import pytest

from app.utils.common.emulator import mumu as mumu_module
from app.utils.common.emulator.mumu import MumuManager, _launch_errcode
from app.utils.common.process_runner import ProcessResult

CONNECT_FAILED = '{"errcode": -503, "errmsg": "mainnx connect failed"}'
LAUNCH_OK = '{"errcode": 0, "errmsg": ""}'


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
    monkeypatch.setattr(mumu_module, "LAUNCH_RETRY_DELAY_SECONDS", 0)
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
async def test_launch_retries_once_after_mainnx_connect_failed(monkeypatch):
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
        ProcessResult(stdout='{"errcode": -500, "errmsg": "nemu-api init failed"}', stderr="", returncode=1),
    )

    result = await manager._launch_with_retry("0", "")

    assert calls == ["0"]
    assert result.returncode == 1


@pytest.mark.asyncio
async def test_launch_gives_up_when_retry_fails_again(monkeypatch):
    manager = _manager()
    calls = _fake_launch(
        monkeypatch,
        ProcessResult(stdout=CONNECT_FAILED, stderr="", returncode=1),
        ProcessResult(stdout=CONNECT_FAILED, stderr="", returncode=1),
    )

    result = await manager._launch_with_retry("1", "")

    assert calls == ["1", "1"]
    assert result.returncode == 1
