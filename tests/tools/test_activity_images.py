"""活动图片的来源限制、磁盘缓存、共享任务与取消回收。"""

import asyncio
import hashlib
import io
import os
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from PIL import Image

from app.tools import bluearchive_activity_source as ba
from app.tools import endfield_images as end

REAL_CLIENT = httpx.AsyncClient
URL = end.ENDFIELD_VERSION_ART_URL


def picture():
    data = io.BytesIO()
    Image.new("RGBA", (2640, 1920), (1, 2, 3, 0)).save(data, "PNG")
    return data.getvalue()


def cache_path(root, url=URL):
    return root / (hashlib.sha256(url.encode()).hexdigest()[:20] + ".jpg")


@pytest.fixture
def image_http(monkeypatch):
    def install(handler):
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: REAL_CLIENT(
                transport=httpx.MockTransport(handler), **kwargs
            ),
        )

    return install


@pytest_asyncio.fixture(autouse=True)
async def isolated_images(monkeypatch, tmp_path):
    monkeypatch.setattr(end, "ENDFIELD_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(end, "_endfield_version_cache", None)
    monkeypatch.setattr(end, "_image_download_tasks", {})
    monkeypatch.setattr(end, "_background_tasks", set())
    yield
    tasks = set(end._image_download_tasks.values()) | end._background_tasks
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module,url",
    [
        (ba, "https://cdnimg-v2.gamekee.com/a.png"),
        (ba, "https://resource.starrailassistant.top/a.jpg"),
        (end, URL),
        (end, "https://web.hycdn.cn/a.png"),
    ],
)
async def test_allowlisted_images_are_fetched(module, url, image_http):
    def respond(request):
        assert str(request.url) == url
        if module is ba:
            assert request.headers["referer"] == ba.GAMEKEE_HEADERS["Referer"]
            assert request.headers["game-alias"] == "ba"
        return httpx.Response(
            200,
            content=picture(),
            headers={"content-type": "image/png; charset=binary"},
        )

    image_http(respond)
    if module is ba:
        content, media = await ba.fetch_bluearchive_image(url)
        assert content == picture() and media == "image/png"
    else:
        path = await end.fetch_image(url)
        with Image.open(path) as image:
            assert image.format == "JPEG" and image.mode == "RGB"
            assert image.size == (1300, 945)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module,host", [(ba, "cdnimg-v2.gamekee.com"), (end, "data.akedata.wiki")]
)
@pytest.mark.parametrize(
    "template",
    [
        "http://{host}/a",
        "https://{host}.evil.test/a",
        "https://{host}@127.0.0.1/a",
        "file://{host}/a",
        "https://127.0.0.1/a",
    ],
)
async def test_disallowed_images_never_reach_network(
    module, host, template, image_http
):
    def unexpected(request):
        pytest.fail("disallowed image requested")

    image_http(unexpected)
    fetch = ba.fetch_bluearchive_image if module is ba else end.fetch_image
    with pytest.raises(module.ImageSourceNotAllowed):
        await fetch(template.format(host=host))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,media,body",
    [
        (200, "text/html", b"<html>error</html>"),
        (200, "", b"x"),
        (200, "image/png", b"x" * (8 * 1024 * 1024 + 1)),
        (302, "image/png", b"x"),
        (503, "image/png", b"x"),
    ],
    ids=["html", "missing-type", "oversize", "redirect", "unavailable"],
)
async def test_bluearchive_rejects_non_images_oversize_errors_and_redirects(
    image_http, status, media, body
):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            status,
            content=body,
            headers={"content-type": media, "location": "https://127.0.0.1/private"},
        )

    image_http(respond)
    with pytest.raises(ba.ImageUnavailable):
        await ba.fetch_bluearchive_image("https://cdnimg-v2.gamekee.com/a")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_endfield_disk_ttl_stale_fallback_and_cache_pruning(
    image_http, tmp_path, monkeypatch
):
    path = cache_path(tmp_path)
    path.write_bytes(b"previous")
    image_http(lambda request: pytest.fail("fresh cache requested"))
    assert await end.fetch_image(URL) == path
    old = end.time.time() - 6 * 3600 - 1
    os.utime(path, (old, old))
    image_http(lambda request: httpx.Response(503))
    assert (await end.fetch_image(URL)).read_bytes() == b"previous"
    assert path.stat().st_mtime == old
    path.unlink()
    with pytest.raises(end.ImageUnavailable):
        await end.fetch_image(URL)
    image_http(lambda request: httpx.Response(200, content=picture()))
    monkeypatch.setattr(end, "ENDFIELD_IMAGE_CACHE_MAX_FILES", 2)
    for index in range(3):
        stale = tmp_path / f"old-{index}.jpg"
        stale.write_bytes(b"x")
        os.utime(stale, (old + index, old + index))
    await end.fetch_image(URL)
    assert {p.name for p in tmp_path.glob("*.jpg")} == {path.name, "old-2.jpg"}
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.asyncio
async def test_prewarm_and_concurrent_request_share_download_after_cancellation(
    image_http, monkeypatch, tmp_path
):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def respond(request):
        calls.append(request)
        entered.set()
        await release.wait()
        return httpx.Response(200, content=picture())

    image_http(respond)
    monkeypatch.setattr(
        end, "_endfield_version_name", AsyncMock(return_value="version")
    )
    assert await end.fetch_version_art() == {"url": URL, "name": "version"}
    await asyncio.wait_for(entered.wait(), 2)
    first = asyncio.create_task(end.fetch_image(URL))
    second = asyncio.create_task(end.fetch_image(URL))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert len(end._image_download_tasks) == 1
    release.set()
    assert await asyncio.wait_for(second, 3) == cache_path(tmp_path)
    await asyncio.gather(*end._background_tasks)
    await asyncio.sleep(0)
    assert len(calls) == 1
    assert end._image_download_tasks == {} and end._background_tasks == set()


