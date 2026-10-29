#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

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


from typing import (
    Any,
    Dict,
    Literal,
)

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    model_validator,
)

from app.core import Config
from app.core.game_calendar_host import GameCalendar
from app.core.taskboard_state import (
    load_state,
    save_archive,
    save_selection,
    set_done_at,
)
from app.models.schema import (
    BlueArchiveActivityIn,
    ComboBoxItem,
    ComboBoxOut,
    EmulatorDeleteIn,
    OutBase,
    PlanComboxConsumer,
)
from app.models.taskboard import (
    TaskboardArchivedActivity,
    TaskboardDoneRecord,
    TaskboardState,
)
from app.tools import (
    arknights_activity,
    bluearchive_activity_source,
    endfield_images,
    stella_official,
)
from app.tools.azurlane_activity import fetch_azurlane_activities
from app.tools.bluearchive_activity_source import (
    fetch_bluearchive_activities,
)
from app.utils import get_logger


class GameCalendarActivityInfo(BaseModel):
    name: str = Field(..., min_length=1, max_length=500, description="活动名称")
    startTime: AwareDatetime = Field(..., description="活动开始时间，包含时区")
    endTime: AwareDatetime = Field(..., description="活动结束时间，包含时区")

    @model_validator(mode="after")
    def validate_period(self):
        if not self.name.strip() or self.endTime <= self.startTime:
            raise ValueError("活动名称不能为空，结束时间必须晚于开始时间")
        return self


class GameCalendarActivityUpdateIn(GameCalendarActivityInfo):
    completed: bool = Field(..., description="是否由用户标记为已完成")


class GameCalendarActivityScopeIn(BaseModel):
    game: Literal[
        "endfield",
        "starrail",
        "genshin",
        "zenless",
        "wutheringwaves",
        "nte",
        "reverse1999",
        "bluearchive",
        "arknights",
        "stellasora",
        "infinitynikki",
        "azurlane",
    ] = Field(..., description="首页游戏标识")
    server: Literal["cn", "jp", "global"] = Field(
        default="cn", description="碧蓝档案服务器，其它游戏忽略此字段"
    )


class GameCalendarActivityCompletionIn(
    GameCalendarActivityScopeIn, GameCalendarActivityUpdateIn
):
    pass


class GameCalendarActivitiesOut(OutBase):
    data: list[GameCalendarActivityInfo] = Field(
        default_factory=list, description="用户已完成且未过期的活动"
    )


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


class PlanComboxIn(BaseModel):
    consumer: PlanComboxConsumer = Field(..., description="计划表消费方")


class TaskboardStateOut(OutBase):
    data: TaskboardState = Field(default_factory=TaskboardState)


class TaskboardSelectionIn(BaseModel):
    games: list[str] = Field(
        default_factory=list, max_length=100, description="勾选的游戏"
    )


class TaskboardArchiveIn(BaseModel):
    archived: list[TaskboardArchivedActivity] = Field(
        default_factory=list, max_length=2000, description="已归档活动的展示缓存"
    )


class TaskboardDoneAtIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=400, description="完成日期记录键")
    record: TaskboardDoneRecord | None = Field(
        default=None, description="为空表示删除该记录"
    )


router = APIRouter(prefix="/api/info", tags=["信息获取"])
logger = get_logger("信息获取 API")


@router.get(
    "/activity/completions",
    tags=["Get"],
    summary="获取游戏已完成活动",
    response_model=GameCalendarActivitiesOut,
)
async def get_activity_completions(
    scope: GameCalendarActivityScopeIn = Depends(),
) -> GameCalendarActivitiesOut:
    try:
        activities = await GameCalendar.completed_activities(
            game=scope.game, server=scope.server
        )
        return GameCalendarActivitiesOut(
            data=[
                GameCalendarActivityInfo(
                    name=item.name, startTime=item.start_at, endTime=item.end_at
                )
                for item in activities
            ]
        )
    except (OSError, ValueError, TypeError):
        logger.exception("读取游戏活动完成状态失败")
        return GameCalendarActivitiesOut(
            code=500, status="error", message="读取活动完成状态失败"
        )


