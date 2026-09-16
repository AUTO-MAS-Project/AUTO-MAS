"""网页邮件内嵌图片（CID）与 Webhook 图片占位段的投递形态。

失败截图要能进邮件正文而不被客户端拦掉，只能走 ``multipart/related`` +
Content-ID；``<img src="data:...">`` 那条路六星喜报早就验证过走不通。
"""

import asyncio
import json
from email import message_from_string
from typing import Any
from unittest.mock import patch

import pytest

from app.services import notification as notification_module
from app.services.notification import MailInlineImage, Notification

_CONFIG = {
    ("Notify", "SMTPServerAddress"): "smtp.example.com",
    ("Notify", "AuthorizationCode"): "code",
    ("Notify", "FromAddress"): "from@example.com",
}


class _FakeSMTP:
    sent: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *exc: Any) -> None:
        pass

    def login(self, *args: Any) -> None:
        pass

    def sendmail(self, _from: str, _to: str, message: str) -> None:
        _FakeSMTP.sent.append(message)


@pytest.fixture
def mail_env(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    _FakeSMTP.sent = []
    monkeypatch.setattr(notification_module.smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(
        notification_module.Config, "get", lambda section, key: _CONFIG[(section, key)]
    )
    return _FakeSMTP.sent


def _send(**kwargs: Any) -> str:
    asyncio.run(
        Notification().send_mail(
            title="报告",
            content=kwargs.pop("content", "<p>hi</p>"),
            to_address="to@example.com",
            **kwargs,
        )
    )
    assert len(_FakeSMTP.sent) == 1
    return _FakeSMTP.sent[0]


def test_html_mail_with_images_is_multipart_related_with_cid(mail_env) -> None:
    raw = _send(
        mode="网页",
        content='<p>x</p><img src="cid:shot-1">',
        images=[MailInlineImage("shot-1", b"\x89PNGfake", "png")],
    )
    message = message_from_string(raw)
    assert message.get_content_type() == "multipart/related"
    parts = message.get_payload()
    assert [part.get_content_type() for part in parts] == ["text/html", "image/png"]
    image = parts[1]
    assert image["Content-ID"] == "<shot-1>"
    assert image.get_content_disposition() == "inline"
    assert image.get_payload(decode=True) == b"\x89PNGfake"


def test_html_mail_without_images_keeps_alternative(mail_env) -> None:
    message = message_from_string(_send(mode="网页"))
    assert message.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in message.get_payload()] == ["text/html"]


def test_text_mail_ignores_images(mail_env) -> None:
    message = message_from_string(
        _send(mode="文本", content="plain", images=[MailInlineImage("x", b"1")])
    )
    assert message.get_content_type() == "text/plain"


class _Webhook:
    def __init__(self, template: str) -> None:
        self._data = {
            ("Info", "Enabled"): True,
            ("Info", "Name"): "bot",
            ("Data", "Url"): "http://127.0.0.1:1/send",
            ("Data", "Template"): template,
            ("Data", "Headers"): "{}",
            ("Data", "Method"): "POST",
        }

    def get(self, section: str, key: str) -> Any:
        return self._data[(section, key)]


class _Response:
    is_success = True
    status_code = 200
    text = '{"status":"ok","retcode":0}'


class _Client:
    posted: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        pass

    async def post(self, url: str, json: Any = None, **kwargs: Any) -> _Response:
        _Client.posted.append(json)
        return _Response()


_TEXT_IMAGE_TEMPLATE = json.dumps(
    {
        "user_id": "1",
        "message": [
            {"type": "text", "data": {"text": "{title}\n{content}"}},
            {"type": "image", "data": {"file": "base64://{image_base64}"}},
        ],
    }
)
_IMAGE_ONLY_TEMPLATE = json.dumps(
    {
        "user_id": "1",
        "message": [{"type": "image", "data": {"file": "base64://{image_base64}"}}],
    }
)


def _push(template: str, image_base64: str) -> list[dict[str, Any]]:
    _Client.posted = []
    with patch.object(notification_module.httpx, "AsyncClient", _Client):
        asyncio.run(
            Notification().WebhookPush(
                "T", "C", _Webhook(template), image_base64=image_base64
            )
        )
    return _Client.posted[0]["message"]


def test_text_image_template_drops_image_segment_when_no_image() -> None:
    segments = _push(_TEXT_IMAGE_TEMPLATE, "")
    assert segments == [{"type": "text", "data": {"text": "T\nC"}}]


def test_text_image_template_fills_image_when_present() -> None:
    segments = _push(_TEXT_IMAGE_TEMPLATE, "QUJD")
    assert segments[0] == {"type": "text", "data": {"text": "T\nC"}}
    assert segments[1] == {"type": "image", "data": {"file": "base64://QUJD"}}


def test_image_only_template_still_falls_back_to_text() -> None:
    segments = _push(_IMAGE_ONLY_TEMPLATE, "")
    assert segments == [{"type": "text", "data": {"text": "T\n\nC"}}]
