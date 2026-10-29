#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""终末地版本名、版本图预热和活动图磁盘缓存。"""

import asyncio
import hashlib
import io
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.utils import get_logger

logger = get_logger("终末地活动图片")


class ImageSourceNotAllowed(ValueError):
    """图片来源不在终末地白名单内。"""


class ImageUnavailable(RuntimeError):
    """下载失败且没有可回退的图片缓存。"""


## 终末地的活动背景图是游戏原生素材：单张 2640×1920 的 png，动辄 20MB。
## 直接让前端引用会把首页拖垮，所以在这里取回来缩到横幅宽度、转成 jpeg 再给出，
## 并且按地址落盘缓存，同一张图只处理一次。
ENDFIELD_IMAGE_HOSTS = ("data.akedata.wiki", "web.hycdn.cn")
ENDFIELD_IMAGE_WIDTH = 1300
ENDFIELD_IMAGE_CACHE_DIR = Path(tempfile.gettempdir()) / "auto-mas-image-cache"
## 活动图按地址换，版本大图却是固定地址换内容，所以缓存还得有有效期
ENDFIELD_IMAGE_CACHE_TTL = 6 * 3600
## 缓存只按地址新增、从不回收的话会一直涨：超过这个数量就按修改时间删掉最旧的一批
ENDFIELD_IMAGE_CACHE_MAX_FILES = 200
## 单张图的下载超时：原生素材动辄十几兆，给太久会把请求一直挂着，前端反而整块空着
ENDFIELD_IMAGE_FETCH_TIMEOUT = 30

## 终末地的版本大图就是 AKEData 首页顶部那张（打开网站第一眼看到的就是它），
## 比活动自带的背景图更稳定：每个版本都会换，且不依赖某个活动是否在跑
ENDFIELD_VERSION_ART_URL = "https://data.akedata.wiki/public/images/index/main.png"

## 版本名（如「雪凇幽梦」）在官网首页的公告列表里：置顶的那条就叫「XX版本更新说明」。
## 那段 JSON 在页面上是双重转义的，所以直接按标题文本匹配；书名号里不允许再出现
## 书名号，否则同一行前面的别的「」标题会被一起吞进来
ENDFIELD_OFFICIAL_URL = "https://endfield.hypergryph.com/"
ENDFIELD_VERSION_NAME = re.compile(r"「([^「」]+)」版本更新说明")
ENDFIELD_ART_CACHE_TTL = 3600
_endfield_version_cache: tuple[float, str] | None = None


async def _endfield_version_name() -> str:
    """从官网首页的公告列表里取当前版本名，取不到就返回上一次取到的值。

    官网响应慢的时候不能把事件循环钉在这里，所以用异步客户端；取数失败或没匹配到
    也不写缓存，免得一个空串把上一版的名字顶掉整整一个小时。
    """

    global _endfield_version_cache

    if (
        _endfield_version_cache is not None
        and time.time() - _endfield_version_cache[0] < ENDFIELD_ART_CACHE_TTL
    ):
        return _endfield_version_cache[1]

    name = ""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(
                ENDFIELD_OFFICIAL_URL,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
        response.raise_for_status()
        matched = ENDFIELD_VERSION_NAME.search(response.text)
        name = matched.group(1) if matched else ""
    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取终末地版本名失败: {type(e).__name__}: {e}"
        )

    if not name:
        return _endfield_version_cache[1] if _endfield_version_cache else ""

    _endfield_version_cache = (time.time(), name)
    return name


def _cache_is_fresh(path: Path) -> bool:
    """磁盘缓存还在有效期内吗（进程重启后也认，所以看文件的修改时间）"""

    try:
        return time.time() - path.stat().st_mtime < ENDFIELD_IMAGE_CACHE_TTL
    except OSError:
        return False


def _prune_image_cache() -> None:
    """图缓存超过上限时，按修改时间删掉最旧的一批。

    缩图后的 jpeg 单张几百 KB，活动一换就是新地址、旧文件再没人看，长期运行会一直涨。
    这里只保留最近用到的那些；万一删掉的正被请求，下次会重新生成。
    """

    try:
        files = sorted(
            ENDFIELD_IMAGE_CACHE_DIR.glob("*.jpg"),
            key=lambda path: path.stat().st_mtime,
        )
    except OSError:
        return
    for path in files[: max(0, len(files) - ENDFIELD_IMAGE_CACHE_MAX_FILES)]:
        path.unlink(missing_ok=True)


