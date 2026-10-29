"""公共信息路由的 HTTP 契约及宿主服务装配回归。"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import info
from app.core import maa_stage


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(info.router)
    with TestClient(app) as client:
        yield client


def test_all_info_routes_keep_methods_and_operation_ids(client):
    expected = {
        ("/activity/completions", "get"): "get_activity_completions",
        ("/activity/completions", "post"): "set_activity_completion",
        ("/taskboard/state", "get"): "get_taskboard_state",
        ("/taskboard/selection", "put"): "set_taskboard_selection",
        ("/taskboard/archive", "put"): "set_taskboard_archive",
        ("/taskboard/done-at", "put"): "set_taskboard_done_at",
        ("/version", "post"): "get_git_version",
        ("/combox/stage", "post"): "get_stage_combox",
        ("/combox/script", "post"): "get_script_combox",
        ("/combox/task", "post"): "get_task_combox",
        ("/combox/plan", "post"): "get_plan_combox",
        ("/combox/emulator", "post"): "get_emulator_combox",
        ("/combox/emulator/devices", "post"): "get_emulator_devices_combox",
        ("/notice/get", "post"): "get_notice_info",
        ("/notice/confirm", "post"): "confirm_notice",
        ("/get/overview", "post"): "get_overview",
        ("/bluearchive/activity", "post"): "get_bluearchive_activity",
        ("/bluearchive/image", "get"): "get_bluearchive_image",
        ("/endfield/version-art", "get"): "get_endfield_version_art",
        ("/endfield/image", "get"): "get_endfield_image",
        ("/arknights/activity", "get"): "get_arknights_activity",
        ("/stella/activity", "post"): "get_stella_activity",
        ("/azurlane/activity", "post"): "get_azurlane_activity",
    }
    paths = client.get("/openapi.json").json()["paths"]
    actual = {
        (path.removeprefix("/api/info"), method): operation["operationId"]
        for path, methods in paths.items()
        for method, operation in methods.items()
    }
    assert set(actual) == set(expected)
    for (path, method), function in expected.items():
        suffix = ("/api/info" + path).replace("/", "_").replace("-", "_")
        assert actual[path, method] == f"{function}{suffix}_{method}"


@pytest.mark.parametrize(
    "path,method,module,name,payload",
    [
        (
            "/arknights/activity",
            "get",
            info.arknights_activity,
            "fetch_arknights_activities",
            None,
        ),
        (
            "/stella/activity",
            "post",
            info.stella_official,
            "fetch_stella_activities",
            None,
        ),
        ("/azurlane/activity", "post", info, "fetch_azurlane_activities", None),
        (
            "/endfield/version-art",
            "get",
            info.endfield_images,
            "fetch_version_art",
            None,
        ),
        (
            "/bluearchive/activity",
            "post",
            info,
            "fetch_bluearchive_activities",
            {"line_type": "Globle", "page": 2, "page_size": 30},
        ),
    ],
)
def test_activity_envelopes_and_forwarded_arguments(
    client, monkeypatch, path, method, module, name, payload
):
    data = {"activities": [{"name": "event", "startTime": "2026-10-01T00:00:00+08:00"}]}
    fetch = AsyncMock(return_value=data)
    monkeypatch.setattr(module, name, fetch)
    response = client.request(method, "/api/info" + path, json=payload)
    assert response.status_code == 200
    assert response.json() == {**info.OutBase().model_dump(), "data": data}
    if payload:
        fetch.assert_awaited_once_with(**payload)
    else:
        fetch.assert_awaited_once_with()


@pytest.mark.parametrize(
    "path,method,module,name,result",
    [
        (
            "/arknights/activity",
            "get",
            info.arknights_activity,
            "fetch_arknights_activities",
            ValueError("upstream"),
        ),
        (
            "/bluearchive/activity",
            "post",
            info,
            "fetch_bluearchive_activities",
            ValueError("upstream"),
        ),
        (
            "/stella/activity",
            "post",
            info.stella_official,
            "fetch_stella_activities",
            None,
        ),
        ("/azurlane/activity", "post", info, "fetch_azurlane_activities", None),
    ],
)
def test_activity_errors_remain_http_200_envelopes(
    client, monkeypatch, path, method, module, name, result
):
    fetch = (
        AsyncMock(side_effect=result)
        if isinstance(result, Exception)
        else AsyncMock(return_value=result)
    )
    monkeypatch.setattr(module, name, fetch)
    response = client.request(
        method, "/api/info" + path, json={"line_type": "CN", "page": 1, "page_size": 20}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 500 and body["status"] == "error" and body["data"] == {}
    if isinstance(result, Exception):
        assert body["message"] == "ValueError: upstream"


@pytest.mark.parametrize(
    "path,module,name",
    [
        (
            "/bluearchive/image",
            info.bluearchive_activity_source,
            "fetch_bluearchive_image",
        ),
        ("/endfield/image", info.endfield_images, "fetch_image"),
    ],
)
@pytest.mark.parametrize(
    "error_type,status", [("ImageSourceNotAllowed", 400), ("ImageUnavailable", 502)]
)
def test_image_error_translation(
    client, monkeypatch, path, module, name, error_type, status
):
    monkeypatch.setattr(
        module, name, AsyncMock(side_effect=getattr(module, error_type)("detail"))
    )
    response = client.get(
        "/api/info" + path, params={"url": "https://example.test/image"}
    )
    assert response.status_code == status
    assert response.json() == {"detail": "detail" if status == 400 else "图片获取失败"}


def test_image_response_bytes_media_cache_headers(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        info.bluearchive_activity_source,
        "fetch_bluearchive_image",
        AsyncMock(return_value=(b"original", "image/webp")),
    )
    response = client.get("/api/info/bluearchive/image", params={"url": "allowed"})
    assert (
        response.content == b"original"
        and response.headers["content-type"] == "image/webp"
    )
    path = tmp_path / "image.jpg"
    path.write_bytes(b"thumbnail")
    monkeypatch.setattr(
        info.endfield_images, "fetch_image", AsyncMock(return_value=path)
    )
    endfield = client.get("/api/info/endfield/image", params={"url": "allowed"})
    assert (
        endfield.content == b"thumbnail"
        and endfield.headers["content-type"] == "image/jpeg"
    )
    for image in (response, endfield):
        assert image.headers["cache-control"] == "public, max-age=86400"


def test_maa_overview_and_stage_use_the_host_service(client, monkeypatch):
    service = maa_stage.maa_stage_service
    get_stage = AsyncMock()
    get_info = AsyncMock(
        side_effect=lambda kind, **kwargs: [
            {"label": kwargs.get("server", kind), "value": kind}
        ]
    )
    monkeypatch.setattr(service, "get_stage", get_stage)
    monkeypatch.setattr(service, "get_stage_info", get_info)
    monkeypatch.setattr(
        info.Config, "get_proxy_overview", AsyncMock(return_value=[{"proxy": "data"}])
    )
    overview = client.post("/api/info/get/overview?refresh=true").json()
    servers = ("Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy")
    assert overview["data"]["Stage"] == overview["data"]["StageByServer"]["Official"]
    assert tuple(overview["data"]["StageByServer"]) == servers
    assert overview["data"]["Proxy"] == [{"proxy": "data"}]
    get_stage.assert_awaited_once_with(refresh=True)
    assert [call.kwargs["server"] for call in get_info.await_args_list] == list(servers)
    response = client.post("/api/info/combox/stage", json={"type": "Today"})
    assert response.json()["data"] == [{"label": "Today", "value": "Today"}]
    get_info.assert_awaited_with("Today")
    get_info.side_effect = RuntimeError("unavailable")
    assert client.post("/api/info/get/overview").json()["data"] == {
        "Stage": [],
        "Proxy": [],
    }
    assert (
        client.post("/api/info/combox/stage", json={"type": "Today"}).json()["data"]
        == []
    )
