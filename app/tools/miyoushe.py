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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from typing import Dict

from app.core import Config
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

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
SALT_WEB = "DlOUwIupfU6YespEUWDJmXtutuXV6owG"  # web 端 salt（游戏社区 GET 请求）
SALT_DATA = "t0qEgfub6cvueAPgR5m9aQWWVciEer7v"  # 有 body/query 的请求（x6）

# 验证码重试配置
CAPTCHA_MAX_RETRIES = 3
CAPTCHA_RETRY_DELAY = (6, 15)  # 秒，随机范围


@dataclass(frozen=True)
class MiyousheSessionCapabilities:
    """米游社会话的脱敏能力状态，不包含任何凭据值。"""

    has_uid: bool
    has_cookie_token: bool
    has_stoken: bool
    has_stoken_v2: bool
    has_mid: bool

    @property
    def activity_missing_fields(self) -> tuple[str, ...]:
        """返回实时便笺缺失的必要凭据字段名。"""

        missing = []
        if not self.has_stoken_v2:
            missing.append("stoken_v2")
        if not self.has_mid:
            missing.append("mid")
        return tuple(missing)

    @property
    def activity_ready(self) -> bool:
        """是否具备实时便笺所需的 v2 stoken 能力。"""

        return self.has_uid and not self.activity_missing_fields

    @property
    def activity_reason(self) -> str:
        """返回可展示但不含凭据值的受限原因。"""

        missing = self.activity_missing_fields
        if not self.has_uid:
            return "米游社凭据缺少 UID 字段"
        if not missing:
            return ""
        return f"米游社实时便笺需要完整的 {' 和 '.join(missing)}，当前凭据能力受限"


@dataclass(frozen=True)
class MiyousheSession:
    """一次米游社运行使用的内存会话。"""

    cookies: dict[str, str] = field(repr=False)
    uid: str
    device_id: str = field(repr=False)
    capabilities: MiyousheSessionCapabilities


