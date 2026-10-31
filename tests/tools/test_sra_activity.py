"""SRA 取数失败仍可通过项目日志格式记录原始异常。"""

import httpx
import pytest
from loguru import logger

from app.tools.common.game_calendar import sra as sra_activity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,error_type",
    [
        ("connection", httpx.ConnectError),
        ("http", httpx.HTTPStatusError),
        ("payload", ValueError),
    ],
)
async def test_fetch_failure_preserves_module_and_exception(
    monkeypatch, tmp_path, failure, error_type
):
    def handle(request):
        if failure == "connection":
            raise httpx.ConnectError("synthetic connection failure", request=request)
        if failure == "http":
            return httpx.Response(404)
        return httpx.Response(200, json={"invalid": []})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        sra_activity.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    monkeypatch.setattr(sra_activity, "_states", {})
    monkeypatch.setattr(sra_activity, "SRA_RETRY_DELAY_SECONDS", 0)

    log_path = tmp_path / "sra.log"
    messages = []
    # 与项目 sink 共用模块字段契约；缺少字段时直接失败，不吞掉格式化异常。
    log_format = "{extra[module]} | {message}"
    file_sink = logger.add(
        log_path,
        format=log_format,
        level="WARNING",
        catch=False,
        diagnose=False,
        encoding="utf-8",
    )
    memory_sink = logger.add(
        messages.append,
        format=log_format,
        level="WARNING",
        catch=False,
        diagnose=False,
    )
    try:
        assert await sra_activity.fetch_sra_activities("ak") is None
    finally:
        logger.remove(file_sink)
        logger.remove(memory_sink)

    assert len(messages) == 1
    record = messages[0].record
    assert record["extra"]["module"] == "SRA活动"
    assert record["exception"].type is error_type
    assert record["exception"].traceback is not None
    for text in (log_path.read_text(encoding="utf-8"), str(messages[0])):
        assert record["extra"]["module"] in text
        assert error_type.__name__ in text
        assert "Traceback" in text