@pytest.mark.asyncio
async def test_failed_or_timed_out_download_is_collected_and_retryable(
    image_http, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, content=picture())

    image_http(blocked)
    monkeypatch.setattr(end, "ENDFIELD_IMAGE_FETCH_TIMEOUT", 0.02)
    with pytest.raises(end.ImageUnavailable) as error:
        await end.fetch_image(URL)
    assert isinstance(error.value.__cause__, TimeoutError)
    await asyncio.sleep(0)
    assert not end._image_download_tasks
    monkeypatch.setattr(end, "ENDFIELD_IMAGE_FETCH_TIMEOUT", 30)
    release.set()
    path = await end.fetch_image(URL)
    assert path.exists()
    await asyncio.sleep(0)
    assert not end._image_download_tasks


@pytest.mark.asyncio
async def test_all_waiters_cancelled_download_still_finishes_and_is_collected(
    image_http, tmp_path
):
    entered, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, content=picture())

    image_http(respond)
    waiter = asyncio.create_task(end.fetch_image(URL))
    await asyncio.wait_for(entered.wait(), 2)
    download = end._image_download_tasks[URL]
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not download.cancelled()
    release.set()
    await asyncio.wait_for(download, 3)
    await asyncio.sleep(0)
    assert cache_path(tmp_path).exists() and not end._image_download_tasks


@pytest.mark.asyncio
async def test_version_name_ttl_last_success_and_failed_prewarm_cleanup(
    image_http, monkeypatch
):
    clock = [1000.0]
    monkeypatch.setattr(end.time, "time", lambda: clock[0])
    calls = []

    def success(request):
        calls.append(request)
        return httpx.Response(200, text="other「name」「雪凇幽梦」版本更新说明")

    image_http(success)
    assert await end._endfield_version_name() == "雪凇幽梦"
    clock[0] += 3599
    assert await end._endfield_version_name() == "雪凇幽梦" and len(calls) == 1
    clock[0] += 1
    image_http(lambda request: httpx.Response(200, text="no matching name"))
    assert await end._endfield_version_name() == "雪凇幽梦"
    assert end._endfield_version_cache[0] == 1000.0
    image_http(lambda request: httpx.Response(503))
    assert await end._endfield_version_name() == "雪凇幽梦"
    await end.fetch_version_art()
    await asyncio.gather(*end._background_tasks)
    await asyncio.sleep(0)
    assert not end._background_tasks and not end._image_download_tasks


def test_thumbnail_failure_does_not_replace_cache_or_leave_partial_file(
    monkeypatch, tmp_path
):
    path = tmp_path / "cache.jpg"
    path.write_bytes(b"previous")
    monkeypatch.setattr(
        Image.Image,
        "save",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    # 编码输入先行生成，失败仅发生在缩图写盘。
    with pytest.raises(OSError):
        end._write_thumbnail(PNG, path)
    assert path.read_bytes() == b"previous"
    assert not list(tmp_path.glob("*.part"))


PNG = picture()


@pytest.mark.asyncio
async def test_bluearchive_image_cancellation_propagates(image_http):
    async def cancelled(request):
        raise asyncio.CancelledError

    image_http(cancelled)
    with pytest.raises(asyncio.CancelledError):
        await ba.fetch_bluearchive_image("https://cdnimg-v2.gamekee.com/a.png")


@pytest.mark.asyncio
async def test_endfield_redirect_and_corrupt_image_use_only_stale_cache(
    image_http, tmp_path
):
    calls = []

    def redirect(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    image_http(redirect)
    with pytest.raises(end.ImageUnavailable):
        await end.fetch_image(URL)
    assert len(calls) == 1
    path = cache_path(tmp_path)
    path.write_bytes(b"previous")
    old = end.time.time() - 6 * 3600 - 1
    os.utime(path, (old, old))
    image_http(lambda request: httpx.Response(200, content=b"broken png"))
    assert (await end.fetch_image(URL)).read_bytes() == b"previous"
    assert not list(tmp_path.glob("*.part"))
