"""公共下载入口的取消与未停写异常不被隐藏或重试。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import script_update as update
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [asyncio.CancelledError(), FluxdownCancelUnconfirmed("unconfirmed")]
)
async def test_cancellation_is_never_hidden_or_retried(tmp_path, monkeypatch, error):
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(FluxdownTakeoverAll=True)),
        ),
    )
    download = AsyncMock(side_effect=error)
    monkeypatch.setattr(update, "download_file", download)
    with pytest.raises(type(error)):
        await update.download_script_package(
            "https://example.invalid/package",
            tmp_path / "package",
            source="GitHub",
            timeout=20,
        )
    download.assert_awaited_once()
