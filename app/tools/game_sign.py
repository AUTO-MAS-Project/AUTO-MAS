#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime

import httpx

from app.core import Config
from app.utils.constants import UTC8
from app.utils.logger import get_logger
from .game_sign_result import build_skland_sign_results

logger = get_logger("游戏社区签到")

_game_sign_lock = asyncio.Lock()
_game_sign_flow_lock = asyncio.Lock()


class GameSignInProgressError(RuntimeError):
    """游戏社区签到已在执行。"""


@asynccontextmanager
async def game_sign_flow():
    """串行保护一次完整签到流程，包括结果持久化和通知。"""

    if _game_sign_flow_lock.locked():
        raise GameSignInProgressError("游戏社区签到正在执行，请稍后重试")

    await _game_sign_flow_lock.acquire()
    try:
        yield
    finally:
        _game_sign_flow_lock.release()


def _all_enabled_platforms_signed(
    results: list[dict],
    *,
    account_uid: str,
    enabled_platforms: list[str],
) -> bool:
    """判断账号的全部已配置平台结果是否均已完成。"""

    if not enabled_platforms:
        return False

    for platform in enabled_platforms:
        platform_results = [
            result
            for result in results
            if result.get("account_uid") == account_uid
            and result.get("platform") == platform
        ]
        if not platform_results or any(
            result.get("status") not in ("成功", "已签到")
            for result in platform_results
        ):
            return False

    return True


async def _check_system_time() -> bool:
    """校准系统时间，避免因时间偏差导致签到失败

    Returns:
        True: 时间正常; False: 偏差过大
    """
    try:
        async with httpx.AsyncClient(proxy=Config.proxy) as client:
            resp = await client.get(
                "http://worldtimeapi.org/api/timezone/Asia/Shanghai", timeout=5
            )
        api_time = resp.json().get("unixtime", 0)
        local_time = time.time()
        offset = abs(api_time - local_time)
        if offset > 300:
            logger.warning(f"系统时间偏差 {offset:.0f} 秒，签到可能失败，请校准系统时间")
            return False
        if offset > 30:
            logger.info(f"系统时间偏差 {offset:.0f} 秒，在可接受范围内")
        return True
    except Exception as e:
        logger.debug(f"时间校准跳过: {e}")
        return True


async def run_all_sign_in(force: bool = False) -> list[dict]:
    """串行执行游戏社区签到，避免重复签到和重复通知。"""
    if _game_sign_lock.locked():
        raise GameSignInProgressError("游戏社区签到正在执行，请稍后重试")

    await _game_sign_lock.acquire()
    try:
        return await _run_all_sign_in(force=force)
    finally:
        _game_sign_lock.release()


