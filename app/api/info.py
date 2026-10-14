#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright (c) 2024-2025 DLmaster361
#   Copyright (c) 2025 MoeSnowyFox
#   Copyright (c) 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.api import OutBase
from app.core import Config, TaskDispatcher
from app.core.history import history_store
from app.models.task import TaskMode

router = APIRouter(prefix="/api/info", tags=["信息获取"])


class InfoOut(OutBase):
    data: Dict[str, Any] = Field(..., description="收到的服务器数据")


class VersionOut(OutBase):
    if_need_update: bool = Field(..., description="后端代码是否需要更新")
    current_time: str = Field(..., description="后端代码当前时间戳")
    current_hash: str = Field(..., description="后端代码当前哈希值")


class NoticeOut(OutBase):
    if_need_show: bool = Field(..., description="是否需要显示公告")
    data: Dict[str, str] = Field(
        ..., description="公告信息, key为公告标题, value为公告内容"
    )


class ComboBoxItem(BaseModel):
    label: str = Field(..., description="展示值")
    value: Optional[str] = Field(..., description="实际值")
    supported_modes: Optional[List[TaskMode]] = Field(
        default=None, description="任务项支持的执行模式；非脚本项为空"
    )


class ComboBoxOut(OutBase):
    data: List[ComboBoxItem] = Field(..., description="下拉框选项")


class GetStageIn(BaseModel):
    type: Literal[
        "User",
        "Today",
        "ALL",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ] = Field(
        ...,
        description="选择的日期类型, Today为当天, ALL为包含当天未开放关卡在内的所有项",
    )


class EmulatorDeleteIn(BaseModel):
    emulatorId: str = Field(..., description="游戏配置 uid")


@router.post(
    "/version",
    tags=["Get"],
    summary="获取后端git版本信息",
    response_model=VersionOut,
    status_code=200,
)
async def get_git_version() -> VersionOut:

    try:
        is_latest, commit_hash, commit_time = await Config.get_git_version()
    except Exception as e:
        return VersionOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_update=False,
            current_time="unknown",
            current_hash="unknown",
        )
    return VersionOut(
        if_need_update=not is_latest,
        current_time=commit_time,
        current_hash=commit_hash,
    )


@router.post(
    "/combox/stage",
    tags=["Get"],
    summary="获取关卡号下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_stage_combox(
    stage: GetStageIn = Body(..., description="关卡号类型"),
) -> ComboBoxOut:

    try:
        raw_data = await Config.get_stage_info(stage.type)
        data = (
            [ComboBoxItem(**item) for item in raw_data if isinstance(item, dict)]
            if raw_data
            else []
        )
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/script",
    tags=["Get"],
    summary="获取脚本下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_script_combox() -> ComboBoxOut:
    try:
        data = [
            ComboBoxItem(label=entry.info.name or str(uid), value=str(uid))
            for uid, entry in Config.ScriptConfig.items()
        ]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/task",
    tags=["Get"],
    summary="获取可选任务下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_task_combox() -> ComboBoxOut:
    try:
        data = [
            ComboBoxItem(
                label=f"{entry.info.mode}:{uid}",
                value=str(uid),
                supported_modes=[entry.info.mode],
            )
            for uid, entry in TaskDispatcher.running_items()
        ]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/plan",
    tags=["Get"],
    summary="获取可选计划下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_plan_combox(
    body: dict = Body(default_factory=dict),
) -> ComboBoxOut:
    try:
        script_type = (body or {}).get("scriptType") or (body or {}).get("script_type")
        data = []
        for uid, entry in Config.PlanConfig.items():
            if script_type and type(entry).__name__ != script_type:
                continue
            data.append(
                ComboBoxItem(label=entry.info.name or str(uid), value=str(uid))
            )
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator",
    tags=["Get"],
    summary="获取可选游戏/模拟器下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_combox() -> ComboBoxOut:
    try:
        data = [
            ComboBoxItem(label=entry.info.name or str(uid), value=str(uid))
            for uid, entry in Config.GameConfig.items()
        ]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator/devices",
    tags=["Get"],
    summary="获取可选游戏多开实例下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_devices_combox(
    emulator: EmulatorDeleteIn = Body(...),
) -> ComboBoxOut:
    try:
        game = Config.GameConfig[UUID(emulator.emulatorId)]
        data = [
            ComboBoxItem(
                label=dev.info.name or str(dev.uid),
                value=str(dev.uid),
            )
            for dev in game.devices.values()
        ]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/notice/get",
    tags=["Get"],
    summary="获取通知信息",
    response_model=NoticeOut,
    status_code=200,
)
async def get_notice_info() -> NoticeOut:

    try:
        if_need_show, data = await Config.get_notice()
    except Exception as e:
        return NoticeOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_show=False,
            data={},
        )
    return NoticeOut(if_need_show=if_need_show, data=data)


