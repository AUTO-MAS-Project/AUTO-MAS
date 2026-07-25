#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates work covered by the following copyright and
#   permission notice:
#
#       nonebot-plugin-mystool Copyright © 2023-2025 Ljzd-PRO
#       https://github.com/Ljzd-PRO/nonebot-plugin-mystool
#
#       MYS_Game_Singin Copyright © 2023 GildedFlames
#       https://github.com/GildedFlames/MYS_Game_Singin

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
import hashlib
import json
import random
import string
import time
import uuid

import httpx

from typing import Dict

from app.core import Config
from app.utils.logger import get_logger

logger = get_logger("米游社签到任务")


# ==================== 常量 ====================

# 签到 API（对齐参考项目域名）
ROLES_URL = "https://api-takumi.mihoyo.com/binding/api/getUserGameRolesByCookie"
SIGN_URL = "https://api-takumi.mihoyo.com/event/luna/sign"
ZZZ_SIGN_URL = "https://act-nap-api.mihoyo.com/event/luna/zzz/sign"
ZZZ_INFO_URL = "https://act-nap-api.mihoyo.com/event/luna/zzz/info"
HOME_URL = "https://api-takumi.mihoyo.com/event/luna/home"
INFO_URL = "https://api-takumi.mihoyo.com/event/luna/info"

# Passport Token 派生 API（对齐 MihoyoBBSTools 域名）
PASSPORT_COOKIE_URL = (
    "https://api-takumi.mihoyo.com/auth/api/getCookieAccountInfoBySToken"
)

# DS 签名 Salt（对齐 MihoyoBBSTools）
SALT_WEB = "DlOUwIupfU6YespEUWDJmXtutuXV6owG"       # web 端 salt（游戏签到 GET 请求）
SALT_DATA = "t0qEgfub6cvueAPgR5m9aQWWVciEer7v"      # 有 body/query 的请求（x6）

# 验证码重试配置
CAPTCHA_MAX_RETRIES = 3
CAPTCHA_RETRY_DELAY = (6, 15)  # 秒，随机范围

# 游戏配置（整合 MihoyoBBSTools 全部支持的游戏）
GAME_CONFIG = {
    "hk4e_cn": {
        "name": "原神",
        "act_id": "e202311201442471",
        "sign_url": SIGN_URL,
        "signgame": "hk4e",
        "extra_headers": {
            "x-rpc-signgame": "hk4e",
            "Origin": "https://act.mihoyo.com",
            "Referer": "https://act.mihoyo.com/",
        },
    },
    "hkrpg_cn": {
        "name": "星穹铁道",
        "act_id": "e202304121516551",
        "sign_url": SIGN_URL,
        "signgame": "",
        "extra_headers": {
            "Origin": "https://act.mihoyo.com",
            "Referer": "https://act.mihoyo.com/",
        },
    },
    "nap_cn": {
        "name": "绝区零",
        "act_id": "e202406242138391",
        "sign_url": ZZZ_SIGN_URL,
        "info_url": ZZZ_INFO_URL,
        "signgame": "zzz",
        "extra_headers": {
            "x-rpc-signgame": "zzz",
            "Origin": "https://act.mihoyo.com",
            "Referer": "https://act.mihoyo.com/",
            "Host": "act-nap-api.mihoyo.com",
        },
    },
    "bh2_cn": {
        "name": "崩坏学园2",
        "act_id": "e202203291431091",
        "sign_url": SIGN_URL,
        "signgame": "",
        "extra_headers": {
            "Origin": "https://act.mihoyo.com",
            "Referer": "https://act.mihoyo.com/",
        },
    },
    "bh3_cn": {
        "name": "崩坏3",
        "act_id": "e202306201626331",
        "sign_url": SIGN_URL,
        "signgame": "",
        "extra_headers": {
            "Origin": "https://act.mihoyo.com",
            "Referer": "https://act.mihoyo.com/",
        },
    },
    "nxx_cn": {
        "name": "未定事件簿",
        "act_id": "e202202251749321",
        "sign_url": SIGN_URL,
        "signgame": "",
        "extra_headers": {
            "Origin": "https://act.mihoyo.com",
            "Referer": "https://act.mihoyo.com/",
        },
    },
}