@router.post(
    "/activity/completions",
    tags=["Set"],
    summary="设置游戏活动完成状态",
    response_model=OutBase,
)
async def set_activity_completion(
    payload: GameCalendarActivityCompletionIn,
) -> OutBase:
    try:
        await GameCalendar.set_activity_completed(
            game=payload.game,
            server=payload.server,
            name=payload.name,
            start=payload.startTime,
            end=payload.endTime,
            completed=payload.completed,
        )
        return OutBase()
    except ValueError as error:
        return OutBase(code=400, status="error", message=str(error))
    except (OSError, TypeError):
        logger.exception("保存游戏活动完成状态失败")
        return OutBase(code=500, status="error", message="保存活动完成状态失败")


## 任务台状态：文件读写与裁剪放在 app.core.taskboard_state，这里只做参数与错误转换。
@router.get(
    "/taskboard/state",
    tags=["Get"],
    summary="获取任务台状态",
    response_model=TaskboardStateOut,
)
async def get_taskboard_state() -> TaskboardStateOut:
    try:
        return TaskboardStateOut(data=await load_state())
    except (OSError, TypeError, ValueError):
        logger.exception("读取任务台状态失败")
        return TaskboardStateOut(code=500, status="error", message="读取任务台状态失败")


@router.put(
    "/taskboard/selection",
    tags=["Set"],
    summary="保存任务台勾选的游戏",
    response_model=OutBase,
)
async def set_taskboard_selection(payload: TaskboardSelectionIn) -> OutBase:
    try:
        await save_selection(payload.games)
        return OutBase()
    except (OSError, TypeError, ValueError):
        logger.exception("保存任务台游戏选择失败")
        return OutBase(code=500, status="error", message="保存任务台游戏选择失败")


@router.put(
    "/taskboard/archive",
    tags=["Set"],
    summary="保存任务台归档缓存",
    response_model=OutBase,
)
async def set_taskboard_archive(payload: TaskboardArchiveIn) -> OutBase:
    try:
        await save_archive(payload.archived)
        return OutBase()
    except (OSError, TypeError, ValueError):
        logger.exception("保存任务台归档失败")
        return OutBase(code=500, status="error", message="保存任务台归档失败")


