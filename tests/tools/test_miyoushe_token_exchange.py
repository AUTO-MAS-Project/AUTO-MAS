"""米游社通行证换票与云原神凭据兼容的回归测试。"""

from __future__ import annotations

import json

import pytest

from app.tools.common.community.providers import cloud_genshin, miyoushe


class _Response:
    """只实现 _safe_json_parse 需要的响应接口。"""

    def __init__(self, payload: dict[str, object]):
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, object]:
        return self._payload


class _RawResponse:
    """模拟被风控或网关拦截的非 JSON 响应，正文带虚构标记。"""

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def json(self) -> object:
        raise ValueError("not json")


class _Client:
    """记录换票请求并返回预设响应。"""

    def __init__(self, payload: dict[str, object] | _Response | _RawResponse):
        self.response = _Response(payload) if isinstance(payload, dict) else payload
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        content: bytes,
        timeout: float,
    ) -> _Response | _RawResponse:
        body = content.decode("utf-8")
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "body": json.loads(body),
                "body_text": body,
                "timeout": timeout,
            }
        )
        return self.response

    async def get(self, *args: object, **kwargs: object) -> _Response | _RawResponse:
        raise AssertionError("换票流程不应调用 GET")


class _SequenceClient:
    """按顺序返回预设响应，用于模拟签到接口先失败后成功。"""

    def __init__(self, payloads: list[dict[str, object] | _Response | _RawResponse]):
        self.payloads = payloads

    async def __aenter__(self) -> "_SequenceClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> _Response | _RawResponse:
        payload = self.payloads.pop(0)
        return _Response(payload) if isinstance(payload, dict) else payload


@pytest.mark.asyncio
async def test_exchange_passport_token_sends_v2_request_and_reads_nested_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client({"retcode": 0, "data": {"token": {"token": "v2_cookie_token"}}})
    monkeypatch.setattr(
        miyoushe,
        "create_community_client",
        lambda proxy=None: client,
    )

    token = await miyoushe._exchange_passport_token(
        "v2_stoken",
        "mid-value",
        miyoushe.TOKEN_TYPE_COOKIE_TOKEN,
        "device-id",
    )

    assert token == "v2_cookie_token"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == miyoushe.PASSPORT_EXCHANGE_URL
    assert call["body"] == {
        "dst_token_type": 4,
        "src_token": {"token": "v2_stoken", "token_type": 1},
        "mid": "mid-value",
    }
    headers = call["headers"]
    assert headers["x-rpc-app_id"] == miyoushe.PASSPORT_APP_ID
    timestamp, nonce, digest = headers["DS"].split(",")
    expected = miyoushe.hashlib.md5(
        (
            f"salt={miyoushe.SALT_PASSPORT_EXCHANGE}&t={timestamp}"
            f"&r={nonce}&b={call['body_text']}&q="
        ).encode()
    ).hexdigest()
    assert digest == expected


@pytest.mark.asyncio
async def test_exchange_business_error_does_not_expose_upstream_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "FABRICATED_UPSTREAM_BUSINESS_TEXT"
    client = _Client({"retcode": -1, "message": marker})
    monkeypatch.setattr(
        miyoushe,
        "create_community_client",
        lambda proxy=None: client,
    )

    with pytest.raises(ValueError) as exc:
        await miyoushe._exchange_passport_token(
            "v2_stoken",
            "mid-value",
            miyoushe.TOKEN_TYPE_COOKIE_TOKEN,
            "device-id",
        )

    message = str(exc.value)
    assert marker not in message
    assert "-1" in message
    assert "上游业务错误" in message


@pytest.mark.asyncio
async def test_exchange_non_json_error_does_not_expose_upstream_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "FABRICATED_UPSTREAM_BODY"
    client = _Client(_RawResponse(f"<html>{marker}</html>", 403))
    monkeypatch.setattr(
        miyoushe,
        "create_community_client",
        lambda proxy=None: client,
    )

    with pytest.raises(ValueError) as exc:
        await miyoushe._exchange_passport_token(
            "v2_stoken",
            "mid-value",
            miyoushe.TOKEN_TYPE_COOKIE_TOKEN,
            "device-id",
        )

    message = str(exc.value)
    assert marker not in message
    assert "非 JSON" in message
    assert "403" not in message


