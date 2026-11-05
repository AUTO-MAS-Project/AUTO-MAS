"""碧蓝档案活动图片中转接口：上游内容类型不规范时的处理。"""

import asyncio
import io

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image

import app.api.info as info_api

IMAGE_URL = "https://cdnimg-v2.gamekee.com/wiki2.0/pro/829/images/sample.webp"


def _webp_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="WEBP")
    return buffer.getvalue()


def _patch_upstream(
    monkeypatch: pytest.MonkeyPatch, content: bytes, content_type: str | None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type is not None else {}
        return httpx.Response(200, content=content, headers=headers)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(info_api.httpx, "AsyncClient", fake_client)


@pytest.mark.parametrize(
    "content_type", ["binary/octet-stream", "application/octet-stream", None]
)
def test_generic_content_type_with_image_bytes_is_served_as_image(
    monkeypatch: pytest.MonkeyPatch, content_type: str | None
) -> None:
    payload = _webp_bytes()
    _patch_upstream(monkeypatch, payload, content_type)

    response = asyncio.run(info_api.get_bluearchive_image(url=IMAGE_URL))

    assert response.status_code == 200
    assert response.media_type == "image/webp"
    assert response.body == payload


def test_declared_image_content_type_is_passed_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _webp_bytes()
    _patch_upstream(monkeypatch, payload, "image/webp")

    response = asyncio.run(info_api.get_bluearchive_image(url=IMAGE_URL))

    assert response.media_type == "image/webp"
    assert response.body == payload


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"<html><body>error</body></html>", "text/html"),
        (b"<html><body>error</body></html>", "binary/octet-stream"),
    ],
)
def test_non_image_payload_is_rejected(
    monkeypatch: pytest.MonkeyPatch, content: bytes, content_type: str
) -> None:
    _patch_upstream(monkeypatch, content, content_type)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(info_api.get_bluearchive_image(url=IMAGE_URL))

    assert excinfo.value.status_code == 502
