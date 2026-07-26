from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import game_center as game_center_api
from app.services.game_center import (
    GameCenterService,
    GameCheckResult,
    GameProgressEvent,
    GameProvider,
    GameProviderDescriptor,
    JsonGameCenterRepository,
)
from app.services.game_presets import BUILTIN_GAME_PRESETS


class _Provider(GameProvider):
    descriptor = GameProviderDescriptor(
        name="api.provider",
        display_name="API Provider",
        platforms=frozenset({"pc"}),
        capabilities=frozenset(
            {"check", "install_or_update", "launch", "close"}
        ),
    )

    async def check(self, game):
        return GameCheckResult(
            local_version="2",
            latest_version="3",
            needs_update=True,
            installed=True,
        )

    async def launch(self, game) -> None:
        return None

    async def close(self, game) -> None:
        return None

    async def install_or_update(self, game, progress, cancel_event) -> str:
        await progress(
            GameProgressEvent(
                phase="handoff",
                percent=100.0,
                message="opened official launcher",
            )
        )
        return "handed_off"


@pytest.fixture
def service(tmp_path: Path) -> GameCenterService:
    result = GameCenterService(
        JsonGameCenterRepository(tmp_path / "GameCenter.json"),
        presets=BUILTIN_GAME_PRESETS,
    )
    result.register_provider(_Provider(), owner="plugin:api")
    return result


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    service: GameCenterService,
) -> TestClient:
    app = FastAPI()
    app.include_router(game_center_api.router)
    monkeypatch.setattr(
        game_center_api,
        "_get_game_center_service",
        lambda: service,
    )
    return TestClient(app)


