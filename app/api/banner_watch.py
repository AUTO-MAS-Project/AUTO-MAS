# SPDX-License-Identifier: AGPL-3.0-or-later
"""游戏日历卡池订阅接口。"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl

from app.core import BannerWatch
from app.core.banner_watch.state import SubscriptionConflict

router = APIRouter(prefix="/api/banner-watch", tags=["BannerWatch"])

CatalogId = Annotated[str, Field(pattern=r"^[a-z0-9_-]{1,32}$")]


class BannerRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game: CatalogId
    server: CatalogId


class BannerSubscriptionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriptions: list[BannerRegion] = Field(max_length=32)
    subscriptionRevision: int = Field(ge=0, strict=True)


class BannerServer(BaseModel):
    id: str
    name: str
    covered: bool
    managed: bool


class BannerGame(BaseModel):
    id: str
    name: str
    servers: list[BannerServer]


class CalendarBanner(BaseModel):
    id: str
    game: CatalogId
    server: CatalogId
    title: str
    kind: str
    start_mode: Literal["scheduled", "after_maintenance", "tbd"]
    starts_at: AwareDatetime | None
    ends_at: AwareDatetime | None
    end_kind: Literal["known", "permanent", "unknown"] = "unknown"
    confirmed_open_at: AwareDatetime | None
    official_url: HttpUrl
    verified_at: AwareDatetime
    status: Literal["pending", "announced", "open", "ended", "cancelled"]
    stale: bool


class BannerSourceStatus(BaseModel):
    game: CatalogId
    server: CatalogId
    last_success_at: AwareDatetime | None
    error: str | None


class BannerWatchOut(BaseModel):
    games: list[BannerGame]
    subscriptions: list[BannerRegion]
    subscriptionRevision: int
    banners: list[CalendarBanner]
    sources: list[BannerSourceStatus]
    hasNotificationChannels: bool


@router.get("", response_model=BannerWatchOut, operation_id="getBannerWatch")
async def get_banner_watch() -> BannerWatchOut:
    return BannerWatchOut.model_validate(await BannerWatch.snapshot())


@router.put(
    "/subscriptions",
    response_model=BannerWatchOut,
    operation_id="updateBannerSubscriptions",
)
async def put_banner_subscriptions(request: BannerSubscriptionsIn) -> BannerWatchOut:
    regions = {(region.game, region.server) for region in request.subscriptions}
    if len(regions) != len(request.subscriptions):
        raise HTTPException(status_code=422, detail="区服不能重复")
    try:
        return BannerWatchOut.model_validate(
            await BannerWatch.subscribe(regions, request.subscriptionRevision)
        )
    except SubscriptionConflict as error:
        raise HTTPException(
            status_code=409, detail="关注设置已变更，请刷新后重试"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