# 通用请求头（对齐 MihoyoBBSTools 游戏签到 headers）
BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://webstatic.mihoyo.com",
    "x-rpc-app_version": "2.99.1",
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Unspecified Device) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Version/4.0 Chrome/103.0.5060.129 Mobile Safari/537.36 "
    "miHoYoBBS/2.99.1",
    "x-rpc-client_type": "5",
    "Referer": "https://act.mihoyo.com/",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,en-US;q=0.8",
    "X-Requested-With": "com.mihoyo.hyperion",
    "x-rpc-channel": "miyousheluodi",
    "Connection": "keep-alive",
    "Content-Type": "application/json;charset=utf-8",
}


# ==================== 工具函数 ====================


class _RiskControlError(Exception):
    """风控异常：API 返回空响应或非 JSON 内容"""
    pass


def _safe_json_parse(response: httpx.Response) -> dict:
    """安全解析 API 响应 JSON

    当响应为空或非 JSON 时（通常是风控拦截），抛出 _RiskControlError。

    Args:
        response: httpx 响应对象

    Returns:
        解析后的 JSON 字典

    Raises:
        _RiskControlError: 响应为空或非 JSON（疑似风控）
    """
    text = response.text.strip()
    if not text:
        raise _RiskControlError("API 返回空响应，疑似被风控")
    try:
        return response.json()
    except Exception:
        raise _RiskControlError(f"API 返回非 JSON 内容，疑似被风控: {text[:100]}")


def _parse_cookie(cookie_str: str) -> Dict[str, str]:
    """解析 cookie 字符串为字典"""
    cookies: Dict[str, str] = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            key, value = item.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def _build_cookie_str(cookies: Dict[str, str]) -> str:
    """将 cookie 字典序列化为字符串"""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _generate_ds(body: str = "", query: str = "") -> str:
    """生成 DS (Dynamic Secret) 签名

    对齐 MihoyoBBSTools：游戏签到 GET 请求使用 SALT_WEB，
    POST 请求（有 body）使用 SALT_DATA。

    Args:
        body: 请求体 JSON 字符串
        query: URL 查询参数字符串

    Returns:
        DS 签名字符串，格式 "t,r,md5hash"
    """
    t = str(int(time.time()))
    r = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))

    if body or query:
        salt = SALT_DATA
        raw = f"salt={salt}&t={t}&r={r}&b={body}&q={query}"
    else:
        salt = SALT_WEB
        raw = f"salt={salt}&t={t}&r={r}"

    md5_hash = hashlib.md5(raw.encode()).hexdigest()
    return f"{t},{r},{md5_hash}"


def _generate_device_id(cookie: str) -> str:
    """从 cookie 生成确定性 device_id

    使用 UUID3 基于 cookie 内容生成，同一 cookie 始终得到同一 device_id，
    与 MihoyoBBSTools 的设备指纹策略一致。

    Args:
        cookie: cookie 字符串

    Returns:
        大写的 UUID 字符串
    """
    return str(uuid.uuid3(uuid.NAMESPACE_URL, cookie))


def _get_stuid(cookies: Dict[str, str]) -> str:
    """从 cookie 中提取米游社 UID

    按优先级依次检查：stuid, ltuid, account_id, login_uid,
    ltuid_v2, account_id_v2
    """
    for key in (
        "stuid", "ltuid", "account_id", "login_uid",
        "ltuid_v2", "account_id_v2",
    ):
        if key in cookies and cookies[key]:
            return cookies[key]
    return ""


def _ensure_uid_aliases(cookies: Dict[str, str], uid: str) -> None:
    """补全所有 UID 别名字段，确保 API 能识别

    米游社 API 可能检查 ltuid、account_id 等特定字段名，
    统一注入所有别名以最大程度兼容。
    """
    for key in ("stuid", "ltuid", "account_id", "login_uid"):
        if key not in cookies or not cookies[key]:
            cookies[key] = uid


# ==================== Token 派生 ====================