@pytest.mark.asyncio
async def test_optional_ltoken_failure_keeps_sign_in_and_hides_upstream_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "FABRICATED_OPTIONAL_TOKEN_BODY"
    records: list[str] = []

    class _CaptureLogger:
        def debug(self, message: str) -> None:
            records.append(str(message))

    client = _SequenceClient(
        [
            {"retcode": 0, "data": {"token": {"token": "v2_cookie"}}},
            _RawResponse(f"<html>{marker}</html>", 502),
        ]
    )
    monkeypatch.setattr(
        miyoushe,
        "create_community_client",
        lambda proxy=None: client,
    )
    monkeypatch.setattr(miyoushe, "logger", _CaptureLogger())

    tokens = await miyoushe.derive_miyoushe_tokens("v2_stoken", "mid", "10001")

    assert tokens["cookie_token"] == "v2_cookie"
    assert "ltoken" not in tokens
    assert any("ltoken" in record for record in records)
    assert all(marker not in record for record in records)


@pytest.mark.asyncio
async def test_derive_failure_reason_hides_all_upstream_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "FABRICATED_FALLBACK_BODY"
    client = _SequenceClient(
        [
            _RawResponse(f"{marker}-exchange", 403),
            _RawResponse(f"{marker}-passport", 403),
            _RawResponse(f"{marker}-takumi", 403),
        ]
    )
    monkeypatch.setattr(
        miyoushe,
        "create_community_client",
        lambda proxy=None: client,
    )

    with pytest.raises(ValueError) as exc:
        await miyoushe.derive_miyoushe_tokens("v2_stoken", "mid", "10001")

    message = str(exc.value)
    assert marker not in message
    assert "派生 cookie_token 失败" in message
    assert "非 JSON" in message


@pytest.mark.asyncio
async def test_derive_tokens_prefers_exchange_and_fetches_ltoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    async def exchange(
        stoken: str,
        mid: str,
        token_type: int,
        device_id: str,
        proxy: str | None = None,
    ) -> str:
        calls.append(token_type)
        return "v2_cookie" if token_type == 4 else "v2_ltoken"

    monkeypatch.setattr(miyoushe, "_exchange_passport_token", exchange)

    tokens = await miyoushe.derive_miyoushe_tokens("v2_stoken", "mid", "10001")

    assert tokens == {
        "cookie_token": "v2_cookie",
        "cookie_token_v2": "v2_cookie",
        "ltoken": "v2_ltoken",
        "ltoken_v2": "v2_ltoken",
    }
    assert calls == [4, 2]


@pytest.mark.asyncio
async def test_derive_tokens_falls_back_to_passport_then_takumi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exchange(*args: object, **kwargs: object) -> str:
        raise ValueError("exchange rejected")

    async def passport(*args: object, **kwargs: object) -> tuple[str, str]:
        return "v2_passport", "10001"

    async def takumi(*args: object, **kwargs: object) -> tuple[str, str]:
        raise AssertionError("passport 已成功，不应继续回退")

    monkeypatch.setattr(miyoushe, "_exchange_passport_token", exchange)
    monkeypatch.setattr(miyoushe, "_derive_cookie_token_by_passport", passport)
    monkeypatch.setattr(miyoushe, "_derive_cookie_token_by_takumi", takumi)

    tokens = await miyoushe.derive_miyoushe_tokens("v2_stoken", "mid", "10001")

    assert tokens["cookie_token"] == "v2_passport"
    assert tokens["cookie_token_v2"] == "v2_passport"
    assert tokens["uid"] == "10001"


@pytest.mark.asyncio
async def test_derive_tokens_reports_sanitized_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*args: object, **kwargs: object) -> str:
        raise ValueError("上游拒绝")

    monkeypatch.setattr(miyoushe, "_exchange_passport_token", fail)
    monkeypatch.setattr(miyoushe, "_derive_cookie_token_by_passport", fail)
    monkeypatch.setattr(miyoushe, "_derive_cookie_token_by_takumi", fail)

    with pytest.raises(ValueError) as exc:
        await miyoushe.derive_miyoushe_tokens("v2_stoken", "mid", "10001")

    message = str(exc.value)
    assert "换票链路异常" in message
    assert "上游拒绝" not in message


