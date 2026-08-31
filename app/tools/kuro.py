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
from typing import Any


from app.core import Config
from app.utils.constants import UTC8
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

logger = get_logger("库街区社区")


def _log_kuro_exception(stage: str, error: Exception) -> str:
    """按异常类型记录库街区失败，并返回安全的非空原因。"""

    expected = isinstance(
        error,
        (ValueError, httpx.HTTPError, TimeoutError, ConnectionError),
    )
    reason = format_exception_reason(
        error,
        stage=stage,
        include_message=expected,
    )
    if expected:
        logger.warning(reason)
    else:
        logger.exception(f"{stage}程序异常")
    return reason


def _safe_json(response: httpx.Response) -> dict:
    """解析库街区响应；非 JSON（通常是风控/维护页）时给出可读错误。"""

    try:
        data = response.json()
    except ValueError as exc:
        try:
            response_preview = response.text[:512].lower()
        except Exception:
            response_preview = ""
        if any(
            marker in response_preview
            for marker in ("captcha", "geetest", "安全验证", "风控", "challenge")
        ):
            raise _KuroRiskError(
                "库街区请求触发风控或安全验证，请稍后重试"
            ) from exc
        raise ValueError(
            f"库街区返回了非 JSON 响应（HTTP {response.status_code}），疑似风控或服务维护"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("库街区返回了异常响应格式，疑似风控或服务维护")
    return data


def _is_kuro_code(value: Any, expected: int) -> bool:
    """兼容库街区接口以数字或字符串返回业务码。"""

    return str(value).strip() == str(expected)


class _KuroAuthError(ValueError):
    """库街区凭据或用户会话已不能继续使用。"""


class _KuroRiskError(ValueError):
    """库街区请求被风控或安全校验拦截。"""


_KURO_RISK_MARKERS = (
    "风控",
    "安全验证",
    "短信验证",
    "需要验证",
    "频繁",
    "captcha",
    "security",
    "risk",
)


def _kuro_device_identifiers(token: str) -> tuple[str, str]:
    """从同一 Token 派生稳定的设备码和请求标识，不改变配置存储格式。"""

    return (
        str(uuid.uuid3(uuid.NAMESPACE_URL, f"auto-mas:kuro:devcode:{token}")),
        str(uuid.uuid3(uuid.NAMESPACE_URL, f"auto-mas:kuro:distinct:{token}")),
    )


def _kuro_request_headers(
    template: dict[str, str],
    token: str,
    dev_code: str,
    distinct_id: str = "",
) -> dict[str, str]:
    """为一次请求注入同一组运行期认证和设备字段。"""

    headers = template.copy()
    headers.update({"token": token, "devcode": dev_code})
    if distinct_id:
        headers["distinct_id"] = distinct_id
    return headers


def _raise_kuro_response_error(
    response: httpx.Response,
    data: dict,
    stage: str,
    *,
    allow_already_signed: bool = False,
) -> None:
    """将库街区业务码转换为可区分的领域异常。"""

    code = data.get("code")
    message = _kuro_response_message(data, f"HTTP {response.status_code}")
    lowered_message = message.lower()
    if response.status_code in (403, 429) and (
        response.status_code == 429
        or any(marker in lowered_message for marker in _KURO_RISK_MARKERS)
    ):
        raise _KuroRiskError(
            f"库街区请求触发频率限制或风控（HTTP {response.status_code}），请稍后重试"
        )
    if response.status_code in (401, 403):
        raise _KuroAuthError("库街区 Token 已失效，请重新获取 Token")
    if not response.is_success:
        raise ValueError(
            f"{stage}失败（HTTP {response.status_code}，code={code}）：{message}"
        )
    if _is_kuro_code(code, 200) or (
        allow_already_signed and _is_kuro_code(code, 1511)
    ):
        return

    if _is_kuro_code(code, 220):
        if any(marker in lowered_message for marker in _KURO_RISK_MARKERS):
            raise _KuroRiskError(
                "库街区请求触发风控或安全验证（code=220），请稍后重试"
            )
        raise _KuroAuthError(
            "库街区 Token 已失效（code=220）；库街区 APP 端再次登录可能使旧 Token 失效，请重新获取 Token"
        )
    if _is_kuro_code(code, 1513):
        raise _KuroAuthError(
            "库街区用户信息异常（code=1513），请重新获取 Token"
        )
    raise ValueError(
        f"{stage}失败（HTTP {response.status_code}，code={code}）：{message}"
    )


def _kuro_result_status(error: Exception) -> str:
    """将库街区领域异常映射为现有通知结果状态。"""

    return "风控" if isinstance(error, _KuroRiskError) else "失败"


def _kuro_response_message(data: dict, fallback: str) -> str:
    """读取接口给出的短错误信息，不回显完整响应正文。"""

    message = data.get("msg", data.get("message", fallback))
    return str(message or "").strip() or fallback


def _extract_kuro_role_records(value: Any) -> list[dict]:
    """兼容角色列表的数组及已确认的常见包装字段。"""

    if value is None:
        return []
    if isinstance(value, list):
        records: list[dict] = []
        for item in value:
            if isinstance(item, (dict, list)):
                records.extend(_extract_kuro_role_records(item))
        return records
    if not isinstance(value, dict):
        raise ValueError("库街区角色列表响应格式无效")

    if any(
        value.get(key) not in (None, "")
        for key in ("roleId", "role_id", "roleID")
    ):
        return [value]

    for key in ("roles", "roleList", "role_list", "list", "data", "roleInfo", "role"):
        if key in value:
            return _extract_kuro_role_records(value[key])
    return []


def _normalise_kuro_role(
    raw_role: dict,
    requested_game_id: str,
) -> dict | None:
    """按本次请求的游戏 ID 归一化角色，拒绝跨游戏猜测。"""

    reported_game_id = str(
        raw_role.get("gameId")
        or raw_role.get("game_id")
        or raw_role.get("gameID")
        or ""
    ).strip()
    if reported_game_id and reported_game_id != requested_game_id:
        return None

    game_id = reported_game_id or requested_game_id
    if game_id not in GAME_CONFIG:
        return None

    role_id = str(
        raw_role.get("roleId")
        or raw_role.get("role_id")
        or raw_role.get("roleID")
        or ""
    ).strip()
    if not role_id:
        return None

    role = dict(raw_role)
    role["gameId"] = game_id
    role["gameName"] = GAME_CONFIG[game_id]["name"]
    role["roleId"] = role_id
    for source, target in (
        ("server_id", "serverId"),
        ("server_name", "serverName"),
        ("role_name", "roleName"),
    ):
        if target not in role and role.get(source) not in (None, ""):
            role[target] = role[source]
    for key in ("serverId", "serverName", "roleName"):
        if role.get(key) not in (None, ""):
            role[key] = str(role[key]).strip()
    return role


def _kuro_game_failure_results(
    account: str,
    reason: str,
    game_ids: tuple[str, ...] | None = None,
    status: str = "失败",
) -> list[dict]:
    """为有明确游戏范围的失败生成逐游戏结果。"""

    selected_game_ids = game_ids or tuple(GAME_CONFIG)
    return [
        {
            "account": f"{account}/{GAME_CONFIG[game_id]['name']}",
            "game": GAME_CONFIG[game_id]["name"],
            "platform": "库街区",
            "status": status,
            "reward": "",
            "reason": reason,
        }
        for game_id in selected_game_ids
        if game_id in GAME_CONFIG
    ]


def _kuro_role_failure_result(
    account: str,
    game_name: str,
    reason: str,
    *,
    status: str = "失败",
) -> dict:
    """构造单个库街区游戏的失败结果。"""

    return {
        "account": account,
        "game": game_name,
        "platform": "库街区",
        "status": status,
        "reward": "",
        "reason": reason,
    }


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
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh-Hans;q=0.9",
    "User-Agent": "okhttp/3.11.0",
    "Host": "api.kurobbs.com",
    "Connection": "keep-alive",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/x-www-form-urlencoded",
    "source": "android",
    "osversion": "Android",
    "model": "2211133C",
    "version": "2.2.0",
    "versioncode": "2200",
    "channelid": "1",
    "lang": "zh-Hans",
    "countrycode": "CN",
}

