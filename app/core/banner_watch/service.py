# SPDX-License-Identifier: AGPL-3.0-or-later
"""通过 AUTO-MAS 原有定时器和通知渠道刷新、派发卡池。"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from app.core import Config, Notify
from app.models.notification import NotifyPayload
from app.models.notification.channel import DispatchResult
from app.tools.common.game_calendar.banner_sources import SOURCES, BannerSource
from app.utils import UTC8, get_logger

from .catalog import game_catalog
from .state import GAME_SERVERS, SERVER_NAMES, BannerWatchState

logger = get_logger("卡池日历")
BANNER_REFRESH_INTERVAL_SECONDS = 15 * 60
_MAX_SOURCE_SECONDS = 75
_MAX_SEND_SECONDS = 45
_NOTICE_LIMIT = 32

_NOTICE_TITLES = {
    "announcement": "卡池官宣",
    "first_follow": "卡池关注汇总",
    "opening": "卡池开池提醒",
    "catchup": "卡池开池补发",
    "correction": "卡池公告更正",
}


def _time_text(value: str | None, default: str = "待定") -> str:
    if not value:
        return default
    return datetime.fromisoformat(value).astimezone(UTC8).strftime("%Y-%m-%d %H:%M")


def _pool_lines(banner: Mapping[str, Any], notice_kind: str) -> list[str]:
    kind = {
        "character": "角色池",
        "weapon": "武器池",
        "rerun": "复刻池",
        "permanent": "常驻池",
        "standard": "常驻池",
        "mixed": "角色与武器池",
        "banner": "卡池",
    }.get(banner["kind"], banner["kind"])
    start_mode = banner["start_mode"]
    start = banner.get("starts_at")
    end = banner.get("ends_at")
    confirmed = banner.get("confirmed_open_at")
    lines = [f"【{kind}】{banner['title']}"]
    if banner.get("status") == "cancelled":
        lines.append("官方已取消本池。")
    elif confirmed:
        lines.append(f"官方确认已开放：{_time_text(confirmed)}（北京时间）")
    elif start_mode == "after_maintenance":
        lines.append("维护后开放，等待官方确认开服。")
    elif notice_kind in {"opening", "catchup"}:
        lines.append(f"按公告已到开池时间：{_time_text(start)}（北京时间）")
    else:
        lines.append(f"开池：{_time_text(start)}（北京时间）")
    if end:
        lines.append(f"结束：{_time_text(end)}（北京时间）")
    if banner.get("end_kind") == "permanent":
        lines.append("长期开放。")
    if banner.get("stale"):
        lines.append("公告暂未复核。")
    lines.append(str(banner["official_url"]))
    return lines


def _payload(kind: str, banners: Sequence[Mapping[str, Any]]) -> NotifyPayload:
    first = banners[0]
    game = GAME_SERVERS[first["game"]][0]
    region = SERVER_NAMES[first["server"]]
    title = f"{game}（{region}）{_NOTICE_TITLES[kind]}"
    return NotifyPayload(
        title=title,
        body_title=f"【{title}】",
        text="\n\n".join("\n".join(_pool_lines(banner, kind)) for banner in banners),
        presentation="announcement",
    )


def _delivery_result(result: DispatchResult, channel: str) -> tuple[str, str | None]:
    if channel in result.succeeded_ids:
        return "delivered", None
    if not result.queued:
        if result.attempted == 0 and not result.failures:
            return "rejected", "empty_recipient"
        failure = next(
            (failure for failure in result.failures if failure.target_id == channel),
            None,
        )
        if failure is not None and failure.stage != "send":
            return "rejected", failure.stage
        if failure is not None:
            # A send error can follow a partial multi-message delivery or an
            # accepted HTTP request whose response did not reach the sender.
            return "unknown", failure.kind
    return "unknown", "missing_receipt"


class _BannerWatch:
    def __init__(self) -> None:
        self._state: BannerWatchState | None = None
        # Results may arrive during delivery. Commit a correction or preference
        # change between channel claims, never between a claim and its send.
        self._mutation = asyncio.Lock()
        self._source_limit = asyncio.Semaphore(4)
        self._last_minute: int | None = None

    @property
    def state(self) -> BannerWatchState:
        if self._state is None:
            self._state = BannerWatchState(
                Config.data_path / "banner_watch" / "watch.sqlite3"
            )
        return self._state

    async def snapshot(self) -> dict:
        now = datetime.now(timezone.utc)
        view = await asyncio.to_thread(self.state.snapshot, now)
        view["games"] = game_catalog(set(SOURCES))
        view["hasNotificationChannels"] = bool(
            Notify.global_target(include_system=True, empty_policy="skip").channels
        )
        return view

    async def subscribe(self, regions: set[tuple[str, str]], revision: int) -> dict:
        if regions - SOURCES.keys():
            raise ValueError("所选区服暂无可用公告源")
        async with self._mutation:
            await asyncio.to_thread(
                self.state.update_subscriptions,
                regions,
                revision,
                datetime.now(timezone.utc),
            )
        return await self.snapshot()

    async def refresh_sources(self) -> None:
        await asyncio.gather(
            *(self._refresh(region, adapter) for region, adapter in SOURCES.items())
        )

    async def _refresh(self, region: tuple[str, str], adapter: BannerSource) -> None:
        async with self._source_limit:
            try:
                async with asyncio.timeout(_MAX_SOURCE_SECONDS):
                    observations = await adapter.fetch()
                if any(
                    (item["game"], item["server"]) != region for item in observations
                ):
                    raise ValueError("公告区服与来源不一致")
            except Exception as error:
                # Do not log raw response bodies, configured proxy details or signed URLs.
                async with self._mutation:
                    await asyncio.to_thread(
                        self.state.source_failure,
                        region,
                        type(error).__name__,
                        datetime.now(timezone.utc),
                    )
                logger.warning(
                    f"刷新{region[0]}/{region[1]}卡池公告失败：{type(error).__name__}"
                )
                return
        async with self._mutation:
            await asyncio.to_thread(
                self.state.apply_observations,
                region,
                observations,
                datetime.now(timezone.utc),
            )

    def minute_due(self) -> bool:
        minute = int(datetime.now(timezone.utc).timestamp()) // 60
        if minute == self._last_minute:
            return False
        self._last_minute = minute
        return True

    async def dispatch_due(self) -> None:
        now = datetime.now(timezone.utc)
        async with self._mutation:
            await asyncio.to_thread(self.state.plan, now)
        target = Notify.global_target(include_system=True, empty_policy="skip")
        for channel, selected in target.channels:
            for _ in range(_NOTICE_LIMIT):
                async with self._mutation:
                    now = datetime.now(timezone.utc)
                    claim = await asyncio.to_thread(self.state.claim, selected.id, now)
                    if claim is None:
                        break
                    claims = [claim]
                    if claim.kind in {"catchup", "correction"}:
                        first = claim.banners[0]
                        region = (first["game"], first["server"])
                        for _ in range(_NOTICE_LIMIT - 1):
                            related = await asyncio.to_thread(
                                self.state.claim,
                                selected.id,
                                now,
                                notice_kind=claim.kind,
                                region=region,
                            )
                            if related is None:
                                break
                            claims.append(related)
                    banners = {
                        banner["id"]: banner
                        for item in claims
                        for banner in item.banners
                    }
                    single_target = replace(
                        target,
                        channels=((channel, selected),),
                        catalog_failures=(),
                        preparation_failures=(),
                    )
                    receipt = None
                    try:
                        async with asyncio.timeout(_MAX_SEND_SECONDS):
                            result = await Notify.dispatch(
                                _payload(claim.kind, tuple(banners.values())),
                                [single_target],
                                attempts=1,
                            )
                        outcome, reason = _delivery_result(result, selected.id)
                        receipt = {
                            "attempted": result.attempted,
                            "accepted": selected.id in result.succeeded_ids,
                            "coalesced_intents": [item.intent_id for item in claims],
                        }
                    except asyncio.CancelledError:
                        # The durable claim remains unknown; resuming cannot resend it.
                        raise
                    except Exception as error:
                        outcome, reason = "unknown", type(error).__name__
                    for item in claims:
                        await asyncio.to_thread(
                            self.state.finish,
                            item,
                            outcome,
                            reason,
                            datetime.now(timezone.utc),
                            receipt=receipt,
                        )
                    if outcome != "delivered":
                        logger.warning(f"卡池通知 {outcome}：{channel.key} / {reason}")