def test_apply_token_updates_only_writes_cookie_fields() -> None:
    cookies = {"stuid": "10001", "cookie_token": "old"}
    miyoushe._apply_token_updates(
        cookies,
        {
            "cookie_token": "v2_cookie",
            "cookie_token_v2": "v2_cookie",
            "ltoken": "v2_ltoken",
            "ltoken_v2": "v2_ltoken",
            "uid": "10001",
        },
    )

    assert cookies["cookie_token"] == "v2_cookie"
    assert cookies["cookie_token_v2"] == "v2_cookie"
    assert cookies["ltoken"] == "v2_ltoken"
    assert cookies["ltoken_v2"] == "v2_ltoken"
    assert "uid" not in cookies


def test_auth_aliases_cover_ltoken_v2() -> None:
    cookies = {"stoken_v2": "v2_stoken", "mid_v2": "mid", "ltoken_v2": "v2_ltoken"}
    miyoushe._ensure_auth_aliases(cookies)

    assert cookies["stoken"] == "v2_stoken"
    assert cookies["mid"] == "mid"
    assert cookies["ltoken"] == "v2_ltoken"


@pytest.mark.asyncio
async def test_do_sign_uses_v2_aliases_to_refresh_on_minus_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def derive(
        stoken: str,
        mid: str,
        stuid: str,
        proxy: str | None = None,
    ) -> dict[str, str]:
        return {"cookie_token": "v2_new_cookie", "cookie_token_v2": "v2_new_cookie"}

    async def no_sleep(_: float) -> None:
        return None

    client = _SequenceClient(
        [
            {"retcode": -100, "message": "请登录"},
            {
                "retcode": 0,
                "data": {"award": {"name": "原石", "cnt": 30}},
            },
        ]
    )
    monkeypatch.setattr(miyoushe, "derive_miyoushe_tokens", derive)
    monkeypatch.setattr(miyoushe.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(miyoushe, "create_community_client", lambda proxy=None: client)

    result, cookie = await miyoushe._do_sign(
        "stuid=10001; stoken_v2=v2_stoken; mid_v2=mid; cookie_token=expired",
        miyoushe.GAME_CONFIG["hk4e_cn"],
        "cn_gf01",
        "10001",
        "测试账号",
    )

    assert result["status"] == "成功"
    assert result["reward"] == "原石x30"
    assert "cookie_token=v2_new_cookie" in cookie
    assert "cookie_token_v2=v2_new_cookie" in cookie


@pytest.mark.asyncio
async def test_cloud_genshin_receives_both_cookie_token_generations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def derive(
        stoken: str,
        mid: str,
        stuid: str,
        proxy: str | None = None,
    ) -> dict[str, str]:
        return {
            "cookie_token": "v2_cookie",
            "cookie_token_v2": "v2_cookie",
            "ltoken": "v2_ltoken",
            "ltoken_v2": "v2_ltoken",
            "uid": "10001",
        }

    captured: dict[str, object] = {}

    async def request(
        client: object,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: object = None,
        cookies: dict[str, str] | None = None,
    ) -> dict[str, object]:
        captured["cookies"] = dict(cookies or {})
        return {
            "retcode": 0,
            "data": {"combo_token": "c" * 40, "open_id": "10001"},
        }

    monkeypatch.setattr(miyoushe, "derive_miyoushe_tokens", derive)
    monkeypatch.setattr(cloud_genshin, "_request_json", request)

    (
        credential,
        from_miyoushe_cookie,
        _,
    ) = await cloud_genshin._prepare_cloud_genshin_credential(
        object(),
        "stuid=10001; stoken=v2_stoken; mid=mid-value",
    )

    assert from_miyoushe_cookie is True
    assert credential.startswith("ai=4;ci=1;oi=10001;")
    cookies = captured["cookies"]
    assert isinstance(cookies, dict)
    assert cookies["cookie_token"] == "v2_cookie"
    assert cookies["cookie_token_v2"] == "v2_cookie"
    assert cookies["ltoken"] == "v2_ltoken"
    assert cookies["ltoken_v2"] == "v2_ltoken"