GAME_HEADERS = {
    **BBS_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://web-static.kurobbs.com",
    "X-Requested-With": "com.kurogame.kjq",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; 2211133C Build/TKQ1.220905.001; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/114.0.5735.131 "
        "Mobile Safari/537.36 Kuro/1.0.9 KuroGameBox/1.0.9"
    ),
}


def validate_kuro_credential(token: str) -> str:
    """校验库街区 Token 的本地非空条件，不探测上游有效期。"""

    value = str(token or "").strip()
    if not value:
        raise ValueError("库街区 Token 为空")
    return value


# ==================== 签到主流程 ====================


async def kuro_sign_in(token: str, proxy: str | None = None) -> list[dict]:
    """库街区社区签到

    Args:
        token: 库街区 JWT Token 字符串
        proxy: 代理地址

    Returns:
        签到结果列表，每项包含 account, game, platform, status, reward, reason
    """
    results = []

    if not token or not token.strip():
        logger.warning("库街区 Token 为空")
        return _kuro_game_failure_results("未知/库街区", "Token 为空")

    token = token.strip()
    dev_code, distinct_id = _kuro_device_identifiers(token)

    resolved_proxy = proxy if proxy is not None else Config.proxy
    async with httpx.AsyncClient(proxy=resolved_proxy, trust_env=False) as client:
        # 获取用户信息
        try:
            user_info = await _get_user_info(token, dev_code, distinct_id, client)
        except Exception as e:
            reason = _log_kuro_exception("获取库街区用户信息失败", e)
            return _kuro_game_failure_results(
                "未知/库街区",
                reason,
                status=_kuro_result_status(e),
            )

        user_id = user_info.get("userId", "")
        nick_name = user_info.get("nickName", user_id)

        # 获取游戏角色列表
        try:
            roles = await _get_role_list(token, dev_code, distinct_id, user_id, client)
        except Exception as e:
            reason = _log_kuro_exception("获取库街区游戏角色失败", e)
            return _kuro_game_failure_results(
                f"{nick_name}/库街区",
                reason,
                status=_kuro_result_status(e),
            )

        query_failures = [
            role
            for role in roles
            if role.get("_queryError") and str(role.get("gameId", "")) in GAME_CONFIG
        ]
        for failure in query_failures:
            game_id = str(failure["gameId"])
            game_name = GAME_CONFIG[game_id]["name"]
            results.append({
                "account": f"{nick_name}/{game_name}",
                "game": game_name,
                "platform": "库街区",
                "status": "失败",
                "reward": "",
                "reason": str(failure["_queryError"]),
            })

        signable_roles = [
            role
            for role in roles
            if not role.get("_queryError")
            and str(role.get("gameId", "")) in GAME_CONFIG
        ]
        if not signable_roles:
            logger.warning("未找到库街区绑定的游戏角色")
            return results

        # 逐游戏执行社区签到
        for index, role in enumerate(signable_roles):
            game_id = str(role.get("gameId", ""))
            server_id = role.get("serverId", "")
            role_id = role.get("roleId", "")
            role_name = role.get("roleName", "")
            game_cfg = GAME_CONFIG[game_id]

            # account 格式: 别名/角色名(角色ID)
            account = (
                f"{nick_name}/{role_name}({role_id})"
                if role_id
                else f"{nick_name}/库街区"
            )

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
                    distinct_id=distinct_id,
                )
                results.append(sign_result)
            except (_KuroAuthError, _KuroRiskError) as e:
                reason = _log_kuro_exception(
                    f"{game_cfg['name']}签到失败",
                    e,
                )
                results.append(
                    _kuro_role_failure_result(
                        account,
                        game_cfg["name"],
                        reason,
                        status=_kuro_result_status(e),
                    )
                )
                # 220/1513/风控已经说明当前会话不可继续，停止撞击剩余角色。
                for remaining_role in signable_roles[index + 1 :]:
                    remaining_game_id = str(remaining_role.get("gameId", ""))
                    remaining_cfg = GAME_CONFIG.get(remaining_game_id)
                    if remaining_cfg is None:
                        continue
                    remaining_role_id = remaining_role.get("roleId", "")
                    remaining_account = (
                        f"{nick_name}/{remaining_role.get('roleName', '')}"
                        f"({remaining_role_id})"
                        if remaining_role_id
                        else f"{nick_name}/库街区"
                    )
                    results.append(
                        _kuro_role_failure_result(
                            remaining_account,
                            remaining_cfg["name"],
                            reason,
                            status=_kuro_result_status(e),
                        )
                    )
                break
            except Exception as e:
                reason = _log_kuro_exception(
                    f"{game_cfg['name']}签到失败",
                    e,
                )
                results.append(
                    _kuro_role_failure_result(account, game_cfg["name"], reason)
                )

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
    headers = _kuro_request_headers(BBS_HEADERS, token, dev_code, distinct_id)

    response = await client.post(
        USER_INFO_URL,
        headers=headers,
        data="",
        timeout=30.0,
    )
    rsp = _safe_json(response)

    _raise_kuro_response_error(response, rsp, "获取用户信息")

    data = rsp.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("库街区用户信息响应格式无效")
    profile = data.get("mine")
    if not isinstance(profile, dict):
        profile = data
    user_id = profile.get("userId") or data.get("userId")
    if user_id in (None, ""):
        raise ValueError("库街区用户信息缺少 userId")
    nick_name = (
        profile.get("nickName")
        or profile.get("userName")
        or data.get("nickName")
        or data.get("userName")
        or user_id
    )
    return {"userId": str(user_id).strip(), "nickName": str(nick_name).strip()}