def _add(client: TestClient, name: str = "API Game") -> dict:
    response = client.post(
        "/api/game_center/add",
        json={
            "data": {
                "Info": {
                    "Name": name,
                    "Platform": "pc",
                    "Provider": "api.provider",
                },
                "Data": {"InstallPath": "C:/Games/API"},
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["code"] == 200
    return response.json()


def test_crud_order_and_revision_contract(client: TestClient) -> None:
    first = _add(client, "first")
    second = _add(client, "second")

    response = client.post(
        "/api/game_center/update",
        json={
            "gameId": first["gameId"],
            "expectedRevision": first["data"]["Revision"],
            "data": {"Info": {"Name": "updated"}},
        },
    )
    updated = response.json()
    assert updated["code"] == 200
    assert updated["data"]["Info"]["Name"] == "updated"
    assert updated["data"]["Revision"] == first["data"]["Revision"] + 1

    stale = client.post(
        "/api/game_center/update",
        json={
            "gameId": first["gameId"],
            "expectedRevision": first["data"]["Revision"],
            "data": {"Info": {"Name": "stale"}},
        },
    ).json()
    assert stale["code"] == 409
    assert stale["status"] == "error"

    ordered = client.post(
        "/api/game_center/order",
        json={"indexList": [second["gameId"], first["gameId"]]},
    ).json()
    assert ordered["code"] == 200
    listing = client.post("/api/game_center/get", json={}).json()
    assert listing["index"] == [
        {"uid": second["gameId"], "type": "GameConfig"},
        {"uid": first["gameId"], "type": "GameConfig"},
    ]

    deleted = client.post(
        "/api/game_center/delete",
        json={
            "gameId": second["gameId"],
            "expectedRevision": second["data"]["Revision"],
        },
    ).json()
    assert deleted["code"] == 200


def test_provider_discovery_and_actions(client: TestClient) -> None:
    game = _add(client)
    providers = client.post("/api/game_center/providers").json()
    assert providers["providers"] == [
        {
            "name": "api.provider",
            "displayName": "API Provider",
            "platforms": ["pc"],
            "capabilities": [
                "check",
                "close",
                "install_or_update",
                "launch",
            ],
            "owner": "plugin:api",
        }
    ]

    checked = client.post(
        "/api/game_center/check",
        json={
            "gameId": game["gameId"],
            "expectedRevision": game["data"]["Revision"],
        },
    ).json()
    assert checked["code"] == 200
    assert checked["local_version"] == "2"
    assert checked["needs_update"] is True

    current = client.post(
        "/api/game_center/get",
        json={"gameId": game["gameId"]},
    ).json()["data"][game["gameId"]]
    for action in ("launch", "close"):
        result = client.post(
            f"/api/game_center/{action}",
            json={
                "gameId": game["gameId"],
                "expectedRevision": current["Revision"],
            },
        ).json()
        assert result["code"] == 200
        assert result["provider"] == "api.provider"


def test_install_task_status_and_cancel_error_contract(client: TestClient) -> None:
    game = _add(client)
    started = client.post(
        "/api/game_center/install",
        json={
            "gameId": game["gameId"],
            "expectedRevision": game["data"]["Revision"],
        },
    ).json()
    assert started["code"] == 200
    assert started["running"] is True
    assert started["taskStatus"] == "running"
    assert started["taskId"]

    status = client.post(
        "/api/game_center/task_status",
        json={"gameId": game["gameId"]},
    ).json()
    assert status["code"] == 200
    assert status["running"] is False
    assert status["taskStatus"] == "handed_off"
    assert status["phase"] == "awaiting_user"
    assert status["detail"] == "opened official launcher"

    duplicate_cancel = client.post(
        "/api/game_center/cancel",
        json={
            "gameId": game["gameId"],
            "expectedRevision": game["data"]["Revision"],
            "expectedTaskId": started["taskId"],
        },
    ).json()
    assert duplicate_cancel["code"] == 409
    assert duplicate_cancel["status"] == "error"
    assert "没有可取消" in duplicate_cancel["message"]


def test_read_only_cache_and_unregistered_preset_are_rejected(
    client: TestClient,
) -> None:
    cache_write = client.post(
        "/api/game_center/add",
        json={"data": {"Cache": {"Installed": True}}},
    ).json()
    assert cache_write["code"] == 400
    assert "只读" in cache_write["message"]

    preset = client.post(
        "/api/game_center/add",
        json={"preset": "not-installed", "data": {}},
    ).json()
    assert preset["code"] == 400
    assert "尚未注册" in preset["message"]

    null_name = client.post(
        "/api/game_center/add",
        json={"data": {"Info": {"Name": None}}},
    ).json()
    assert null_name["code"] == 400
    assert null_name["status"] == "error"


def test_presets_are_server_locked_against_ui_bypass(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EmulatorService:
        async def get_config(self, emulator_id: str):
            return [], {
                emulator_id: {
                    "Info": {"Path": "C:/Emulator/bin/manager.exe"},
                }
            }

    from app.plugins import emulator_compat

    monkeypatch.setattr(
        emulator_compat,
        "get_emulator_service",
        lambda: _EmulatorService(),
    )
    presets = client.post("/api/game_center/presets").json()
    assert presets["code"] == 200
    starrail = next(item for item in presets["presets"] if item["key"] == "starrail_cn")
    assert starrail == {
        "key": "starrail_cn",
        "name": "崩坏：星穹铁道（国服）",
        "platform": "pc",
        "provider": "mihoyo_pc",
        "executable": "StarRail.exe",
        "packageName": "",
    }

    created = client.post(
        "/api/game_center/add",
        json={
            "preset": "arknights_android_cn",
            "data": {
                "Info": {
                    "Name": "恶意名称",
                    "Platform": "pc",
                    "Provider": "evil.provider",
                    "PresetKey": "arknights_android_cn",
                },
                "Data": {
                    "InstallPath": "C:/evil.exe",
                    "PackageName": "evil.package",
                    "EmulatorId": "emulator-a",
                    "EmulatorIndex": "2",
                    "AdbPath": "C:/evil/adb.exe",
                    "LaunchArgs": "--evil",
                },
            },
        },
    ).json()
    assert created["code"] == 200
    assert created["data"]["Info"] == {
        "Name": "明日方舟（模拟器国服）",
        "Platform": "emulator",
        "Provider": "adb_apk",
        "PresetKey": "arknights_android_cn",
    }
    assert created["data"]["Data"]["PackageName"] == "com.hypergryph.arknights"
    assert created["data"]["Data"]["EmulatorId"] == "emulator-a"
    assert created["data"]["Data"]["EmulatorIndex"] == "2"
    assert created["data"]["Data"]["AdbPath"] == "C:\\Emulator\\bin\\adb.exe"
    assert created["data"]["Data"]["InstallPath"] is None
    assert created["data"]["Data"]["LaunchArgs"] is None

    updated = client.post(
        "/api/game_center/update",
        json={
            "gameId": created["gameId"],
            "expectedRevision": created["data"]["Revision"],
            "data": {
                "Info": {
                    "Name": "再次绕过",
                    "Platform": "pc",
                    "Provider": "evil.provider",
                    "PresetKey": "arknights_android_cn",
                },
                "Data": {
                    "PackageName": "evil.updated",
                    "EmulatorId": "emulator-a",
                    "EmulatorIndex": "3",
                    "AdbPath": "C:/evil/new-adb.exe",
                },
            },
        },
    ).json()
    assert updated["code"] == 200
    assert updated["data"]["Info"] == created["data"]["Info"]
    assert updated["data"]["Data"]["PackageName"] == "com.hypergryph.arknights"
    assert updated["data"]["Data"]["EmulatorIndex"] == "3"
    assert updated["data"]["Data"]["AdbPath"] == "C:\\Emulator\\bin\\adb.exe"


def test_missing_provider_returns_deterministic_unavailable_error(
    client: TestClient,
) -> None:
    game = client.post(
        "/api/game_center/add",
        json={
            "data": {
                "Info": {
                    "Name": "disabled",
                    "Platform": "pc",
                    "Provider": "disabled.provider",
                }
            }
        },
    ).json()
    launched = client.post(
        "/api/game_center/launch",
        json={
            "gameId": game["gameId"],
            "expectedRevision": game["data"]["Revision"],
        },
    ).json()
    assert launched["code"] == 503
    assert launched["status"] == "error"
    assert launched["provider"] == ""


def test_actions_require_expected_revision(client: TestClient) -> None:
    game = _add(client)
    missing_revision = client.post(
        "/api/game_center/check",
        json={"gameId": game["gameId"]},
    )
    assert missing_revision.status_code == 422

    stale_revision = client.post(
        "/api/game_center/launch",
        json={
            "gameId": game["gameId"],
            "expectedRevision": game["data"]["Revision"] + 1,
        },
    ).json()
    assert stale_revision["code"] == 409
    assert stale_revision["status"] == "error"