def _write_thumbnail(payload: bytes, target: Path) -> None:
    """把大图缩到横幅宽度、转成 jpeg，再原子地落到缓存文件上。

    Pillow 的解码与编码都是 CPU 活，调用方放进线程里跑。写入先落临时文件再改名：
    中途失败不会留下半截图片被当成有效缓存，并发请求也不会互相覆盖。
    """

    with Image.open(io.BytesIO(payload)) as image:
        picture = image.convert("RGB")
        if picture.width > ENDFIELD_IMAGE_WIDTH:
            height = round(picture.height * ENDFIELD_IMAGE_WIDTH / picture.width)
            picture = picture.resize((ENDFIELD_IMAGE_WIDTH, height), Image.LANCZOS)

        handle, temp_path = tempfile.mkstemp(
            dir=target.parent, prefix=f"{target.stem}-", suffix=".part"
        )
        os.close(handle)
        try:
            picture.save(temp_path, "JPEG", quality=85)
            os.replace(temp_path, target)
        except BaseException:
            Path(temp_path).unlink(missing_ok=True)
            raise


## 同一张图正在下载时就复用那个任务：预热与图片接口只隔几毫秒，各下一份纯属浪费流量
_image_download_tasks: dict[str, asyncio.Task[None]] = {}


async def _download_image(url: str, cache_file: Path) -> None:
    """下载 url、缩到横幅宽度再原子落盘。

    整段流程套一个总期限：httpx 的 timeout 只管各阶段，持续慢速传输能一直拖下去，
    到点就断，前端才好立刻降级。
    """

    async with asyncio.timeout(ENDFIELD_IMAGE_FETCH_TIMEOUT):
        async with httpx.AsyncClient(timeout=ENDFIELD_IMAGE_FETCH_TIMEOUT) as client:
            response = await client.get(url)
        response.raise_for_status()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(_write_thumbnail, response.content, cache_file)
    ## 真写了新文件才需要回收；两条路径共用这里，也就只扫一次目录
    await asyncio.to_thread(_prune_image_cache)


def _drop_download_task(task: asyncio.Task[None], url: str) -> None:
    """下载结束后把表项摘掉；期间已被新任务顶替的就别动。"""

    if _image_download_tasks.get(url) is task:
        _image_download_tasks.pop(url, None)


def _ensure_image_downloaded(url: str, cache_file: Path) -> asyncio.Task[None]:
    """拿到该地址正在跑的下载任务，没有就起一个。"""

    task = _image_download_tasks.get(url)
    if task is not None and not task.done():
        return task
    task = asyncio.get_running_loop().create_task(_download_image(url, cache_file))
    _image_download_tasks[url] = task
    task.add_done_callback(lambda done: _drop_download_task(done, url))
    return task


## 后台任务要留住引用，否则可能被 GC 掉（asyncio 的已知行为）
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    """把协程丢到后台跑，并把引用留住。"""

    task = asyncio.get_running_loop().create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _warm_version_art_cache() -> None:
    """把版本大图先拉进磁盘缓存。

    那张图 5MB 级，等前端拿着地址来取、后端才现下载的话，横幅要空着等好几秒。
    这里在给出地址的时候顺手热一下，前端请求图片时通常已经命中缓存。
    """

    digest = hashlib.sha256(ENDFIELD_VERSION_ART_URL.encode("utf-8")).hexdigest()[:20]
    cache_file = ENDFIELD_IMAGE_CACHE_DIR / f"{digest}.jpg"
    if _cache_is_fresh(cache_file):
        return
    try:
        ## 前端这会儿正好来取同一张图的话，等的就是同一个任务
        await asyncio.shield(
            _ensure_image_downloaded(ENDFIELD_VERSION_ART_URL, cache_file)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"预热终末地版本图失败: {type(e).__name__}: {e}"
        )


async def fetch_version_art() -> dict[str, str]:
    """返回版本图地址和版本名，并保留后台预热任务直到完成。"""
    _spawn_background(_warm_version_art_cache())
    return {"url": ENDFIELD_VERSION_ART_URL, "name": await _endfield_version_name()}


async def fetch_image(url: str) -> Path:
    """校验来源并取得缩图；取消等待不会取消共享下载。"""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ENDFIELD_IMAGE_HOSTS:
        raise ImageSourceNotAllowed("只允许中转终末地活动图片")

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    ENDFIELD_IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = ENDFIELD_IMAGE_CACHE_DIR / f"{digest}.jpg"
    if not _cache_is_fresh(cache_file):
        try:
            ## 预热可能正在下同一张图，等它就好；请求被取消时别把那个任务一起带走
            await asyncio.shield(_ensure_image_downloaded(url, cache_file))
        except Exception as e:
            logger.opt(exception=True).warning(
                f"获取终末地活动图片失败: {type(e).__name__}: {e}"
            )
            ## 手里还有上一版图就接着用，比直接报错强
            if not cache_file.exists():
                raise ImageUnavailable("图片获取失败") from e

    return cache_file