async def _get_role_list(
    token: str,
    dev_code: str,
    distinct_id: str,
    user_id: str,
    client: httpx.AsyncClient,
) -> list[dict]:
    """获取游戏角色列表"""
    headers = _kuro_request_headers(BBS_HEADERS, token, dev_code, distinct_id)

    all_roles = []

    for game_id in GAME_CONFIG:
        game_name = GAME_CONFIG[game_id]["name"]
        try:
            response = await client.post(
                ROLE_LIST_URL,
                headers=headers,
                data=f"gameId={game_id}&userId={user_id}",
                timeout=30.0,
            )
            rsp = _safe_json(response)

            _raise_kuro_response_error(response, rsp, f"获取{game_name}角色")

            raw_roles = _extract_kuro_role_records(rsp.get("data", []))
            for raw_role in raw_roles:
                role = _normalise_kuro_role(raw_role, game_id)
                if role is not None:
                    all_roles.append(role)
        except (_KuroAuthError, _KuroRiskError):
            raise
        except Exception as e:
            reason = _log_kuro_exception(f"获取{game_name}角色失败", e)
            all_roles.append({"gameId": game_id, "_queryError": reason})

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
    *,
    distinct_id: str = "",
) -> dict:
    """执行库街区签到"""

    headers = _kuro_request_headers(GAME_HEADERS, token, dev_code, distinct_id)

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

    _raise_kuro_response_error(
        response,
        rsp,
        f"{game_cfg['name']}签到",
        allow_already_signed=True,
    )

    if _is_kuro_code(code, 200):
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
    elif _is_kuro_code(code, 1511):
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
        message = _kuro_response_message(rsp, f"错误码 {code}")
        logger.warning(f"{account} {game_cfg['name']} 签到失败: {message}")
        return _kuro_role_failure_result(account, game_cfg["name"], message)
