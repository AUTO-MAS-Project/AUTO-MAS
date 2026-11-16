"""取消下载须等待真实文件操作结束，重复取消不能交还写入权。"""

import asyncio
import io
import threading

import aiofiles.threadpool
import httpx
import pytest

from app.services.common.update import transport


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "resumable", "range"])
async def test_repeated_http_cancel_waits_for_file_writer(tmp_path, monkeypatch, kind):
    entered, release, finished, closed = (threading.Event() for _ in range(4))

    class SlowFile(io.BytesIO):
        def write(self, block):
            entered.set()
            try:
                assert release.wait(5)
                return super().write(block)
            finally:
                finished.set()

        def close(self):
            if entered.is_set():
                assert finished.wait(5)
            super().close()
            closed.set()

    sink = SlowFile()
    # 在同一文件系统边界注入慢写；旧 aiofiles 和同步持有句柄的实现都经过它。
    monkeypatch.setattr(aiofiles.threadpool, "sync_open", lambda *_a, **_kw: sink)
    monkeypatch.setattr(transport, "open", lambda *_a, **_kw: sink, raising=False)
    original_client = httpx.AsyncClient
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"data")
    )
    monkeypatch.setattr(
        transport.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=mock_transport, **kwargs),
    )
    destination = tmp_path / "package"

    async def download():
        if kind == "file":
            return await transport.download_file(
                "https://example.invalid/file", destination, timeout=1
            )
        async with original_client(transport=mock_transport) as client:
            if kind == "resumable":
                return await transport.download_resumable(
                    client, "https://example.invalid/file", destination, expected_size=4
                )
            return await transport.download_range(
                client, "https://example.invalid/file", destination, offset=0, length=4
            )

    task = asyncio.create_task(download())
    try:
        for _ in range(500):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set()
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done(), (
            "download returned while its file writer was still running"
        )
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set() and closed.is_set()
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.to_thread(finished.wait, 5)