class _SignOutcome(tuple):
    """签到结果与刷新凭据的兼容返回值。

    新版调用方可继续解包为 ``(result, cookie)``；旧调用方读取
    ``outcome["status"]`` 时仍会得到签到结果字段。
    """

    def __new__(cls, result: dict[str, object], cookie: str):
        return super().__new__(cls, (result, cookie))

    def __getitem__(self, key):
        if isinstance(key, str):
            return super().__getitem__(0)[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        return super().__getitem__(0).get(key, default)


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

# 通用请求头（对齐 MihoyoBBSTools 游戏社区 headers）
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


def _log_miyoushe_exception(stage: str, error: Exception) -> str:
    """按异常类型记录米游社失败，并返回安全的非空原因。"""

    expected = isinstance(
        error,
        (
            _RiskControlError,
            ValueError,
            httpx.HTTPError,
            TimeoutError,
            ConnectionError,
        ),
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


def _safe_json_parse(response: httpx.Response) -> dict[str, object]:
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
        data = response.json()
    except ValueError as exc:
        raise _RiskControlError(
            f"API 返回非 JSON 内容，疑似被风控: {text[:100]}"
        ) from exc
    if not isinstance(data, dict):
        raise _RiskControlError("API 返回异常 JSON 格式，疑似被风控")
    return data


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


def merge_miyoushe_cookie_update(cookie: str, updated_cookie: str) -> str:
    """合并刷新结果，避免新增 Cookie 字段时丢失原始认证字段。"""
    current = _parse_cookie(cookie)
    refreshed = _parse_cookie(updated_cookie)
    if not refreshed:
        return cookie
    if not current:
        return updated_cookie

    merged = current.copy()
    for key, value in refreshed.items():
        if value:
            merged[key] = value
    return _build_cookie_str(merged)


def _generate_ds(body: str = "", query: str = "") -> str:
    """生成 DS (Dynamic Secret) 签名

    对齐 MihoyoBBSTools：游戏社区 GET 请求使用 SALT_WEB，
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
    """生成确定性 device_id

    优先以 cookie 中的米游社 UID（stuid 等）为种子，保证同一账号在
    token 刷新（cookie 串变化）后设备指纹保持稳定，避免触发风控；
    无法提取 UID 时退回以整个 cookie 串为种子。
    与 MihoyoBBSTools 的设备指纹策略一致。

    Args:
        cookie: cookie 字符串

    Returns:
        UUID 字符串
    """
    try:
        seed = _get_stuid(_parse_cookie(cookie)) or cookie
    except Exception:
        seed = cookie
    return str(uuid.uuid3(uuid.NAMESPACE_URL, seed))


def _get_stuid(cookies: Dict[str, str]) -> str:
    """从 cookie 中提取米游社 UID

    按优先级依次检查：stuid, stuid_v2, ltuid, account_id, login_uid,
    ltuid_v2, account_id_v2
    """
    for key in (
        "stuid",
        "stuid_v2",
        "ltuid",
        "account_id",
        "login_uid",
        "ltuid_v2",
        "account_id_v2",
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


def _ensure_auth_aliases(cookies: Dict[str, str]) -> None:
    """将 Passport v2 认证字段补齐为签到接口兼容的旧字段名。"""
    aliases = {
        "cookie_token_v2": "cookie_token",
        "stoken_v2": "stoken",
        "mid_v2": "mid",
        "ltmid_v2": "mid",
        "account_mid_v2": "mid",
    }
    for source, target in aliases.items():
        if not cookies.get(target) and cookies.get(source):
            cookies[target] = cookies[source]


def prepare_miyoushe_session(cookie: str) -> MiyousheSession:
    """统一解析米游社 Cookie、认证别名、设备 ID 和脱敏能力。"""

    cookies = _parse_cookie(cookie)
    _ensure_auth_aliases(cookies)
    uid = _get_stuid(cookies)
    stoken = str(cookies.get("stoken") or "").strip()
    stoken_v2 = str(cookies.get("stoken_v2") or "").strip()
    capabilities = MiyousheSessionCapabilities(
        has_uid=bool(uid),
        has_cookie_token=bool(cookies.get("cookie_token")),
        has_stoken=bool(stoken),
        has_stoken_v2=bool(stoken_v2 or stoken.startswith("v2_")),
        has_mid=bool(cookies.get("mid")),
    )
    return MiyousheSession(
        cookies=cookies,
        uid=uid,
        device_id=_generate_device_id(cookie),
        capabilities=capabilities,
    )


def validate_miyoushe_cookie(cookie: str) -> None:
    """校验米游社凭据包含签到所需的 UID 和认证字段。"""

    session = prepare_miyoushe_session(cookie)
    cookies = session.cookies
    if not session.capabilities.has_uid:
        raise ValueError("Cookie 缺少 UID 字段")
    if session.capabilities.has_cookie_token:
        return
    if session.capabilities.has_stoken and session.capabilities.has_mid:
        return
    if session.capabilities.has_stoken:
        raise ValueError("stoken Cookie 缺少 mid 字段")
    raise ValueError("Cookie 缺少认证字段 (cookie_token 或 stoken)")


# ==================== Token 派生 ====================


async def _derive_cookie_token(
    stoken: str,
    mid: str,
    stuid: str,
    proxy: str | None = None,
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

    resolved_proxy = proxy if proxy is not None else Config.proxy
    async with httpx.AsyncClient(proxy=resolved_proxy, trust_env=False) as client:
        response = await client.get(
            PASSPORT_COOKIE_URL,
            headers=headers,
            cookies=stoken_cookies,
            timeout=30.0,
        )
        rsp = _safe_json_parse(response)

    if rsp.get("retcode") != 0:
        raise ValueError(f"派生 cookie_token 失败: {rsp.get('message')}")

    data = rsp.get("data", {})
    cookie_token = data.get("cookie_token", "")
    uid = data.get("uid", "")
    if not cookie_token:
        raise ValueError("派生 cookie_token 失败: 返回数据无 cookie_token")

    logger.debug(f"成功从 stoken 派生 cookie_token, uid={uid}")
    return cookie_token, uid


# ==================== 签到主流程 ====================


async def miyoushe_sign_in(
    cookie: str,
    proxy: str | None = None,
    *,
    on_credential_update: Callable[[str], Awaitable[None]] | None = None,
) -> list[dict[str, object]]:
    """米游社社区签到

    支持多种 cookie 认证策略：
    1. cookie_token + UID → 直接使用
    2. cookie_token_v2 + UID → 兼容 Passport/二维码登录凭据
    3. stoken_v2 + mid + UID → 派生 cookie_token 后使用
    4. stoken_v1 + UID → 暂不支持派生（需 mid），日志提示

    Args:
        cookie: cookie 字符串，至少包含 UID 字段 + (cookie_token 或 stoken)
        proxy: 代理地址
        on_credential_update: 凭据被替换后的可选回写回调

    Returns:
        签到结果列表，每项包含 account, game, platform, status, reward, reason
    """
    results = []
    updated_cookie = ""

    async def report_credential_update() -> None:
        if on_credential_update is None or not updated_cookie:
            return
        try:
            await on_credential_update(updated_cookie)
        except Exception as e:
            _log_miyoushe_exception("米游社凭据回写失败", e)

    session = prepare_miyoushe_session(cookie)
    cookies = dict(session.cookies)
    stuid = session.uid
    device_id = session.device_id

    if not stuid:
        logger.warning("Cookie 缺少 UID 字段 (stuid/ltuid/account_id)")
        return [
            {
                "account": "未知/米游社",
                "game": "米游社",
                "platform": "米游社",
                "status": "失败",
                "reward": "",
                "reason": "Cookie 缺少 UID 字段",
            }
        ]

    # ---- 认证策略选择 ----
    effective_cookies = cookies.copy()

    if cookies.get("cookie_token") or cookies.get("cookie_token_v2"):
        # 策略 1/2: QR/Passport 可能只返回 cookie_token_v2。
        # 保留 v2 字段，同时补充旧字段供签到接口和旧配置兼容。
        if not cookies.get("cookie_token") and cookies.get("cookie_token_v2"):
            effective_cookies["cookie_token"] = cookies["cookie_token_v2"]
        logger.debug("使用 cookie_token/cookie_token_v2 + UID 认证")
    elif cookies.get("stoken") and cookies.get("mid"):
        # 策略 3: stoken_v2 + mid，派生 cookie_token
        logger.info("缺少 cookie_token，尝试从 stoken 派生")
        try:
            derived_token, derived_uid = await _derive_cookie_token(
                cookies["stoken"],
                cookies["mid"],
                stuid,
                proxy,
            )
            effective_cookies["cookie_token"] = derived_token
            if derived_uid:
                _ensure_uid_aliases(effective_cookies, derived_uid)
            updated_cookie = _build_cookie_str(effective_cookies)
        except Exception as e:
            reason = _log_miyoushe_exception(
                "从 stoken 派生 cookie_token 失败",
                e,
            )
            return [
                {
                    "account": f"{stuid}/米游社",
                    "game": "米游社",
                    "platform": "米游社",
                    "status": "失败",
                    "reward": "",
                    "reason": reason,
                }
            ]
    elif cookies.get("stoken"):
        # 策略 4: stoken_v1 无 mid，无法派生
        logger.warning(
            "仅有 v1 stoken 但缺少 mid，无法派生 cookie_token，请补充完整 cookie"
        )
        return [
            {
                "account": f"{stuid}/米游社",
                "game": "米游社",
                "platform": "米游社",
                "status": "失败",
                "reward": "",
                "reason": "缺少 cookie_token 和 mid，无法完成认证",
            }
        ]
    else:
        logger.warning("Cookie 缺少认证字段 (cookie_token 或 stoken)")
        return [
            {
                "account": f"{stuid}/米游社",
                "game": "米游社",
                "platform": "米游社",
                "status": "失败",
                "reward": "",
                "reason": "Cookie 缺少认证字段 (cookie_token 或 stoken)",
            }
        ]

    # 补全 UID 别名
    _ensure_uid_aliases(effective_cookies, stuid)
    effective_cookie = _build_cookie_str(effective_cookies)

    # 获取游戏角色列表
    try:
        roles = await _get_game_roles(
            effective_cookie,
            proxy=proxy,
            device_id=device_id,
        )
    except _RiskControlError:
        logger.warning("获取米游社游戏角色被风控")
        await report_credential_update()
        return [
            {
                "account": f"{stuid}/米游社",
                "game": "米游社",
                "platform": "米游社",
                "status": "风控",
                "reward": "",
                "reason": "账号被风控，接口返回异常",
            }
        ]
    except Exception as e:
        reason = _log_miyoushe_exception("获取米游社游戏角色失败", e)
        await report_credential_update()
        return [
            {
                "account": f"{stuid}/米游社",
                "game": "米游社",
                "platform": "米游社",
                "status": "失败",
                "reward": "",
                "reason": reason,
            }
        ]

    if not roles:
        logger.warning("未找到米游社绑定的游戏角色")
        await report_credential_update()
        return results

    # 逐游戏执行社区签到
    for index, role in enumerate(roles):
        game_biz = role.get("game_biz", "")
        region = role.get("region", "")
        game_uid = role.get("game_uid", "")
        nickname = role.get("nickname", "")

        game_cfg = GAME_CONFIG.get(game_biz)
        if not game_cfg:
            continue

        # account 格式: 别名/昵称(uid)
        account = (
            f"{nickname}/{nickname}({game_uid})" if game_uid else f"{nickname}/米游社"
        )

        # 检查今日是否已签到
        try:
            is_signed = await _check_sign_info(
                effective_cookie,
                game_cfg,
                region,
                game_uid,
                proxy=proxy,
                device_id=device_id,
            )
            if is_signed:
                results.append(
                    {
                        "account": account,
                        "game": game_cfg["name"],
                        "platform": "米游社",
                        "status": "已签到",
                        "reward": "",
                        "reason": "",
                    }
                )
                logger.info(f"{account} {game_cfg['name']} 今日已签到")
                continue
        except _RiskControlError:
            results.append(
                {
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "风控",
                    "reward": "",
                    "reason": "账号被风控，签到接口返回异常",
                }
            )
            logger.warning(f"{account} {game_cfg['name']} 账号被风控")
            continue
        except Exception as e:
            _log_miyoushe_exception("检查米游社签到状态失败", e)

        # 执行签到
        try:
            sign_result, refreshed_cookie = await _do_sign(
                effective_cookie,
                game_cfg,
                region,
                game_uid,
                account,
                proxy=proxy,
                device_id=device_id,
            )
            results.append(sign_result)
            # cookie_token 过期被刷新后，同一轮后续游戏复用新 cookie，
            # 避免每个游戏重复走派生接口增加风控概率。
            if refreshed_cookie and refreshed_cookie != effective_cookie:
                effective_cookie = refreshed_cookie
                updated_cookie = refreshed_cookie
        except _RiskControlError:
            results.append(
                {
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "风控",
                    "reward": "",
                    "reason": "账号被风控，签到接口返回异常",
                }
            )
            logger.warning(f"{account} {game_cfg['name']} 签到时被风控")
        except Exception as e:
            reason = _log_miyoushe_exception(
                f"{game_cfg['name']}签到失败",
                e,
            )
            results.append(
                {
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "失败",
                    "reward": "",
                    "reason": reason,
                }
            )

        # 间隔防风控（对齐 MihoyoBBSTools：随机 2-8 秒）
        if index < len(roles) - 1:
            await asyncio.sleep(random.uniform(2.0, 8.0))

    await report_credential_update()

    return results


async def _get_game_roles(
    cookie: str,
    *,
    proxy: str | None = None,
    device_id: str = "",
) -> list[dict[str, object]]:
    """获取游戏角色列表

    兼容两种 API 返回结构：
    - 扁平结构: data.list 直接是角色数组
    - 嵌套结构: data.list[].list[] 是角色数组（按游戏分组）
    """
    headers = BASE_HEADERS.copy()
    headers["DS"] = _generate_ds()
    headers["x-rpc-device_id"] = device_id or _generate_device_id(cookie)

    resolved_proxy = proxy if proxy is not None else Config.proxy
    async with httpx.AsyncClient(proxy=resolved_proxy, trust_env=False) as client:
        response = await client.get(
            ROLES_URL,
            headers=headers,
            cookies=_parse_cookie(cookie),
            timeout=30.0,
        )
        rsp = _safe_json_parse(response)

    if rsp.get("retcode") != 0:
        raise ValueError(f"获取角色列表失败: {rsp.get('message')}")

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
    cookie: str,
    game_cfg: dict[str, object],
    region: str,
    uid: str,
    *,
    proxy: str | None = None,
    device_id: str = "",
) -> bool:
    """检查今日是否已签到"""
    headers = BASE_HEADERS.copy()
    query = f"lang=zh-cn&act_id={game_cfg['act_id']}&region={region}&uid={uid}"
    headers["DS"] = _generate_ds(query=query)
    headers["x-rpc-device_id"] = device_id or _generate_device_id(cookie)
    headers.update(game_cfg.get("extra_headers", {}))

    url = f"{game_cfg.get('info_url', INFO_URL)}?{query}"

    resolved_proxy = proxy if proxy is not None else Config.proxy
    async with httpx.AsyncClient(proxy=resolved_proxy, trust_env=False) as client:
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
    cookie: str,
    game_cfg: dict[str, object],
    region: str,
    uid: str,
    account: str = "",
    *,
    proxy: str | None = None,
    device_id: str = "",
) -> tuple[dict[str, object], str]:
    """执行签到（含验证码重试）

    当签到返回极验（Geetest）验证码时，自动重试最多 CAPTCHA_MAX_RETRIES 次。
    两次重试之间有随机延迟以防触发更严格的风控。

    Args:
        cookie: cookie 字符串
        game_cfg: 游戏配置
        region: 服务器区号
        uid: 游戏 UID
        account: 账号标识（如 nickname/nickname(uid)），为空时用 stuid 构造

    Returns:
        (签到结果, 实际生效的 cookie 字符串) 元组；
        cookie_token 过期被刷新后返回新 cookie，供同一轮后续游戏复用。
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
        headers["x-rpc-device_id"] = device_id or _generate_device_id(cookie)
        headers.update(game_cfg.get("extra_headers", {}))

        resolved_proxy = proxy if proxy is not None else Config.proxy
        async with httpx.AsyncClient(proxy=resolved_proxy, trust_env=False) as client:
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
            return _SignOutcome(
                {
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "成功",
                    "reward": reward,
                    "reason": "",
                },
                cookie,
            )

        # ---- 已签到 ----
        if retcode == -5003 or "请勿重复签到" in rsp.get("message", ""):
            return _SignOutcome(
                {
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "已签到",
                    "reward": "",
                    "reason": "",
                },
                cookie,
            )

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
                        parsed["stoken"],
                        parsed["mid"],
                        stuid,
                        proxy=proxy,
                    )
                    parsed["cookie_token"] = new_token
                    if new_uid:
                        _ensure_uid_aliases(parsed, new_uid)
                    cookie = _build_cookie_str(parsed)
                    refreshed = True
                except Exception as e:
                    _log_miyoushe_exception("stoken 刷新失败", e)

            # 方式 2: 用 cookie_token_v2 替换 cookie_token
            if not refreshed and has_v2 and attempt < CAPTCHA_MAX_RETRIES:
                logger.info(f"{account} {game_cfg['name']} 尝试用 cookie_token_v2 替代")
                parsed["cookie_token"] = parsed["cookie_token_v2"]
                cookie = _build_cookie_str(parsed)
                refreshed = True

            # 方式 3: 用 ltoken 替换 cookie_token
            if not refreshed and "ltoken" in parsed and attempt < CAPTCHA_MAX_RETRIES:
                logger.info(f"{account} {game_cfg['name']} 尝试用 ltoken 替代")
                parsed["cookie_token"] = parsed["ltoken"]
                cookie = _build_cookie_str(parsed)
                refreshed = True

            if refreshed:
                cookies = parsed.copy()
                await asyncio.sleep(random.uniform(1.0, 3.0))
                continue

            return _SignOutcome(
                {
                    "account": account,
                    "game": game_cfg["name"],
                    "platform": "米游社",
                    "status": "失败",
                    "reward": "",
                    "reason": "请登录后重试（cookie_token 过期，无可用替代 token）",
                },
                cookie,
            )

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
                logger.warning(f"{account} {game_cfg['name']} 验证码重试耗尽，签到失败")
                return _SignOutcome(
                    {
                        "account": account,
                        "game": game_cfg["name"],
                        "platform": "米游社",
                        "status": "风控",
                        "reward": "",
                        "reason": "触发极验验证码，重试次数耗尽",
                    },
                    cookie,
                )

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
                return _SignOutcome(
                    {
                        "account": account,
                        "game": game_cfg["name"],
                        "platform": "米游社",
                        "status": "风控",
                        "reward": "",
                        "reason": "高频风控 (retcode=1034)，重试次数耗尽",
                    },
                    cookie,
                )

        # ---- 其他失败 ----
        message = rsp.get("message", "未知错误")
        logger.warning(f"{account} {game_cfg['name']} 签到失败: {message}")
        return _SignOutcome(
            {
                "account": account,
                "game": game_cfg["name"],
                "platform": "米游社",
                "status": "失败",
                "reward": "",
                "reason": message,
            },
            cookie,
        )

    # 理论上不会到这里
    return _SignOutcome(
        {
            "account": account,
            "game": game_cfg["name"],
            "platform": "米游社",
            "status": "失败",
            "reward": "",
            "reason": "签到流程异常退出",
        },
        cookie,
    )
