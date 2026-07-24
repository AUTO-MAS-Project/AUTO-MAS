from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.configuration import CONFIG_V2_MODE_AUTHORITATIVE
from app.configuration.roots.config import Webhook as NativeWebhook
from app.models.schema import WebhookTestIn


def _webhook_payload() -> dict[str, object]:
    return {
        "Info": {
            "Name": "native test",
            "Enabled": True,
        },
        "Data": {
            "Url": "https://example.test/hook",
            "Template": "{{ title }}: {{ content }}",
            "Headers": '{"X-Test": "yes"}',
            "Method": "POST",
        },
    }


def test_authoritative_webhook_probe_uses_native_config_entry() -> None:
    from app.api import setting

    with patch.object(
        setting,
        "CONFIG_V2_MODE",
        CONFIG_V2_MODE_AUTHORITATIVE,
    ):
        webhook = setting._build_webhook_test_config(_webhook_payload())

    assert isinstance(webhook, NativeWebhook)
    assert webhook.get("Info", "Name") == "native test"
    assert webhook.get("Data", "Url") == "https://example.test/hook"


@pytest.mark.asyncio
async def test_authoritative_webhook_endpoint_passes_native_entry() -> None:
    from app.api import setting

    sender = AsyncMock(return_value=True)
    request = WebhookTestIn.model_validate({"data": _webhook_payload()})

    with (
        patch.object(
            setting,
            "CONFIG_V2_MODE",
            CONFIG_V2_MODE_AUTHORITATIVE,
        ),
        patch.object(setting.Notify, "WebhookPush", sender),
    ):
        response = await setting.test_webhook(request)

    assert response.code == 200
    sent_webhook = sender.await_args.args[2]
    assert isinstance(sent_webhook, NativeWebhook)
    assert sent_webhook.get("Data", "Method") == "POST"