@router.post(
    "/notice/confirm",
    tags=["Action"],
    summary="确认通知",
    response_model=OutBase,
    status_code=200,
)
async def confirm_notice() -> OutBase:

    try:
        Config.setting.data.if_show_notice = False
        await Config.setting.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webconfig",
    tags=["Get"],
    summary="获取配置分享中心的配置信息",
    response_model=InfoOut,
    status_code=200,
)
async def get_web_config() -> InfoOut:

    try:
        data = await Config.get_web_config()
    except Exception as e:
        return InfoOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data={}
        )
    return InfoOut(data={"WebConfig": data})


@router.post(
    "/get/overview",
    tags=["Get"],
    summary="信息总览",
    response_model=InfoOut,
    status_code=200,
)
async def get_overview() -> InfoOut:
    try:
        stage = await Config.get_stage_info("Info")
        proxy = history_store.get_overview()
    except Exception as e:
        return InfoOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={"Stage": [], "Proxy": []},
        )
    return InfoOut(data={"Stage": stage, "Proxy": proxy})


# ==================== 主页活动与图片中转（沿用原有只读服务） ====================

import asyncio
import hashlib
import io
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import httpx
from fastapi import Body, HTTPException, Query
from fastapi.responses import FileResponse, Response
from app.models.schema import BlueArchiveActivityIn
from app.tools.sra_activity import fetch_sra_activities
from app.tools.stella_official import classify_activity_name, fetch_official_activities
from app.utils import get_logger

logger = get_logger("信息获取 API")


GAMEKEE_ACTIVITY_URL = "https://www.gamekee.com/v1/activity/page-list"


GAMEKEE_HEADERS = {
    "game-alias": "ba",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.gamekee.com/ba/huodong/16",
}


GAMEKEE_SERVER_IDS = {"JP": 15, "GLOBLE": 17, "CN": 16}


SRA_BLUEARCHIVE_IDS = {"JP": "ba-jp", "GLOBLE": "ba-global", "CN": "ba-cn"}


BLUEARCHIVE_IMAGE_HOSTS = ("cdnimg-v2.gamekee.com", "resource.starrailassistant.top")


BLUEARCHIVE_IMAGE_MAX_BYTES = 8 * 1024 * 1024


PRTS_ACTIVITY_URL = "https://prts.wiki/w/%E6%B4%BB%E5%8A%A8%E4%B8%80%E8%A7%88"


PRTS_HEADERS = {"User-Agent": "AUTO-MAS"}


ARKNIGHTS_CACHE_TTL = 600


ARKNIGHTS_RECENT_WINDOW_DAYS = 14


_arknights_cache: tuple[float, dict] | None = None


BLUEARCHIVE_CACHE_TTL = 600


BLUEARCHIVE_CACHE_MAX_ENTRIES = 32


_bluearchive_cache: dict[str, tuple[float, dict]] = {}


def _prune_bluearchive_cache(now: float) -> None:
    """先清掉过期项，仍超出上限时按写入时间淘汰最旧的。"""

    for key in [
        k for k, v in _bluearchive_cache.items() if now - v[0] >= BLUEARCHIVE_CACHE_TTL
    ]:
        _bluearchive_cache.pop(key, None)

    while len(_bluearchive_cache) >= BLUEARCHIVE_CACHE_MAX_ENTRIES:
        oldest = min(_bluearchive_cache, key=lambda key: _bluearchive_cache[key][0])
        _bluearchive_cache.pop(oldest, None)


def _epoch_seconds(value: str) -> int:
    """ISO 时间串 → Unix 秒；解析不出来返回 0。"""

    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return 0


