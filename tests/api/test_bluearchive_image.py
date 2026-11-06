"""碧蓝档案活动图片中转接口：上游内容类型不规范时的处理。"""

import asyncio
import io

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image

import app.api.info as info_api

IMAGE_URL = "https://cdnimg-v2.gamekee.com/wiki2.0/pro/829/images/sample.webp"


def _patch_upstream(monkeypatch: pytest.MonkeyPatch, content: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=content, headers={"content-type": "binary/octet-stream"}
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(info_api.httpx, "AsyncClient", fake_client)


def test_generic_content_type_with_image_bytes_is_served_as_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="WEBP")
    payload = buffer.getvalue()
    _patch_upstream(monkeypatch, payload)

    response = asyncio.run(info_api.get_bluearchive_image(url=IMAGE_URL))

    assert response.status_code == 200
    assert response.media_type == "image/webp"
    assert response.body == payload


def test_non_image_payload_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_upstream(monkeypatch, b"<html><body>error</body></html>")

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(info_api.get_bluearchive_image(url=IMAGE_URL))

    assert excinfo.value.status_code == 502
