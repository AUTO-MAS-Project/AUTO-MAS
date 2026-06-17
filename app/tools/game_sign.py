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

from app.core import Config
from app.utils.logger import get_logger

logger = get_logger("游戏社区签到")


def _check_system_time() -> bool:
    """校准系统时间，避免因时间偏差导致签到失败

    Returns:
        True: 时间正常; False: 偏差过大
    """
    try:
        import httpx
        resp = httpx.get("http://worldtimeapi.org/api/timezone/Asia/Shanghai", timeout=5)
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


async def run_all_sign_in() -> list[dict]:
    """执行所有已配置平台的签到

    遍历所有账号组，对每个账号组中有配置的平台执行签到

    Returns:
        签到结果列表，每项包含 account, game, platform, status, reward, reason
    """
    results = []

    # 时间校准
    _check_system_time()

    for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
        account_name = account.get("GameSignAccount", "Name") or "默认账号"
        account_enabled = account.get("GameSignAccount", "Enabled")

        # 跳过已禁用的用户
        if not account_enabled:
            continue

        # 森空岛签到（方舟 + 终末地，一次调用获取两个游戏结果）
        skland_token = account.get("GameSignAccount", "SklandToken")
        skland_enabled = account.get("GameSignAccount", "SklandEnabled")
        if skland_token and skland_enabled:
            logger.info(f"[{account_name}] 开始森空岛签到")
            try:
                from .skland import skland_sign_in

                skland_results = await skland_sign_in(skland_token, app_code="all")
                for item in skland_results.get("成功", []):
                    results.append({
                        "account": account_name,
                        "account_uid": str(uid),
                        "game": "森空岛",
                        "platform": "森空岛",
                        "status": "成功",
                        "reward": "",
                        "reason": "",
                    })
                for item in skland_results.get("重复", []):
                    results.append({
                        "account": account_name,
                        "account_uid": str(uid),
                        "game": "森空岛",
                        "platform": "森空岛",
                        "status": "已签到",
                        "reward": "",
                        "reason": "",
                    })
                for item in skland_results.get("失败", []):
                    results.append({
                        "account": account_name,
                        "account_uid": str(uid),
                        "game": "森空岛",
                        "platform": "森空岛",
                        "status": "失败",
                        "reward": "",
                        "reason": "签到失败",
                    })

            except Exception as e:
                logger.error(f"[{account_name}] 森空岛签到异常: {e}")
                results.append({
                    "account": account_name,
                    "account_uid": str(uid),
                    "game": "森空岛",
                    "platform": "森空岛",
                    "status": "失败",
                    "reward": "",
                    "reason": str(e),
                })

        # 米游社签到
        miyoushe_token = account.get("GameSignAccount", "MiyousheToken")
        miyoushe_enabled = account.get("GameSignAccount", "MiyousheEnabled")
        if miyoushe_token and miyoushe_enabled:
            logger.info(f"[{account_name}] 开始米游社签到")
            try:
                from .miyoushe import miyoushe_sign_in

                miyoushe_results = await miyoushe_sign_in(miyoushe_token)
                for item in miyoushe_results:
                    item["account"] = account_name
                    item["account_uid"] = str(uid)
                results.extend(miyoushe_results)
            except Exception as e:
                logger.error(f"[{account_name}] 米游社签到异常: {e}")
                results.append({
                    "account": account_name,
                    "game": "米游社",
                    "platform": "米游社",
                    "status": "失败",
                    "reward": "",
                    "reason": str(e),
                })

        # 库街区签到
        kuro_token = account.get("GameSignAccount", "KuroToken")
        kuro_enabled = account.get("GameSignAccount", "KuroEnabled")
        if kuro_token and kuro_enabled:
            logger.info(f"[{account_name}] 开始库街区签到")
            try:
                from .kuro import kuro_sign_in

                kuro_results = await kuro_sign_in(kuro_token)
                for item in kuro_results:
                    item["account"] = account_name
                    item["account_uid"] = str(uid)
                results.extend(kuro_results)
            except Exception as e:
                logger.error(f"[{account_name}] 库街区签到异常: {e}")
                results.append({
                    "account": account_name,
                    "game": "库街区",
                    "platform": "库街区",
                    "status": "失败",
                    "reward": "",
                    "reason": str(e),
                })

    if not results:
        logger.info("没有配置任何签到平台")

    return results


def format_sign_results(results: list[dict]) -> dict:
    """将签到结果格式化为前端可展示的结构

    按平台分组，平台内按别名去重

    Returns:
        {platform: [{account_alias, account_uid, games: [{game, status, reward, reason}]}]}
    """
    platforms: dict[str, dict[str, dict]] = {}

    for item in results:
        platform = item.get("platform", "未知")
        account = item.get("account", "未知")
        account_uid = item.get("account_uid", "")
        # 别名 = account 中 '/' 前的部分
        alias = account.split("/")[0] if "/" in account else account

        if platform not in platforms:
            platforms[platform] = {}

        if alias not in platforms[platform]:
            platforms[platform][alias] = {
                "account_alias": alias,
                "account_uid": account_uid,
                "games": [],
            }

        platforms[platform][alias]["games"].append({
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