def _to_gamekee_rows(activities: list[dict[str, object]]) -> list[dict[str, object]]:
    """把 SRA 的活动条目换成 GameKee 表的字段形状。

    前端只认 GameKee 那一套（title / activity_kind_name / begin_at…），照着拼一份
    省得让前端认识第二套数据源；SRA 已经滤掉非活动条目，分类固定写「活动」。
    """

    rows: list[dict[str, object]] = []
    for item in activities:
        name = str(item.get("name") or "").strip()
        begin = _epoch_seconds(str(item.get("startTime") or ""))
        end = _epoch_seconds(str(item.get("endTime") or ""))
        if not name or not begin or not end:
            continue
        rows.append(
            {
                "title": name,
                "picture": str(item.get("cover") or ""),
                "description": str(item.get("description") or ""),
                "activity_kind_name": "活动",
                "begin_at": begin,
                "end_at": end,
            }
        )
    return rows


@router.post(
    "/bluearchive/activity",
    tags=["Get"],
    summary="获取碧蓝档案活动数据（GameKee 中转）",
    response_model=InfoOut,
    status_code=200,
)
async def get_bluearchive_activity(
    payload: BlueArchiveActivityIn = Body(...),
) -> InfoOut:
    """按服务器取回碧蓝档案的活动。

    这里只做转发：把 GameKee 的响应原样交给前端，分类筛选与格式转换都由前端完成。
    之所以要绕一道后端，一是那个接口认自定义头、二是响应没给跨域头，浏览器直连取不到。

    GameKee 取不到时改用 SRA 托管的那份：那一份已经筛掉非活动条目，这里换成 GameKee
    的字段形状再交给前端，省得让前端认识第二套数据源。
    """

    cache_key = f"{payload.line_type}:{payload.page}:{payload.page_size}"
    cached = _bluearchive_cache.get(cache_key)
    if cached is not None and time.time() - cached[0] < BLUEARCHIVE_CACHE_TTL:
        return InfoOut(data=cached[1])

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                GAMEKEE_ACTIVITY_URL,
                params={
                    "serverId": GAMEKEE_SERVER_IDS[payload.line_type],
                    "page_no": payload.page,
                    "limit": payload.page_size,
                    "status": 0,
                    "importance": 0,
                    "sort": -1,
                    "keyword": "",
                },
                headers=GAMEKEE_HEADERS,
            )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise ValueError(f"GameKee 返回 {data.get('code')}: {data.get('msg')}")
    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取碧蓝档案活动数据失败({payload.line_type}): {type(e).__name__}: {e}"
        )
        ## SRA 一次给全，翻页请求不再重复给同一批活动
        if payload.page > 1:
            return InfoOut(data={"code": 0, "data": []})
        fallback = await fetch_sra_activities(SRA_BLUEARCHIVE_IDS[payload.line_type])
        if fallback is None:
            return InfoOut(
                code=500,
                status="error",
                message=f"{type(e).__name__}: {str(e)}",
                data={},
            )
        logger.info(f"碧蓝档案活动数据改用 SRA 兜底({payload.line_type})")
        data = {"code": 0, "data": _to_gamekee_rows(fallback["activities"])}

    _prune_bluearchive_cache(time.time())
    _bluearchive_cache[cache_key] = (time.time(), data)
    return InfoOut(data=data)