async def _derive_cookie_token(
    stoken: str, mid: str, stuid: str, proxy: str | None = None,
) -> tuple[str, str]:
    """从 stoken_v2 + mid 派生 cookie_token

    调用 Passport API getCookieAccountInfoBySToken 获取 cookie_token。

    Args:
        stoken: stoken 值（v2 格式，v2_ 前缀）
        mid: v2 stoken 的配套 mid 字段
        stuid: 米游社 UID
        proxy: 代理地址

    Returns:
        (cookie_token, uid) 元组

    Raises:
        Exception: 派生失败时抛出
    """
    headers = BASE_HEADERS.copy()
    headers["x-rpc-device_id"] = _generate_device_id(stoken + mid)

    # stoken_v2 需要搭配 mid 和 stuid
    stoken_cookies = {
        "stoken": stoken,
        "mid": mid,
        "stuid": stuid,
    }

    async with httpx.AsyncClient(proxy=proxy or Config.proxy) as client:
        response = await client.get(
            PASSPORT_COOKIE_URL,
            headers=headers,
            cookies=stoken_cookies,
            timeout=30.0,
        )
        rsp = _safe_json_parse(response)

    if rsp.get("retcode") != 0:
        raise Exception(f"派生 cookie_token 失败: {rsp.get('message')}")

    data = rsp.get("data", {})
    cookie_token = data.get("cookie_token", "")
    uid = data.get("uid", "")
    if not cookie_token:
        raise Exception("派生 cookie_token 失败: 返回数据无 cookie_token")

    logger.debug(f"成功从 stoken 派生 cookie_token, uid={uid}")
    return cookie_token, uid


# ==================== 签到主流程 ====================


