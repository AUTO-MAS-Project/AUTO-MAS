"""Mirror 酱 ``/latest`` 查询必须始终带 ``os`` / ``arch``。

``interface.json`` 的 ``mirrorchyan_multiplatform`` 只是发布方给打包器的提示，
分平台发布的项目（MAA_Punish）并没有写它；而 Mirror 酱对分平台 rid 不带 os/arch
直接回 ``8001 resource not found``，运行前更新检查就整条失败。单平台 rid 多带这
两个参数照常回 200（线上实测 AUTO_MAS），所以不再按该字段分支。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_project_update import updater


class _FakeResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "code": 0,
            "msg": "current resource latest version is v3.10.42",
            "data": {
                "version_name": "v3.10.42",
                "channel": "stable",
                "os": "windows",
                "arch": "amd64",
            },
        }


class _FakeAsyncClient:
    captured: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def get(
        self, url: str, *, params: dict[str, str], headers: Any
    ) -> _FakeResponse:
        self.captured.append({"url": url, "params": dict(params)})
        return _FakeResponse()


@pytest.fixture
def captured_requests(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    _FakeAsyncClient.captured = []
    monkeypatch.setattr(updater.httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient.captured


@pytest.mark.asyncio
@pytest.mark.parametrize("multiplatform", [None, False, True])
async def test_latest_query_always_carries_os_and_arch(
    captured_requests: list[dict[str, Any]], multiplatform: bool | None
) -> None:
    interface = MaaFWInterface(
        interface_version=2,
        name="FOS",
        mirrorchyan_rid="MAA_Punish",
        mirrorchyan_multiplatform=multiplatform,
    )

    check = await updater._query_mirrorchyan_latest(
        interface,
        current_version="v3.10.41",
        mirror_cdk="",
        channel="stable",
        proxy=None,
    )

    assert check.version_name == "v3.10.42"
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request["url"].endswith("/api/resources/MAA_Punish/latest")
    assert request["params"]["os"] == "win"
    assert request["params"]["arch"] == "x86_64"
    assert request["params"]["current_version"] == "v3.10.41"
    assert "cdk" not in request["params"]