@router.get(
    "/bluearchive/image",
    tags=["Get"],
    summary="获取碧蓝档案活动图片（GameKee 中转）",
)
async def get_bluearchive_image(
    url: str = Query(..., description="图片地址"),
) -> Response:
    """中转 GameKee 的图片。

    那个 CDN 校验 Referer：带上它自己的站点才给图，页面直连（Referer 是本软件）会被拒。
    所以图片也由后端取回，前端只管引用这个地址。
    """

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in BLUEARCHIVE_IMAGE_HOSTS:
        raise HTTPException(status_code=400, detail="只允许中转碧蓝档案活动图片")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers=GAMEKEE_HEADERS)
        response.raise_for_status()
        ## 这个接口带着自定义头去白名单域名取东西再原样吐给前端，所以要确认拿回来的确实是图片：
        ## 上游报错时可能返回一坨 200 的 HTML，直接转发会让前端拿着垃圾当图；大小也设个上限
        media_type = response.headers.get("content-type", "").split(";")[0].strip()
        if not media_type.startswith("image/"):
            raise ValueError(f"来源不是图片: {media_type or '未给类型'}")
        if len(response.content) > BLUEARCHIVE_IMAGE_MAX_BYTES:
            raise ValueError(f"图片过大: {len(response.content)} 字节")
    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取碧蓝档案活动图片失败: {type(e).__name__}: {e}"
        )
        raise HTTPException(status_code=502, detail="图片获取失败")

    return Response(
        content=response.content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


ENDFIELD_IMAGE_HOSTS = ("data.akedata.wiki", "web.hycdn.cn")


ENDFIELD_IMAGE_WIDTH = 1300


ENDFIELD_IMAGE_CACHE_DIR = Path(tempfile.gettempdir()) / "auto-mas-image-cache"


ENDFIELD_IMAGE_CACHE_TTL = 6 * 3600


ENDFIELD_IMAGE_CACHE_MAX_FILES = 200


ENDFIELD_VERSION_ART_URL = "https://data.akedata.wiki/public/images/index/main.png"


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

    from PIL import Image

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


@router.get(
    "/endfield/version-art",
    tags=["Get"],
    summary="获取终末地版本图与版本名",
    response_model=InfoOut,
    status_code=200,
)
async def get_endfield_version_art() -> InfoOut:
    """终末地的版本图地址与版本名（图是固定地址，前端再走图片中转取回）。"""

    return InfoOut(
        data={"url": ENDFIELD_VERSION_ART_URL, "name": await _endfield_version_name()}
    )


@router.get(
    "/endfield/image",
    tags=["Get"],
    summary="获取终末地活动图片（缩放后转发）",
)
async def get_endfield_image(url: str = Query(..., description="图片地址")) -> Response:
    """把终末地的活动大图缩到横幅宽度再交给前端。"""

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ENDFIELD_IMAGE_HOSTS:
        raise HTTPException(status_code=400, detail="只允许中转终末地活动图片")

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    ENDFIELD_IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = ENDFIELD_IMAGE_CACHE_DIR / f"{digest}.jpg"
    if not _cache_is_fresh(cache_file):
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.get(url)
            response.raise_for_status()
            ## 缩图是 CPU 活，扔给线程跑，别把事件循环钉住
            await asyncio.to_thread(_write_thumbnail, response.content, cache_file)
            ## 只在新增文件时回收一次，别让每次请求都去扫一遍目录
            await asyncio.to_thread(_prune_image_cache)
        except Exception as e:
            logger.opt(exception=True).warning(
                f"获取终末地活动图片失败: {type(e).__name__}: {e}"
            )
            ## 手里还有上一版图就接着用，比直接报错强
            if not cache_file.exists():
                raise HTTPException(status_code=502, detail="图片获取失败")

    return FileResponse(
        cache_file,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


_PRTS_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)


_PRTS_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


_PRTS_END_TIME = re.compile(r'data-time="\d+,(\d+)"')


_PRTS_RENDER_TIME = re.compile(r'data-time="(\d+),\d+"')


_PRTS_START_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})")


_PRTS_NAME = re.compile(r"<a[^>]*>(.*?)</a>", re.S)


_PRTS_IMAGE = re.compile(r'src="(https://media\.prts\.wiki/[^"]+)"')


_PRTS_THUMB_WIDTH = re.compile(r"/\d+px-")


_PRTS_TAG = re.compile(r"<[^>]+>")


def _prts_text(fragment: str) -> str:
    """把一小段 HTML 压成纯文本"""

    return re.sub(r"\s+", " ", _PRTS_TAG.sub("", fragment)).strip()