async def _run_all_sign_in(force: bool = False) -> list[dict]:
    """执行所有已配置平台的签到

    遍历所有账号组，对每个账号组中有配置的平台执行签到

    Args:
        force: 为 True 时忽略每用户 LastSignDate，强制重新签到（手动签到用）

    Returns:
        签到结果列表，每项包含 account, game, platform, status, reward, reason
    """
    results = []
    today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

    # 时间校准：偏差过大时跳过本轮签到，避免因时间错误导致 API 失败
    if not await _check_system_time():
        logger.warning("系统时间偏差过大，跳过本轮游戏社区签到")
        return results

    for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
        account_name = account.get("GameSignAccount", "Name") or "默认账号"
        account_enabled = account.get("GameSignAccount", "Enabled")
        account_uid = str(uid)
        enabled_platforms = []

        # 跳过已禁用的用户
        if not account_enabled:
            continue

        # 非强制模式：跳过今日已签到的用户
        if not force:
            user_last_sign = account.get("GameSignAccount", "LastSignDate")
            if user_last_sign == today:
                logger.debug(f"[{account_name}] 今日已签到，跳过")
                continue

        # 森空岛签到（方舟 + 终末地，一次调用获取两个游戏结果）
        skland_token = account.get("GameSignAccount", "SklandToken")
        if skland_token:
            enabled_platforms.append("森空岛")
            logger.info(f"[{account_name}] 开始森空岛签到")
            try:
                from .skland import skland_sign_in

                skland_results = await skland_sign_in(skland_token, app_code="all")
                if not any(
                    game_key in skland_results
                    for game_key in ("arknights", "endfield")
                ):
                    results.extend(
                        build_skland_sign_results(
                            skland_results,
                            account_name=account_name,
                            account_uid=account_uid,
                        )
                    )
                    skland_results = {}
                # 按游戏分组的结果：{"arknights": {成功/重复/失败}, "endfield": {成功/重复/失败}}
                game_mapping = {
                    "arknights": "明日方舟",
                    "endfield": "终末地",
                }
                for game_key, game_name in game_mapping.items():
                    game_data = skland_results.get(game_key, {})
                    if not game_data:
                        continue
                    for item in game_data.get("成功", []):
                        results.append({
                            "account": item if isinstance(item, str) else str(item),
                            "account_uid": account_uid,
                            "game": game_name,
                            "platform": "森空岛",
                            "status": "成功",
                            "reward": "",
                            "reason": "",
                        })
                    for item in game_data.get("重复", []):
                        results.append({
                            "account": item if isinstance(item, str) else str(item),
                            "account_uid": account_uid,
                            "game": game_name,
                            "platform": "森空岛",
                            "status": "已签到",
                            "reward": "",
                            "reason": "",
                        })
                    for item in game_data.get("失败", []):
                        results.append({
                            "account": item if isinstance(item, str) else str(item),
                            "account_uid": account_uid,
                            "game": game_name,
                            "platform": "森空岛",
                            "status": "失败",
                            "reward": "",
                            "reason": "签到失败",
                        })

            except Exception as e:
                logger.error(f"[{account_name}] 森空岛签到异常: {e}")
                results.append({
                    "account": f"{account_name}/森空岛",
                    "account_uid": account_uid,
                    "game": "森空岛",
                    "platform": "森空岛",
                    "status": "失败",
                    "reward": "",
                    "reason": str(e),
                })

        # 米游社签到
        miyoushe_token = account.get("GameSignAccount", "MiyousheToken")
        if miyoushe_token:
            enabled_platforms.append("米游社")
            logger.info(f"[{account_name}] 开始米游社签到")
            try:
                from .miyoushe import miyoushe_sign_in

                miyoushe_results = await miyoushe_sign_in(miyoushe_token)
                for item in miyoushe_results:
                    item["account"] = account_name
                    item["account_uid"] = account_uid
                results.extend(miyoushe_results)
            except Exception as e:
                logger.error(f"[{account_name}] 米游社签到异常: {e}")
                results.append({
                    "account": f"{account_name}/米游社",
                    "account_uid": account_uid,
                    "game": "米游社",
                    "platform": "米游社",
                    "status": "失败",
                    "reward": "",
                    "reason": str(e),
                })

        # 库街区签到
        kuro_token = account.get("GameSignAccount", "KuroToken")
        if kuro_token:
            enabled_platforms.append("库街区")
            logger.info(f"[{account_name}] 开始库街区签到")
            try:
                from .kuro import kuro_sign_in

                kuro_results = await kuro_sign_in(kuro_token)
                for item in kuro_results:
                    item["account"] = account_name
                    item["account_uid"] = account_uid
                results.extend(kuro_results)
            except Exception as e:
                logger.error(f"[{account_name}] 库街区签到异常: {e}")
                results.append({
                    "account": f"{account_name}/库街区",
                    "account_uid": account_uid,
                    "game": "库街区",
                    "platform": "库街区",
                    "status": "失败",
                    "reward": "",
                    "reason": str(e),
                })

        # 每个已配置平台的全部角色或游戏均完成后，才标记该用户今日已签到
        if _all_enabled_platforms_signed(
            results,
            account_uid=account_uid,
            enabled_platforms=enabled_platforms,
        ):
            try:
                await account.set("GameSignAccount", "LastSignDate", today)
            except Exception as e:
                logger.warning(f"[{account_name}] 保存签到完成日期失败: {e}")

    if not results:
        logger.info("没有配置任何签到平台")

    return results


def merge_sign_results(existing: dict, formatted: dict, replace: bool = False) -> dict:
    """将新签到结果合并到已有结果中

    Args:
        existing: 已有的 _game_sign_result_data
        formatted: 本次 format_sign_results 的新结果
        replace: True 时按 account_uid 替换旧数据（手动签到用）；
                 False 时仅追加不存在的 account_uid

    Returns:
        合并后的 _game_sign_result_data
    """
    if not existing:
        return formatted

    for platform, accounts in formatted.items():
        if platform not in existing:
            existing[platform] = accounts
        elif replace:
            new_uids = {g.get("account_uid") for g in accounts if g.get("account_uid")}
            if new_uids:
                existing[platform] = [
                    g for g in existing[platform]
                    if g.get("account_uid") not in new_uids
                ]
            existing[platform].extend(accounts)
        else:
            # 自动签到也按 platform + account_uid 替换整组结果，避免失败/风控
            # 状态被旧的成功结果遮蔽；同 uid 多账号组需批量替换后一次性追加。
            new_uids = {g.get("account_uid") for g in accounts if g.get("account_uid")}
            if new_uids:
                existing[platform] = [
                    g for g in existing[platform]
                    if g.get("account_uid") not in new_uids
                ]
            existing[platform].extend(accounts)

    return existing


def format_sign_results(results: list[dict]) -> dict:
    """将签到结果格式化为前端可展示的结构

    按平台分组，平台内按账号 UID 聚合

    Returns:
        {platform: [{account_alias, account_uid, games: [{game, status, reward, reason}]}]}
    """
    platforms: dict[str, dict[str, dict]] = {}

    for item in results:
        platform = item.get("platform", "未知")
        account = str(item.get("account", "未知"))
        account_uid = str(item.get("account_uid", ""))
        # 别名 = account 中 '/' 前的部分
        alias = account.split("/")[0] if "/" in account else account
        group_key = account_uid or f"alias:{alias}"

        if platform not in platforms:
            platforms[platform] = {}

        if group_key not in platforms[platform]:
            platforms[platform][group_key] = {
                "account_alias": alias,
                "account_uid": account_uid,
                "games": [],
            }

        platforms[platform][group_key]["games"].append({
            "game": item.get("game", "未知"),
            "status": item.get("status", "失败"),
            "reward": item.get("reward", ""),
            "reason": item.get("reason", ""),
        })

    # 转为列表格式
    result = {}
    for platform, accounts in platforms.items():
        result[platform] = list(accounts.values())

    return result