async def miyoushe_sign_in(cookie: str, proxy: str | None = None) -> list[dict]:
    """米游社游戏签到

    支持多种 cookie 认证策略：
    1. cookie_token + UID → 直接使用
    2. stoken_v2 + mid + UID → 派生 cookie_token 后使用
    3. stoken_v1 + UID → 暂不支持派生（需 mid），日志提示

    Args:
        cookie: cookie 字符串，至少包含 UID 字段 + (cookie_token 或 stoken)
        proxy: 代理地址

    Returns:
        签到结果列表，每项包含 account, game, platform, status, reward, reason
    """
    results = []
    cookies = _parse_cookie(cookie)
    stuid = _get_stuid(cookies)

    if not stuid:
        logger.error("Cookie 缺少 UID 字段 (stuid/ltuid/account_id)")
        return [{
            "account": "未知/米游社",
            "game": "米游社",
            "platform": "米游社",
            "status": "失败",
            "reward": "",
            "reason": "Cookie 缺少 UID 字段",
        }]

    # ---- 认证策略选择 ----
    effective_cookies = cookies.copy()

    if "cookie_token" in cookies:
        # 策略 1: cookie_token + UID，直接使用
        logger.debug("使用 cookie_token + UID 认证")
    elif "stoken" in cookies and "mid" in cookies:
        # 策略 2: stoken_v2 + mid，派生 cookie_token
        logger.info("缺少 cookie_token，尝试从 stoken 派生")
        try:
            derived_token, derived_uid = await _derive_cookie_token(
                cookies["stoken"], cookies["mid"], stuid, proxy,
            )
            effective_cookies["cookie_token"] = derived_token
            if derived_uid:
                _ensure_uid_aliases(effective_cookies, derived_uid)
        except Exception as e:
            logger.error(f"从 stoken 派生 cookie_token 失败: {e}")
            return [{
                "account": f"{stuid}/米游社",
                "game": "米游社",
                "platform": "米游社",
                "status": "失败",
                "reward": "",
                "reason": f"派生 cookie_token 失败: {e}",
            }]
    elif "stoken" in cookies:
        # 策略 3: stoken_v1 无 mid，无法派生
        logger.error("仅有 v1 stoken 但缺少 mid，无法派生 cookie_token，请补充完整 cookie")
        return [{
            "account": f"{stuid}/米游社",
            "game": "米游社",
            "platform": "米游社",
            "status": "失败",
            "reward": "",
            "reason": "缺少 cookie_token 和 mid，无法完成认证",
        }]
    else:
        logger.error("Cookie 缺少认证字段 (cookie_token 或 stoken)")
        return [{
            "account": f"{stuid}/米游社",
            "game": "米游社",
            "platform": "米游社",
            "status": "失败",
            "reward": "",
            "reason": "Cookie 缺少认证字段 (cookie_token 或 stoken)",
        }]

    # 补全 UID 别名
    _ensure_uid_aliases(effective_cookies, stuid)
    effective_cookie = _build_cookie_str(effective_cookies)

    # 获取游戏角色列表
    try:
        roles = await _get_game_roles(effective_cookie)
    except _RiskControlError:
        logger.warning(f"获取米游社游戏角色被风控")
        return [{
            "account": f"{stuid}/米游社",
            "game": "米游社",
            "platform": "米游社",
            "status": "风控",
            "reward": "",
            "reason": "账号被风控，接口返回异常",
        }]
    except Exception as e:
        logger.error(f"获取米游社游戏角色失败: {e}")
        return [{
            "account": f"{stuid}/米游社",
            "game": "米游社",
            "platform": "米游社",
            "status": "失败",
            "reward": "",
            "reason": f"获取角色列表失败: {e}",
        }]

    if not roles:
        logger.warning("未找到米游社绑定的游戏角色")
        return results

    # 逐游戏签到
    for role in roles:
        game_biz = role.get("game_biz", "")
        region = role.get("region", "")
        game_uid = role.get("game_uid", "")
        nickname = role.get("nickname", "")

        game_cfg = GAME_CONFIG.get(game_biz)
        if not game_cfg:
            continue

        # account 格式: 别名/昵称(uid)
        account = f"{nickname}/{nickname}({game_uid})" if game_uid else f"{nickname}/米游社"

        # 检查今日是否已签到
        try:
            is_signed = await _check_sign_info(effective_cookie, game_cfg, region, game_uid)
            if is_signed:
                results.append({
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "已签到",
                    "reward": "",
                    "reason": "",
                })
                logger.info(f"{account} {game_cfg['name']} 今日已签到")
                continue
        except _RiskControlError:
            results.append({
                "account": account,
                "game": game_cfg["name"],
                "platform": "米游社",
                "status": "风控",
                "reward": "",
                "reason": "账号被风控，签到接口返回异常",
            })
            logger.warning(f"{account} {game_cfg['name']} 账号被风控")
            continue
        except Exception as e:
            logger.warning(f"检查签到状态异常: {e}")

        # 执行签到
        try:
            sign_result = await _do_sign(effective_cookie, game_cfg, region, game_uid, account)
            results.append(sign_result)
        except _RiskControlError:
            results.append({
                "account": account,
                "game": game_cfg["name"],
                "platform": "米游社",
                "status": "风控",
                "reward": "",
                "reason": "账号被风控，签到接口返回异常",
            })
            logger.warning(f"{account} {game_cfg['name']} 签到时被风控")
        except Exception as e:
            results.append({
                "account": account,
                "game": game_cfg["name"],
                "platform": "米游社",
                "status": "失败",
                "reward": "",
                "reason": str(e),
            })
            logger.error(f"{account} {game_cfg['name']} 签到异常: {e}")

        # 间隔防风控（对齐 MihoyoBBSTools：随机 2-8 秒）
        await asyncio.sleep(random.uniform(2.0, 8.0))

    return results


