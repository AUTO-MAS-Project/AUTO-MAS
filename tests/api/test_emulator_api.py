"""模拟器 API 端点确定性测试。

使用 FastAPI TestClient 验证所有 CRUD / operate / status / search 端点的返回语义，
重点检查：
- 成功路径的 code/status/message/envelope 结构
- operate 端点的 accepted / operationId 契约（消除假成功）
- 错误路径的 _error_code 映射（ValueError/KeyError/FileNotFoundError → 400, 其它 → 500）

所有测试通过 monkeypatch 替换 ``_get_emulator_service``，不触达真实配置/进程/注册表。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import emulator as emulator_api
from app.api.emulator import router


# ---------------------------------------------------------------------------
# Fake service
# ---------------------------------------------------------------------------


class _FakeConfigLike:
    """模拟 ``EmulatorConfig`` 实例，提供 ``toDict()`` 协程。"""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data or {}

    async def toDict(self) -> dict[str, Any]:
        return self._data


class FakeEmulatorService:
    """可配置的模拟器服务替身。

    每个方法可通过 ``set_*`` 配置返回值或抛出异常，实现确定性测试。
    """

    def __init__(self) -> None:
        self.get_config_return: tuple[list, dict] = ([], {})
        self.get_config_exc: Exception | None = None

        self.add_return: tuple[str, _FakeConfigLike] = ("", _FakeConfigLike())
        self.add_exc: Exception | None = None

        self.update_exc: Exception | None = None
        self.delete_exc: Exception | None = None
        self.reorder_exc: Exception | None = None

        self.operate_return: str = "op-id-fixture"
        self.operate_exc: Exception | None = None

        self.status_return: dict = {}
        self.status_exc: Exception | None = None

        self.search_return: list[dict] = []
        self.search_exc: Exception | None = None

    async def get_config(self, emulator_id: str | None):
        if self.get_config_exc is not None:
            raise self.get_config_exc
        return self.get_config_return

    async def add(self):
        if self.add_exc is not None:
            raise self.add_exc
        return self.add_return

    async def update(self, emulator_id: str, data: dict) -> None:
        if self.update_exc is not None:
            raise self.update_exc

    async def delete(self, emulator_id: str) -> None:
        if self.delete_exc is not None:
            raise self.delete_exc

    async def reorder(self, index_list: list[str]) -> None:
        if self.reorder_exc is not None:
            raise self.reorder_exc

    async def operate(self, operate: str, emulator_id: str, index: str) -> str:
        if self.operate_exc is not None:
            raise self.operate_exc
        return self.operate_return

    async def status(self, emulator_id: str | None = None):
        if self.status_exc is not None:
            raise self.status_exc
        return self.status_return

    async def search_installed(self) -> list[dict[str, str]]:
        if self.search_exc is not None:
            raise self.search_exc
        return self.search_return


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_service() -> FakeEmulatorService:
    return FakeEmulatorService()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeEmulatorService
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(emulator_api, "_get_emulator_service", lambda: fake_service)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/emulator/get
# ---------------------------------------------------------------------------


class TestGetEmulator:
    def test_success_returns_index_and_data(self, client, fake_service) -> None:
        fake_service.get_config_return = (
            [{"uid": "emu-1", "type": "EmulatorConfig"}],
            {"emu-1": {"Info": {"Name": "test"}}},
        )
        resp = client.post("/api/emulator/get", json={"emulatorId": "emu-1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["status"] == "success"
        assert len(body["index"]) == 1
        assert body["index"][0]["uid"] == "emu-1"
        assert "emu-1" in body["data"]

    def test_value_error_returns_400(self, client, fake_service) -> None:
        fake_service.get_config_exc = ValueError("bad id")
        resp = client.post("/api/emulator/get", json={"emulatorId": "bad"})
        assert resp.json()["code"] == 400
        assert resp.json()["status"] == "error"
        assert "ValueError" in resp.json()["message"]

    def test_runtime_error_returns_500(self, client, fake_service) -> None:
        fake_service.get_config_exc = RuntimeError("boom")
        resp = client.post("/api/emulator/get", json={"emulatorId": "x"})
        assert resp.json()["code"] == 500
        assert resp.json()["status"] == "error"

    def test_no_body_gets_all(self, client, fake_service) -> None:
        fake_service.get_config_return = ([], {})
        resp = client.post("/api/emulator/get", json={})
        assert resp.json()["code"] == 200
        assert resp.json()["data"] == {}


# ---------------------------------------------------------------------------
# /api/emulator/add
# ---------------------------------------------------------------------------


class TestAddEmulator:
    def test_success_returns_emulator_id_and_data(self, client, fake_service) -> None:
        fake_service.add_return = ("new-uid", _FakeConfigLike({"Info": {"Name": "new"}}))
        resp = client.post("/api/emulator/add")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["emulatorId"] == "new-uid"
        assert body["data"]["Info"]["Name"] == "new"

    def test_failure_returns_error_envelope(self, client, fake_service) -> None:
        fake_service.add_exc = RuntimeError("disk full")
        resp = client.post("/api/emulator/add")
        body = resp.json()
        assert body["code"] == 500
        assert body["status"] == "error"
        assert body["emulatorId"] == ""


# ---------------------------------------------------------------------------
# /api/emulator/update
# ---------------------------------------------------------------------------


class TestUpdateEmulator:
    def test_success_returns_default_outbase(self, client, fake_service) -> None:
        resp = client.post(
            "/api/emulator/update",
            json={
                "emulatorId": "emu-1",
                "data": {"Info": {"Name": "updated"}},
            },
        )
        body = resp.json()
        assert body["code"] == 200
        assert body["status"] == "success"

    def test_key_error_returns_400(self, client, fake_service) -> None:
        fake_service.update_exc = KeyError("not found")
        resp = client.post(
            "/api/emulator/update",
            json={"emulatorId": "missing", "data": {}},
        )
        assert resp.json()["code"] == 400
        assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# /api/emulator/delete
# ---------------------------------------------------------------------------


class TestDeleteEmulator:
    def test_success(self, client, fake_service) -> None:
        resp = client.post(
            "/api/emulator/delete", json={"emulatorId": "emu-1"}
        )
        assert resp.json()["code"] == 200

    def test_file_not_found_returns_400(self, client, fake_service) -> None:
        fake_service.delete_exc = FileNotFoundError("gone")
        resp = client.post(
            "/api/emulator/delete", json={"emulatorId": "gone"}
        )
        assert resp.json()["code"] == 400
        assert "FileNotFoundError" in resp.json()["message"]


# ---------------------------------------------------------------------------
# /api/emulator/order
# ---------------------------------------------------------------------------


class TestReorderEmulator:
    def test_success(self, client, fake_service) -> None:
        resp = client.post(
            "/api/emulator/order", json={"indexList": ["a", "b"]}
        )
        assert resp.json()["code"] == 200

    def test_value_error_returns_400(self, client, fake_service) -> None:
        fake_service.reorder_exc = ValueError("dup id")
        resp = client.post(
            "/api/emulator/order", json={"indexList": ["a", "a"]}
        )
        assert resp.json()["code"] == 400


# ---------------------------------------------------------------------------
# /api/emulator/operate — accepted / operationId 契约
# ---------------------------------------------------------------------------


class TestOperateEmulator:
    def test_success_returns_accepted_and_operation_id(
        self, client, fake_service
    ) -> None:
        fake_service.operate_return = "uuid-op-123"
        resp = client.post(
            "/api/emulator/operate",
            json={
                "emulatorId": "emu-1",
                "operate": "open",
                "index": "0",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["status"] == "accepted"
        assert body["accepted"] is True
        assert body["operationId"] == "uuid-op-123"
        assert "WS" in body["message"] or "推送" in body["message"]

    def test_value_error_returns_400_not_accepted(
        self, client, fake_service
    ) -> None:
        fake_service.operate_exc = ValueError("bad uuid")
        resp = client.post(
            "/api/emulator/operate",
            json={
                "emulatorId": "bad",
                "operate": "open",
                "index": "0",
            },
        )
        body = resp.json()
        assert body["code"] == 400
        assert body["status"] == "error"
        assert body["accepted"] is False
        assert body["operationId"] is None

    def test_file_not_found_returns_400(self, client, fake_service) -> None:
        fake_service.operate_exc = FileNotFoundError("path missing")
        resp = client.post(
            "/api/emulator/operate",
            json={
                "emulatorId": "emu-1",
                "operate": "close",
                "index": "0",
            },
        )
        assert resp.json()["code"] == 400
        assert resp.json()["accepted"] is False

    def test_key_error_returns_400(self, client, fake_service) -> None:
        fake_service.operate_exc = KeyError("no config")
        resp = client.post(
            "/api/emulator/operate",
            json={
                "emulatorId": "missing",
                "operate": "show",
                "index": "0",
            },
        )
        assert resp.json()["code"] == 400

    def test_runtime_error_returns_500(self, client, fake_service) -> None:
        fake_service.operate_exc = RuntimeError("device busy")
        resp = client.post(
            "/api/emulator/operate",
            json={
                "emulatorId": "emu-1",
                "operate": "open",
                "index": "0",
            },
        )
        body = resp.json()
        assert body["code"] == 500
        assert body["status"] == "error"
        assert body["accepted"] is False

    def test_operate_enum_validation(self, client, fake_service) -> None:
        """operate 字段必须是 open/close/show 之一。"""
        resp = client.post(
            "/api/emulator/operate",
            json={
                "emulatorId": "emu-1",
                "operate": "invalid",
                "index": "0",
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/emulator/status
# ---------------------------------------------------------------------------


class TestStatusEmulator:
    def test_success_returns_data(self, client, fake_service) -> None:
        fake_service.status_return = {
            "emu-1": {
                "0": {"title": "dev0", "status": 0, "adb_address": "127.0.0.1:5555"}
            }
        }
        resp = client.post("/api/emulator/status", json={"emulatorId": "emu-1"})
        body = resp.json()
        assert body["code"] == 200
        assert "emu-1" in body["data"]
        assert body["data"]["emu-1"]["0"]["title"] == "dev0"

    def test_failure_returns_error_with_empty_data(
        self, client, fake_service
    ) -> None:
        fake_service.status_exc = RuntimeError("scan failed")
        resp = client.post("/api/emulator/status", json={"emulatorId": "emu-1"})
        body = resp.json()
        assert body["code"] == 500
        assert body["status"] == "error"
        assert body["data"] == {}


# ---------------------------------------------------------------------------
# /api/emulator/emulator/search
# ---------------------------------------------------------------------------


class TestSearchEmulators:
    def test_success_returns_list(self, client, fake_service) -> None:
        fake_service.search_return = [
            {"type": "mumu", "path": "C:\\mumu", "name": "MuMu"},
            {"type": "ldplayer", "path": "C:\\ld", "name": "LDPlayer"},
        ]
        resp = client.post("/api/emulator/emulator/search")
        body = resp.json()
        assert body["code"] == 200
        assert len(body["emulators"]) == 2
        assert body["emulators"][0]["type"] == "mumu"

    def test_failure_returns_empty_list(self, client, fake_service) -> None:
        fake_service.search_exc = RuntimeError("registry locked")
        resp = client.post("/api/emulator/emulator/search")
        body = resp.json()
        assert body["code"] == 500
        assert body["status"] == "error"
        assert body["emulators"] == []
