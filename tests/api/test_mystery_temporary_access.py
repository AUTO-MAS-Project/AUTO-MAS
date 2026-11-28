"""神秘入口在临时开放期间使用当天的解锁记录。"""

import json
import sys
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mystery
from app.mystery import gate, temporary_access

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="限时开放仅供 Windows 客户端"
)

_CONTEXT_URL = "/api/mystery/context"
_DESKTOP_HEADERS = {
    "user-agent": "Mozilla/5.0 Electron/43.8.2 Safari/537.36",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}
_DEVICE = "a" * 64
_BACKEND = "b" * 64
_FINGERPRINT = f"{_DEVICE}:{_BACKEND}"


@pytest.fixture
def entrance(isolated_app_paths, monkeypatch):
    monkeypatch.setattr(mystery, "get_access_context", lambda: (_DEVICE, _BACKEND))
    config_path = isolated_app_paths.config_path / gate.CONFIG_FILE_NAME
    config_path.parent.mkdir(parents=True, exist_ok=True)
    app = FastAPI()
    app.include_router(mystery.router)
    return app, config_path


def _set_time(monkeypatch, clock_time: str) -> None:
    current = datetime.fromisoformat(clock_time)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current.astimezone(tz)

    monkeypatch.setattr(temporary_access, "datetime", FixedClock)


def test_desktop_opens_once_a_day_and_respects_manual_lock(entrance, monkeypatch):
    app, path = entrance
    path.write_text('{"language": "ja-JP"}', encoding="utf-8")
    _set_time(monkeypatch, "2026-12-08T23:59:59+08:00")

    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        response = client.get(_CONTEXT_URL, headers=_DESKTOP_HEADERS)
        assert response.status_code == 200
        assert response.json()["data"] == {
            "deviceHash": _DEVICE,
            "backendHash": _BACKEND,
        }
        config = json.loads(path.read_bytes())
        assert config["language"] == "ja-JP"
        assert config["mysteryUnlockedDate"] == "2026-12-08"
        assert config["mysteryUnlockedFingerprint"] == _FINGERPRINT

        # 客户端手动锁定时保留配置中其余字段。
        config.update(mysteryUnlockedDate="", mysteryUnlockedFingerprint="")
        path.write_text(json.dumps(config), encoding="utf-8")
        client.get(_CONTEXT_URL, headers=_DESKTOP_HEADERS)
        assert json.loads(path.read_bytes()) == config

        _set_time(monkeypatch, "2026-12-09T23:59:59+08:00")
        client.get(_CONTEXT_URL, headers=_DESKTOP_HEADERS)
        assert json.loads(path.read_bytes())["mysteryUnlockedDate"] == "2026-12-09"

        _set_time(monkeypatch, "2026-12-10T00:00:00+08:00")
        client.get(_CONTEXT_URL, headers=_DESKTOP_HEADERS)
        assert json.loads(path.read_bytes())["mysteryUnlockedDate"] == "2026-12-09"


def test_manual_lock_after_loading_an_existing_unlock(entrance, monkeypatch):
    app, path = entrance
    _set_time(monkeypatch, "2026-12-09T12:00:00+08:00")
    unlocked = {
        "mysteryUnlockedDate": "2026-12-09",
        "mysteryUnlockedFingerprint": _FINGERPRINT,
    }
    path.write_text(json.dumps(unlocked), encoding="utf-8")
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get(_CONTEXT_URL, headers=_DESKTOP_HEADERS).status_code == 200
        config = json.loads(path.read_bytes())
        config.update(mysteryUnlockedDate="", mysteryUnlockedFingerprint="")
        path.write_text(json.dumps(config), encoding="utf-8")
        client.get(_CONTEXT_URL, headers=_DESKTOP_HEADERS)
    assert json.loads(path.read_bytes()) == config


@pytest.mark.parametrize(
    ("address", "headers"),
    [
        ("192.0.2.10", _DESKTOP_HEADERS),
        ("127.0.0.1", {**_DESKTOP_HEADERS, "origin": "https://example.test"}),
        ("127.0.0.1", {}),
    ],
)
def test_context_queries_outside_desktop_remain_read_only(
    entrance, monkeypatch, address, headers
):
    app, path = entrance
    _set_time(monkeypatch, "2026-12-09T12:00:00+08:00")
    with TestClient(app, client=(address, 12345)) as client:
        assert client.get(_CONTEXT_URL, headers=headers).status_code == 200
    assert not path.exists()


def test_invalid_config_is_left_for_recovery(entrance, monkeypatch):
    app, path = entrance
    path.write_bytes(b"{")
    _set_time(monkeypatch, "2026-12-09T12:00:00+08:00")
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get(_CONTEXT_URL, headers=_DESKTOP_HEADERS).status_code == 200
    assert path.read_bytes() == b"{"


def test_new_desktop_profile_loads_an_unlock_record(entrance, monkeypatch):
    app, path = entrance
    _set_time(monkeypatch, "2026-12-09T12:00:00+08:00")
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get(_CONTEXT_URL, headers=_DESKTOP_HEADERS).status_code == 200
    config = json.loads(path.read_bytes())
    assert config["mysteryUnlockedDate"] == "2026-12-09"
    assert config["mysteryUnlockedFingerprint"] == _FINGERPRINT


def test_config_replacement_keeps_an_intervening_client_save(tmp_path):
    from app.mystery.windows_config import replace_if_unchanged

    path = tmp_path / gate.CONFIG_FILE_NAME
    path.write_bytes(b'{"language": "ja-JP"}')
    before = path.read_bytes()
    path.write_bytes(b'{"language": "zh-CN"}')

    replace_if_unchanged(
        path=path,
        original=before,
        updated=b'{"language": "ja-JP", "mysteryUnlockedDate": "2026-12-09"}',
    )

    assert path.read_bytes() == b'{"language": "zh-CN"}'