async def _get_game_roles(cookie: str) -> list[dict]:
    """获取游戏角色列表

    兼容两种 API 返回结构：
    - 扁平结构: data.list 直接是角色数组
    - 嵌套结构: data.list[].list[] 是角色数组（按游戏分组）
    """
    headers = BASE_HEADERS.copy()
    headers["DS"] = _generate_ds()
    headers["x-rpc-device_id"] = _generate_device_id(cookie)

    async with httpx.AsyncClient(proxy=Config.proxy) as client:
        response = await client.get(
            ROLES_URL,
            headers=headers,
            cookies=_parse_cookie(cookie),
            timeout=30.0,
        )
        rsp = _safe_json_parse(response)

    if rsp.get("retcode") != 0:
        raise Exception(f"获取角色列表失败: {rsp.get('message')}")

    data_list = rsp.get("data", {}).get("list", [])
    roles = []

    if not data_list:
        return roles

    # 判断数据结构：有 "list" 子键 = 嵌套，否则 = 扁平
    if "list" in data_list[0]:
        # 嵌套结构: data.list[].list[]
        for item in data_list:
            for role in item.get("list", []):
                if role.get("game_biz") in GAME_CONFIG:
                    roles.append(role)
    else:
        # 扁平结构: data.list[]
        for role in data_list:
            if role.get("game_biz") in GAME_CONFIG:
                roles.append(role)

    return roles


async def _check_sign_info(
    cookie: str, game_cfg: dict, region: str, uid: str
) -> bool:
    """检查今日是否已签到"""
    headers = BASE_HEADERS.copy()
    query = f"lang=zh-cn&act_id={game_cfg['act_id']}&region={region}&uid={uid}"
    headers["DS"] = _generate_ds(query=query)
    headers["x-rpc-device_id"] = _generate_device_id(cookie)
    headers.update(game_cfg.get("extra_headers", {}))

    url = f"{game_cfg.get('info_url', INFO_URL)}?{query}"

    async with httpx.AsyncClient(proxy=Config.proxy) as client:
        response = await client.get(
            url,
            headers=headers,
            cookies=_parse_cookie(cookie),
            timeout=30.0,
        )
        rsp = _safe_json_parse(response)

    if rsp.get("retcode") != 0:
        return False

    sign_info = rsp.get("data", {})
    is_sign = sign_info.get("is_sign", False)
    return is_sign


