import asyncio
from unittest.mock import MagicMock

import pytest

import app.api.core as core_api
from app.core import Config


def _make_request(
    background_status: str = "ready", background_error: str | None = None
) -> MagicMock:
    request = MagicMock()
    request.app.state.background_status = background_status
    request.app.state.background_error = background_error
    return request


def _get_health() -> core_api.BackendHealthOut:
    return asyncio.run(core_api.get_health(_make_request()))


def test_supervised_with_full_identity_echoes_injected_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """受监督且三个环境变量齐全时，身份字段精确等于注入值（protocol 固定为 1）。"""

    monkeypatch.setenv("AUTO_MAS_SUPERVISED", "1")
    monkeypatch.setenv("AUTO_MAS_EXPECTED_VERSION", "v5.5.0-beta.3")
    monkeypatch.setenv(
        "AUTO_MAS_EXPECTED_COMMIT", "0123456789abcdef0123456789abcdef01234567"
    )

    result = _get_health()

    assert result.protocol == 1
    assert result.version == "v5.5.0-beta.3"
    assert result.commit == "0123456789abcdef0123456789abcdef01234567"


def test_unsupervised_falls_back_to_local_version_and_empty_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未受监督时忽略残留的期望版本/提交环境变量，回退本地版本号与空提交。"""

    monkeypatch.delenv("AUTO_MAS_SUPERVISED", raising=False)
    monkeypatch.setenv("AUTO_MAS_EXPECTED_VERSION", "v9.9.9")
    monkeypatch.setenv(
        "AUTO_MAS_EXPECTED_COMMIT", "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    )

    result = _get_health()

    assert result.protocol == 1
    assert result.version == Config.VERSION
    assert result.commit == ""