def _parse_prts_activities(page: str, now: datetime) -> list[dict]:
    """从活动一览页里抽出本次活动相关的条目。"""

    horizon = now - timedelta(days=ARKNIGHTS_RECENT_WINDOW_DAYS)
    activities: list[dict] = []

    ## 页面渲染时刻：PRTS 对已经结束的活动会把结束时间填成它，这种条目直接丢掉
    render_match = _PRTS_RENDER_TIME.search(page)
    render_seconds = int(render_match.group(1)) if render_match else 0

    for row in _PRTS_ROW.findall(page):
        end_match = _PRTS_END_TIME.search(row)
        cells = _PRTS_CELL.findall(row)
        if end_match is None or len(cells) < 3:
            continue

        end = int(end_match.group(1))
        if datetime.fromtimestamp(end, timezone.utc) < horizon:
            continue

        ## 已结束的历史活动不要
        if render_seconds and abs(end - render_seconds) <= 60:
            continue

        ## 开始时间在首列（形如 2026-09-29 16:00）。data-time 的第一个值不是它，
        ## 页面上所有行的那个值都一样，是渲染时刻
        start_match = _PRTS_START_TIME.search(_prts_text(cells[0]))
        ## 活动名取单元格里的链接文本：后面还跟着状态徽标和内联脚本，直接取文本会带上它们
        name_match = _PRTS_NAME.search(cells[1])
        if start_match is None or name_match is None:
            continue

        name = _prts_text(name_match.group(1))
        if not name:
            continue

        year, month, day, hour, minute = (int(value) for value in start_match.groups())
        start_time = datetime(
            year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=8))
        )
        end_time = datetime.fromtimestamp(end, timezone(timedelta(hours=8)))
        if end_time <= start_time:
            continue

        cover = _PRTS_IMAGE.search(row)
        cover_url = _PRTS_THUMB_WIDTH.sub("/1300px-", cover.group(1)) if cover else ""

        activities.append(
            {
                "name": name,
                "kind": _prts_text(cells[2]),
                "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "cover": cover_url,
            }
        )

    activities.sort(key=lambda item: item["startTime"])
    return activities


@router.get(
    "/arknights/activity",
    tags=["Get"],
    summary="获取明日方舟活动数据（PRTS 中转）",
    response_model=InfoOut,
    status_code=200,
)
async def get_arknights_activity() -> InfoOut:
    """取回明日方舟的活动一览。

    PRTS 的页面里已经带了活动名、分类、起止时间与配图，这里解析成前端好用的形状。
    最近两周一场活动都没有是正常情况（长草期），按空列表返回并照常缓存，
    不然前端会把「没有活动」当成接口出错反复重试。

    PRTS 在部分网络下会连不上、也挡浏览器直连，真取不到时改用 SRA 托管的那份活动列表
    顶上：数据没有活动分类，卡片上会少一列标签，但至少不是空的。
    """

    global _arknights_cache

    now = datetime.now(timezone.utc)
    if (
        _arknights_cache is not None
        and time.time() - _arknights_cache[0] < ARKNIGHTS_CACHE_TTL
    ):
        return InfoOut(data=_arknights_cache[1])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(PRTS_ACTIVITY_URL, headers=PRTS_HEADERS)
        response.raise_for_status()
        data = {"activities": _parse_prts_activities(response.text, now)}
    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取明日方舟活动数据失败: {type(e).__name__}: {e}"
        )
        fallback = await fetch_sra_activities("ak")
        if fallback is None:
            return InfoOut(
                code=500,
                status="error",
                message=f"{type(e).__name__}: {str(e)}",
                data={},
            )
        logger.info("明日方舟活动数据改用 SRA 兜底")
        data = fallback

    _arknights_cache = (time.time(), data)
    return InfoOut(data=data)


@router.post(
    "/stella/activity",
    tags=["Get"],
    summary="获取星塔旅人活动数据（官网公告）",
    response_model=InfoOut,
    status_code=200,
)
async def get_stella_activity() -> InfoOut:
    """取回星塔旅人的活动一览。

    数据取自国服官网的活动公告：官网 CMS 不放开跨域、也认 Referer，所以由后端
    取回并按公告正文里的开放时间整理成与其它游戏一致的形状。

    官网取不到、或者这一次一篇活动公告都没识别出来时，改用 SRA 托管的那份顶上：
    对方的抓取在它自己的服务器上完成，用户本机到不了官网也能看到活动。那份数据没有
    分类，按本模块给星塔旅人定的判据补一个，否则前端的横幅与常驻分组会全落空。

    Returns:
        InfoOut: ``{"activities": [...]}``；两处都取不到时返回 ``code=500`` 的错误信封。
    """

    try:
        data = await fetch_official_activities()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_stella_activity失败: {type(e).__name__}: {e}"
        )
        data = None

    if data is None:
        fallback = await fetch_sra_activities("xtlr")
        if fallback is None:
            return InfoOut(
                code=500,
                status="error",
                message="星塔旅人活动数据暂不可用",
                data={},
            )
        for item in fallback["activities"]:
            item["kind"] = classify_activity_name(str(item["name"]))
        logger.info("星塔旅人活动数据改用 SRA 兜底")
        data = fallback

    return InfoOut(data=data)