async def _do_sign(
    cookie: str, game_cfg: dict, region: str, uid: str, account: str = ""
) -> dict:
    """执行签到（含验证码重试）

    当签到返回极验（Geetest）验证码时，自动重试最多 CAPTCHA_MAX_RETRIES 次。
    两次重试之间有随机延迟以防触发更严格的风控。

    Args:
        cookie: cookie 字符串
        game_cfg: 游戏配置
        region: 服务器区号
        uid: 游戏 UID
        account: 账号标识（如 nickname/nickname(uid)），为空时用 stuid 构造
    """
    cookies = _parse_cookie(cookie)
    stuid = _get_stuid(cookies)
    if not account:
        account = f"{stuid}/{stuid}({uid})" if uid else f"{stuid}/米游社"

    body = json.dumps(
        {"act_id": game_cfg["act_id"], "region": region, "uid": uid},
        separators=(",", ":"),
    )
    sign_url = game_cfg["sign_url"]

    for attempt in range(CAPTCHA_MAX_RETRIES + 1):
        headers = BASE_HEADERS.copy()
        headers["DS"] = _generate_ds(body=body)
        headers["x-rpc-device_id"] = _generate_device_id(cookie)
        headers.update(game_cfg.get("extra_headers", {}))

        async with httpx.AsyncClient(proxy=Config.proxy) as client:
            response = await client.post(
                sign_url,
                headers=headers,
                content=body,
                cookies=cookies,
                timeout=30.0,
            )
            rsp = _safe_json_parse(response)

        retcode = rsp.get("retcode", 0)
        data = rsp.get("data") or {}

        # ---- 成功 ----
        if retcode == 0:
            reward = ""
            award = data.get("award", {})
            if award:
                reward = f"{award.get('name', '')}x{award.get('cnt', 1)}"
            logger.info(f"{account} {game_cfg['name']} 签到成功")
            return {
                "account": account,
                "game": game_cfg["name"],
                "platform": "米游社",
                "status": "成功",
                "reward": reward,
                "reason": "",
            }

        # ---- 已签到 ----
        if retcode == -5003 or "请勿重复签到" in rsp.get("message", ""):
            return {
                "account": account,
                "game": game_cfg["name"],
                "platform": "米游社",
                "status": "已签到",
                "reward": "",
                "reason": "",
            }

        # ---- -100: cookie_token 过期，尝试多种方式恢复 ----
        if retcode == -100:
            parsed = _parse_cookie(cookie)
            has_stoken = "stoken" in parsed
            has_v2 = "cookie_token_v2" in parsed

            refreshed = False

            # 方式 1: 用 stoken 派生新 cookie_token
            if has_stoken and "mid" in parsed and attempt < CAPTCHA_MAX_RETRIES:
                stuid = _get_stuid(parsed)
                logger.warning(
                    f"{account} {game_cfg['name']} cookie_token 过期，"
                    f"尝试用 stoken 刷新"
                )
                try:
                    new_token, new_uid = await _derive_cookie_token(
                        parsed["stoken"], parsed["mid"], stuid,
                    )
                    parsed["cookie_token"] = new_token
                    if new_uid:
                        _ensure_uid_aliases(parsed, new_uid)
                    cookie = _build_cookie_str(parsed)
                    refreshed = True
                except Exception as e:
                    logger.error(f"stoken 刷新失败: {e}")

            # 方式 2: 用 cookie_token_v2 替换 cookie_token
            if not refreshed and has_v2 and attempt < CAPTCHA_MAX_RETRIES:
                logger.info(
                    f"{account} {game_cfg['name']} 尝试用 cookie_token_v2 替代"
                )
                parsed["cookie_token"] = parsed["cookie_token_v2"]
                cookie = _build_cookie_str(parsed)
                refreshed = True

            # 方式 3: 用 ltoken 替换 cookie_token
            if not refreshed and "ltoken" in parsed and attempt < CAPTCHA_MAX_RETRIES:
                logger.info(
                    f"{account} {game_cfg['name']} 尝试用 ltoken 替代"
                )
                parsed["cookie_token"] = parsed["ltoken"]
                cookie = _build_cookie_str(parsed)
                refreshed = True

            if refreshed:
                await asyncio.sleep(random.uniform(1.0, 3.0))
                continue

            return {
                "account": account,
                "game": game_cfg["name"],
                "platform": "米游社",
                "status": "失败",
                "reward": "",
                "reason": "请登录后重试（cookie_token 过期，无可用替代 token）",
            }

        # ---- 需要验证码（极验风控） ----
        if data.get("gt") and data.get("challenge"):
            if attempt < CAPTCHA_MAX_RETRIES:
                delay = random.uniform(*CAPTCHA_RETRY_DELAY)
                logger.warning(
                    f"{account} {game_cfg['name']} 触发验证码 "
                    f"(第 {attempt + 1}/{CAPTCHA_MAX_RETRIES} 次)，"
                    f"等待 {delay:.0f} 秒后重试"
                )
                await asyncio.sleep(delay)
                continue
            else:
                logger.error(
                    f"{account} {game_cfg['name']} 验证码重试耗尽，签到失败"
                )
                return {
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "风控",
                    "reward": "",
                    "reason": "触发极验验证码，重试次数耗尽",
                }

        # ---- retcode 1034：高频风控 ----
        if retcode == 1034:
            if attempt < CAPTCHA_MAX_RETRIES:
                delay = random.uniform(*CAPTCHA_RETRY_DELAY)
                logger.warning(
                    f"{account} {game_cfg['name']} 高频风控 (retcode=1034) "
                    f"(第 {attempt + 1}/{CAPTCHA_MAX_RETRIES} 次)，"
                    f"等待 {delay:.0f} 秒后重试"
                )
                await asyncio.sleep(delay)
                continue
            else:
                return {
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "风控",
                    "reward": "",
                    "reason": "高频风控 (retcode=1034)，重试次数耗尽",
                }

        # ---- 其他失败 ----
        message = rsp.get("message", "未知错误")
        logger.error(f"{account} {game_cfg['name']} 签到失败: {message}")
        return {
            "account": account,
            "game": game_cfg["name"],
            "platform": "米游社",
            "status": "失败",
            "reward": "",
            "reason": message,
        }

    # 理论上不会到这里
    return {
        "account": account,
        "game": game_cfg["name"],
        "platform": "米游社",
        "status": "失败",
        "reward": "",
        "reason": "签到流程异常退出",
    }
