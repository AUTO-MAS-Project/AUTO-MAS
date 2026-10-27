#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAA 活动关卡查询与共享刷新，缓存沿用现有配置框架。"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Literal, cast

import httpx

from app.core import Config
from app.utils import constants as _utils_constants
from app.utils import get_logger

from ..constants import RESOURCE_STAGE_DATE_TEXT, RESOURCE_STAGE_DROP_INFO

logger = get_logger("MAA 关卡")


class MaaStageService:
    def __init__(self) -> None:
        self._stage_refresh_task: asyncio.Task[None] | None = None
        # 上次活动关卡刷新失败的时间: 冷却期内不再重复请求远端
        self._stage_refresh_failed_at: datetime | None = None

    async def get_stage_info(
        self,
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
            "Info",
        ],
        refresh: bool = False,
        server: str = "Official",
    ):
        """获取关卡信息"""

        stage_by_server = await self.get_stage(refresh=refresh)
        # 开放日按区服的游戏日判断
        game_today = _utils_constants.game_now(server)
        server = "Official" if server == "Bilibili" else server
        stage_data = stage_by_server.get(server, {})

        if type == "Info":
            today = game_today.isoweekday()
            res_stage_info = []
            for stage in _utils_constants.RESOURCE_STAGE_INFO:
                if (
                    today in stage["days"]
                    and stage["value"] in RESOURCE_STAGE_DROP_INFO
                ):
                    res_stage_info.append(RESOURCE_STAGE_DROP_INFO[stage["value"]])
            stage_options = [dict(item) for item in stage_data.get("ALL", [])]
            for combox in stage_options:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            raw_stage_data = json.loads(Config.setting.Data.StageData)
            has_cache = isinstance(raw_stage_data.get(server), dict) and (
                "sideStoryStage" in raw_stage_data[server]
            )
            activity_stages = stage_data.get("Info", [])
            activity_status = "ready" if activity_stages else "empty"
            if not has_cache:
                activity_status = "unavailable"
            elif self._stage_refresh_failed_at is not None:
                activity_status = "stale"
            return {
                "Activity": activity_stages,
                "ActivityStatus": activity_status,
                "ActivityUpdatedAt": Config.setting.Data.LastStageUpdated.isoformat(),
                "Resource": res_stage_info,
                "Options": stage_options,
            }
        elif type == "User":
            data = stage_data.get("ALL", [])
            for combox in data:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            return data
        elif type == "Today":
            return stage_data.get(game_today.strftime("%A"), [])
        else:
            return stage_data.get(type, [])

    async def get_stage(
        self, *, refresh: bool = False, wait_stale: bool = True
    ) -> dict[str, Any]:
        """更新活动关卡信息。

        refresh=True 强制远端检查；wait_stale=True 时缓存过期也等本次刷新完成，
        调用方拿到的是本次请求触发的那次刷新的结果（刷新失败则仍是旧缓存）。
        wait_stale=False 只把刷新丢到后台并立即返回缓存，供启动预热使用。
        """

        raw_stage_data = json.loads(Config.setting.Data.StageData)
        has_server_data = isinstance(raw_stage_data.get("Official"), dict) and (
            "sideStoryStage" in raw_stage_data["Official"]
        )
        # 缺官方缓存也必须抓一次, 但这不等于调用方要求等待本次刷新
        if (
            not refresh
            and has_server_data
            and (self._stage_refresh_failed_at is None)
            and (
                datetime.now().astimezone() - timedelta(hours=1)
                < Config.setting.Data.LastStageUpdated
            )
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的活动关卡信息")
            return json.loads(cast(str, Config.setting.Data.Stage))

        if (
            not refresh
            and self._stage_refresh_failed_at is not None
            and datetime.now() - self._stage_refresh_failed_at < timedelta(seconds=60)
        ):
            # 刚失败过就先不再抓: 断网时总览与注入流程会串行重复等超时
            logger.info("活动关卡信息刷新刚失败过, 直接使用缓存")
            return json.loads(cast(str, Config.setting.Data.Stage))

        if self._stage_refresh_task is None:
            task = asyncio.create_task(self._refresh_stage())
            self._stage_refresh_task = task
            Config.temp_task.append(task)

            def _done(t: asyncio.Task) -> None:
                if self._stage_refresh_task is t:
                    self._stage_refresh_task = None
                if t in Config.temp_task:
                    Config.temp_task.remove(t)

            task.add_done_callback(_done)
        else:
            logger.info("活动关卡信息更新任务已在进行中")

        refresh_task = self._stage_refresh_task
        if refresh_task is not None and (refresh or wait_stale):
            await asyncio.shield(refresh_task)

        return json.loads(cast(str, Config.setting.Data.Stage))

    async def _refresh_stage(self) -> None:
        """从远端刷新活动关卡信息（仅后台调用）。"""

        logger.info("开始获取活动关卡信息")
        try:
            raw_stage_data = json.loads(Config.setting.Data.StageData)
            has_server_data = isinstance(raw_stage_data.get("Official"), dict) and (
                "sideStoryStage" in raw_stage_data["Official"]
            )
            headers = (
                {"If-None-Match": Config.setting.Data.StageETag}
                if has_server_data
                else {}
            )
            async with httpx.AsyncClient(
                proxy=Config.proxy, follow_redirects=True
            ) as client:
                response = await client.get(
                    "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivityV2.json",
                    headers=headers,
                )

                if response.status_code == 304:
                    self._stage_refresh_failed_at = None
                    logger.info("关卡信息未更新，使用本地缓存的活动关卡信息")
                    await Config.setting.update(
                        type(Config.setting).model_validate(
                            {"Data": {"LastStageUpdated": datetime.now().astimezone()}}
                        ),
                        check_visibility=False,
                    )
                elif response.status_code == 200:
                    self._stage_refresh_failed_at = None
                    logger.success("成功获取远端活动关卡信息")
                    # 时间戳最后写: 并发调用按它判断缓存新鲜度, 先写会在
                    # 两次写入之间把旧关卡当成刚更新过的缓存返回
                    await Config.setting.update(
                        type(Config.setting).model_validate(
                            {
                                "Data": {
                                    "StageData": json.dumps(
                                        response.json(), ensure_ascii=False
                                    )
                                }
                            }
                        ),
                        check_visibility=False,
                    )
                    await Config.setting.update(
                        type(Config.setting).model_validate(
                            {
                                "Data": {
                                    "StageETag": response.headers.get("ETag")
                                    or response.headers.get("etag")
                                    or ""
                                }
                            }
                        ),
                        check_visibility=False,
                    )
                    await Config.setting.update(
                        type(Config.setting).model_validate(
                            {"Data": {"LastStageUpdated": datetime.now().astimezone()}}
                        ),
                        check_visibility=False,
                    )
                else:
                    logger.warning(f"无法从MAA服务器获取活动关卡信息:{response.text}")
                    self._stage_refresh_failed_at = datetime.now()
        except Exception as e:
            self._stage_refresh_failed_at = datetime.now()
            logger.warning(f"无法从MAA服务器获取活动关卡信息: {type(e).__name__}: {e}")


maa_stage_service = MaaStageService()
