#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates work covered by the following copyright and
#   permission notice:
#
#       Kuro-autosignin Copyright © 2024 mxyooR
#       https://github.com/mxyooR/Kuro-autosignin
#
#       Kuro-API-Collection Copyright © 2024 TomyJan
#       https://github.com/TomyJan/Kuro-API-Collection

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


import uuid
import asyncio
import httpx
from datetime import datetime

from typing import Dict, Any

from app.core import Config
from app.utils.constants import UTC8
from app.utils.logger import get_logger


def _safe_json(response: httpx.Response) -> dict:
    """解析库街区响应；非 JSON（通常是风控/维护页）时给出可读错误。"""

    try:
        data = response.json()
    except Exception:
        raise Exception(
            f"库街区返回了非 JSON 响应（HTTP {response.status_code}），疑似风控或服务维护"
        )
    if not isinstance(data, dict):
        raise Exception("库街区返回了异常响应格式，疑似风控或服务维护")
    return data

logger = get_logger("库街区签到任务")


# ==================== 常量 ====================

# API 端点
USER_INFO_URL = "https://api.kurobbs.com/user/mineV2"
ROLE_LIST_URL = "https://api.kurobbs.com/user/role/findRoleList"
SIGN_URL = "https://api.kurobbs.com/encourage/signIn/v2"

# 游戏配置
GAME_CONFIG = {
    "2": {"name": "战双帕弥什"},
    "3": {"name": "鸣潮"},
}

# 请求头模板
BBS_HEADERS = {
    "User-Agent": "Kuro/2.2.0 (Android;13) okhttp/4.11.0",
    "Host": "api.kurobbs.com",
    "Connection": "keep-alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/x-www-form-urlencoded",
}

GAME_HEADERS = {
    "User-Agent": "Kuro/2.2.0 (Android;13) okhttp/4.11.0",
    "Host": "api.kurobbs.com",
    "Connection": "keep-alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/x-www-form-urlencoded",
    "devCode": "",
}


# ==================== 签到主流程 ====================


async def kuro_sign_in(token: str, proxy: str | None = None) -> list[dict]:
    """库街区游戏签到

    Args:
        token: 库街区 JWT Token 字符串
        proxy: 代理地址

    Returns:
        签到结果列表，每项包含 account, game, platform, status, reward, reason
    """
    results = []

    if not token or not token.strip():
        logger.warning("库街区 Token 为空")
        return [{
            "account": "未知/库街区",
            "game": "库街区",
            "platform": "库街区",
            "status": "失败",
            "reward": "",
            "reason": "Token 为空",
        }]

    token = token.strip()
    dev_code = str(uuid.uuid4())
    distinct_id = str(uuid.uuid4())

    resolved_proxy = proxy if proxy is not None else Config.proxy
    async with httpx.AsyncClient(proxy=resolved_proxy, trust_env=False) as client:
        # 获取用户信息
        try:
            user_info = await _get_user_info(token, dev_code, distinct_id, client)
        except Exception as e:
            logger.warning(f"获取库街区用户信息失败: {e}")
            return [{
                "account": "未知/库街区",
                "game": "库街区",
                "platform": "库街区",
                "status": "失败",
                "reward": "",
                "reason": f"获取用户信息失败: {e}",
            }]

        user_id = user_info.get("userId", "")
        nick_name = user_info.get("nickName", user_id)

        # 获取游戏角色列表
        try:
            roles = await _get_role_list(token, dev_code, distinct_id, user_id, client)
        except Exception as e:
            logger.warning(f"获取库街区游戏角色失败: {e}")
            return [{
                "account": f"{nick_name}/库街区",
                "game": "库街区",
                "platform": "库街区",
                "status": "失败",
                "reward": "",
                "reason": f"获取角色列表失败: {e}",
            }]

        signable_roles = [
            role for role in roles if str(role.get("gameId", "")) in GAME_CONFIG
        ]
        if not signable_roles:
            logger.warning("未找到库街区绑定的游戏角色")
            return results

        # 逐游戏签到
        for index, role in enumerate(signable_roles):
            game_id = str(role.get("gameId", ""))
            server_id = role.get("serverId", "")
            role_id = role.get("roleId", "")
            role_name = role.get("roleName", "")
            game_cfg = GAME_CONFIG[game_id]

            # account 格式: 别名/角色名(角色ID)
            account = f"{nick_name}/{role_name}({role_id})" if role_id else f"{nick_name}/库街区"

            # 执行签到
            try:
                sign_result = await _do_sign(
                    token,
                    dev_code,
                    game_id,
                    server_id,
                    role_id,
                    user_id,
                    account,
                    game_cfg,
                    client,
                )
                results.append(sign_result)
            except Exception as e:
                results.append({
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "库街区",
                    "status": "失败",
                    "reward": "",
                    "reason": str(e),
                })
                logger.warning(f"{account} {game_cfg['name']} 签到异常: {e}")

            if index < len(signable_roles) - 1:
                await asyncio.sleep(3)

    return results