@router.put(
    "/taskboard/done-at",
    tags=["Set"],
    summary="记录或删除任务台的完成日期",
    response_model=OutBase,
)
async def set_taskboard_done_at(payload: TaskboardDoneAtIn) -> OutBase:
    try:
        await set_done_at(payload.key, payload.record)
        return OutBase()
    except (OSError, TypeError, ValueError):
        logger.exception("保存任务台完成日期失败")
        return OutBase(code=500, status="error", message="保存任务台完成日期失败")


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
        logger.opt(exception=True).warning(
            f"get_git_version失败: {type(e).__name__}: {e}"
        )
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

    from app.core.maa_stage import maa_stage_service

    try:
        raw_data = await maa_stage_service.get_stage_info(stage.type)
        data = (
            [ComboBoxItem(**item) for item in raw_data if isinstance(item, dict)]
            if raw_data
            else []
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_stage_combox失败: {type(e).__name__}: {e}"
        )
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
        raw_data = await Config.get_script_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_script_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
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
        raw_data = await Config.get_task_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_task_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/plan",
    tags=["Get"],
    summary="获取可选计划下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_plan_combox(plan: PlanComboxIn = Body(...)) -> ComboBoxOut:

    try:
        raw_data = await Config.get_plan_combox(plan.consumer)
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_plan_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator",
    tags=["Get"],
    summary="获取可选模拟器下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_combox() -> ComboBoxOut:

    try:
        raw_data = await Config.get_emulator_combox()
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_emulator_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/combox/emulator/devices",
    tags=["Get"],
    summary="获取可选模拟器多开实例下拉框信息",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_emulator_devices_combox(
    emulator: EmulatorDeleteIn = Body(...),
) -> ComboBoxOut:
    try:
        raw_data = await Config.get_emulator_devices_combox(emulator.emulatorId)
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_emulator_devices_combox失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
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
        logger.opt(exception=True).warning(
            f"get_notice_info失败: {type(e).__name__}: {e}"
        )
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
        await Config.setting.update(
            type(Config.setting).model_validate({"Data": {"IfShowNotice": False}}),
            check_visibility=False,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"confirm_notice失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


# @router.post(
#     "/apps_info", summary="获取可下载应用信息", response_model=InfoOut, status_code=200
# )
# async def get_apps_info() -> InfoOut:

#     try:
#         data = await Config.get_server_info("apps_info")
#     except Exception as e:
#         return InfoOut(
#             code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data={}
#         )
#     return InfoOut(data=data)


@router.post(
    "/get/overview",
    tags=["Get"],
    summary="信息总览",
    response_model=InfoOut,
    status_code=200,
)
async def get_overview(
    refresh: bool = False,
) -> InfoOut:
    from app.core.maa_stage import maa_stage_service

    try:
        if refresh:
            await maa_stage_service.get_stage(refresh=True)
        stage_by_server = {
            server: await maa_stage_service.get_stage_info("Info", server=server)
            for server in (
                "Official",
                "Bilibili",
                "YoStarEN",
                "YoStarJP",
                "YoStarKR",
                "txwy",
            )
        }
        proxy = await Config.get_proxy_overview()
    except Exception as e:
        logger.opt(exception=True).warning(f"get_overview失败: {type(e).__name__}: {e}")
        return InfoOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={
                "Stage": [],
                "Proxy": [],
            },
        )
    return InfoOut(
        data={
            "Stage": stage_by_server["Official"],
            "StageByServer": stage_by_server,
            "Proxy": proxy,
        }
    )


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

    共享取数模块负责 GameKee 请求与 SRA 兜底，这里只包装响应。
    前端继续接收 GameKee 字段，活动筛选与展示格式保持不变。
    """

    try:
        data = await fetch_bluearchive_activities(
            line_type=payload.line_type, page=payload.page, page_size=payload.page_size
        )
    except Exception as e:
        return InfoOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )
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

    try:
        content, media_type = await bluearchive_activity_source.fetch_bluearchive_image(
            url
        )
    except bluearchive_activity_source.ImageSourceNotAllowed as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except bluearchive_activity_source.ImageUnavailable as error:
        raise HTTPException(status_code=502, detail="图片获取失败") from error
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get(
    "/endfield/version-art",
    tags=["Get"],
    summary="获取终末地版本图与版本名",
    response_model=InfoOut,
    status_code=200,
)
async def get_endfield_version_art() -> InfoOut:
    """终末地的版本图地址与版本名（图是固定地址，前端再走图片中转取回）。

    给出地址的同时顺手把那张图热进缓存：它有 5MB 级，前端拿到地址才现下载的话，
    横幅要空着等好几秒。
    """

    return InfoOut(data=await endfield_images.fetch_version_art())


@router.get(
    "/endfield/image",
    tags=["Get"],
    summary="获取终末地活动图片（缩放后转发）",
)
async def get_endfield_image(url: str = Query(..., description="图片地址")) -> Response:
    """把终末地的活动大图缩到横幅宽度再交给前端。"""

    try:
        cache_file = await endfield_images.fetch_image(url)
    except endfield_images.ImageSourceNotAllowed as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except endfield_images.ImageUnavailable as error:
        raise HTTPException(status_code=502, detail="图片获取失败") from error
    return FileResponse(
        cache_file,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


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

    try:
        data = await arknights_activity.fetch_arknights_activities()
    except Exception as e:
        return InfoOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data={}
        )
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

    data = await stella_official.fetch_stella_activities()
    if data is None:
        return InfoOut(
            code=500, status="error", message="星塔旅人活动数据暂不可用", data={}
        )
    return InfoOut(data=data)


@router.post(
    "/azurlane/activity",
    tags=["Get"],
    summary="获取碧蓝航线活动数据（BWIKI 中转）",
    response_model=InfoOut,
    status_code=200,
)
async def get_azurlane_activity() -> InfoOut:
    """取回碧蓝航线的活动一览。

    数据来自碧蓝海事局 WIKI 的活动日历页：官方站与日服站都是纯前端渲染，HTML 里
    没有活动内容，GameKee 也没开放这条线，能稳定拿到的只有这份维基文本。日历只写
    月日，时刻由取数模块按当天 10:00 开始、23:59 结束落到北京时间。

    Returns:
        InfoOut: ``{"activities": [...]}``；取不到时返回 ``code=500`` 的错误信封。
    """

    try:
        data = await fetch_azurlane_activities()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_azurlane_activity失败: {type(e).__name__}: {e}"
        )
        data = None

    if data is None:
        return InfoOut(
            code=500,
            status="error",
            message="碧蓝航线活动数据暂不可用",
            data={},
        )

    return InfoOut(data=data)
