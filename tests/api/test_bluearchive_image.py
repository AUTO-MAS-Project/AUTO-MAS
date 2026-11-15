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


def test_generic_content_type_is_validated_before_serving_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="WEBP")
    payload = buffer.getvalue()
    with monkeypatch.context() as upstream:
        _patch_upstream(upstream, payload)
        response = asyncio.run(info_api.get_bluearchive_image(url=IMAGE_URL))
        assert response.status_code == 200
        assert response.media_type == "image/webp"
        assert response.body == payload

    with monkeypatch.context() as upstream:
        _patch_upstream(upstream, b"<html>upstream error</html>")
        with pytest.raises(HTTPException) as caught:
            asyncio.run(info_api.get_bluearchive_image(url=IMAGE_URL))
        assert caught.value.status_code == 502