async def _get_user_info(
    token: str,
    dev_code: str,
    distinct_id: str,
    client: httpx.AsyncClient,
) -> dict:
    """获取用户信息"""
    headers = BBS_HEADERS.copy()
    headers["token"] = token
    headers["devcode"] = dev_code
    headers["distinct_id"] = distinct_id

    response = await client.post(
        USER_INFO_URL,
        headers=headers,
        data="",
        timeout=30.0,
    )
    rsp = _safe_json(response)

    if rsp.get("code") != 200:
        raise Exception(f"获取用户信息失败: {rsp.get('msg', rsp.get('message', ''))}")

    return rsp.get("data", {})


async def _get_role_list(
    token: str,
    dev_code: str,
    distinct_id: str,
    user_id: str,
    client: httpx.AsyncClient,
) -> list[dict]:
    """获取游戏角色列表"""
    headers = BBS_HEADERS.copy()
    headers["token"] = token
    headers["devcode"] = dev_code
    headers["distinct_id"] = distinct_id

    all_roles = []

    for game_id in GAME_CONFIG:
        response = await client.post(
            ROLE_LIST_URL,
            headers=headers,
            data=f"gameId={game_id}&userId={user_id}",
            timeout=30.0,
        )
        rsp = _safe_json(response)

        if rsp.get("code") != 200:
            logger.warning(f"获取 gameId={game_id} 角色失败: {rsp.get('msg', '')}")
            continue

        for role in rsp.get("data", []):
            role["gameId"] = game_id
            all_roles.append(role)

    return all_roles


async def _do_sign(
    token: str,
    dev_code: str,
    game_id: str,
    server_id: str,
    role_id: str,
    user_id: str,
    account: str,
    game_cfg: dict,
    client: httpx.AsyncClient,
) -> dict:
    """执行库街区签到"""

    headers = GAME_HEADERS.copy()
    headers["token"] = token
    headers["devcode"] = f"{dev_code}, Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) "

    # 库街区服务端按北京时间计月，本地时区可能不同，统一使用 UTC+8
    req_month = datetime.now(tz=UTC8).strftime("%m")
    body = f"gameId={game_id}&serverId={server_id}&roleId={role_id}&userId={user_id}&reqMonth={req_month}"

    response = await client.post(
        SIGN_URL,
        headers=headers,
        data=body,
        timeout=30.0,
    )
    rsp = _safe_json(response)

    code = rsp.get("code", -1)

    if code == 200:
        # 尝试获取奖励
        reward = ""
        data = rsp.get("data", {})
        if isinstance(data, dict):
            reward_name = data.get("rewardName", "")
            reward_cnt = data.get("rewardCnt", 1)
            if reward_name:
                reward = f"{reward_name}x{reward_cnt}"
        logger.info(f"{account} {game_cfg['name']} 签到成功")
        return {
            "account": account,
            "game": game_cfg["name"],
            "platform": "库街区",
            "status": "成功",
            "reward": reward,
            "reason": "",
        }
    elif code == 1511:
        # 今日已签到
        return {
            "account": account,
            "game": game_cfg["name"],
            "platform": "库街区",
            "status": "已签到",
            "reward": "",
            "reason": "",
        }
    else:
        message = rsp.get("msg", rsp.get("message", f"错误码 {code}"))
        logger.warning(f"{account} {game_cfg['name']} 签到失败: {message}")
        return {
            "account": account,
            "game": game_cfg["name"],
            "platform": "库街区",
            "status": "失败",
            "reward": "",
            "reason": message,
        }
