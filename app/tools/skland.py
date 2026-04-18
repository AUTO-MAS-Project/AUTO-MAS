#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates work covered by the following copyright and
#   permission notice:
#
#       skland-checkin-ghaction Copyright © 2023 Yanstory
#       https://github.com/Yanstory/skland-checkin-ghaction
#
#       skland-daily-attendance Copyright © 2023-2025 enpitsuLin
#       https://github.com/enpitsuLin/skland-daily-attendance

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


import time
import json
import uuid
import hmac
import gzip
import httpx
import base64
import asyncio
import hashlib
from urllib import parse
from datetime import datetime, timedelta
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, AES, DES
from Crypto.Util.Padding import pad

from typing import Dict, Any, cast

from app.utils.constants import SKLAND_SM_CONFIG, BROWSER_ENV, DES_RULE
from app.utils.logger import get_logger

logger = get_logger("森空岛签到任务")


def get_proxy(proxy: str | None = None) -> Any:
    if proxy is not None:
        return proxy

    from app.core import Config

    return Config.proxy


def md5_hash(data: str) -> str:
    """MD5哈希"""
    return hashlib.md5(data.encode()).hexdigest()


def get_sm_id() -> str:
    """生成数美ID"""
    now = time.localtime()
    _time = time.strftime("%Y%m%d%H%M%S", now)
    uid = str(uuid.uuid4())
    uid_md5 = md5_hash(uid)
    v = f"{_time}{uid_md5}00"
    smsk_web = md5_hash(f"smsk_web_{v}")[:14]
    return f"{v}{smsk_web}0"


def get_tn(obj: Dict[str, Any]) -> str:
    """计算tn值"""
    sorted_keys = sorted(obj.keys())
    result_list: list[str] = []

    for key in sorted_keys:
        v = obj[key]
        if isinstance(v, (int, float)):
            v = str(int(v * 10000))
        elif isinstance(v, dict):
            v = get_tn(v)
        else:
            v = str(v)
        result_list.append(v)

    return "".join(result_list)


def encrypt_rsa(message: str, public_key_str: str) -> str:
    """RSA加密"""
    try:
        formatted_key = "\n".join(
            [public_key_str[i : i + 64] for i in range(0, len(public_key_str), 64)]
        )
        public_key_pem = (
            f"-----BEGIN PUBLIC KEY-----\n{formatted_key}\n-----END PUBLIC KEY-----"
        )
        key = RSA.import_key(public_key_pem)
        cipher = PKCS1_v1_5.new(key)
        encrypted = cipher.encrypt(message.encode())
        return base64.b64encode(encrypted).decode()
    except Exception as e:
        raise Exception(f"RSA加密失败: {e}")


def encrypt_des(message: str, key: str) -> str:
    """DES ECB 加密"""
    key_bytes = key.encode()[:8].ljust(8, b"\0")
    message_bytes = str(message).encode()
    while len(message_bytes) % 8 != 0:
        message_bytes += b"\0"
    cipher = cast(Any, DES).new(key_bytes, DES.MODE_ECB)
    encrypted = cipher.encrypt(message_bytes)
    return base64.b64encode(encrypted).decode()


def gzip_compress_object(obj: Dict[str, Any]) -> str:
    """GZIP压缩对象"""
    json_str = json.dumps(obj, separators=(", ", ": "))
    compressed = gzip.compress(json_str.encode())
    compressed_bytes = bytearray(compressed)
    if len(compressed_bytes) > 9:
        compressed_bytes[9] = 19
    return base64.b64encode(compressed_bytes).decode()


def encrypt_aes(message: str, key: str) -> str:
    """AES CBC加密"""
    iv = b"0102030405060708"
    key_bytes = key.encode()[:16].ljust(16, b"\0")
    cipher = cast(Any, AES).new(key_bytes, AES.MODE_CBC, iv)
    padded_data = pad(message.encode(), AES.block_size)
    encrypted = cipher.encrypt(padded_data)
    return encrypted.hex()


def encrypt_object_by_des_rules(
    obj: Dict[str, Any], rules: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """根据DES规则加密对象"""
    result: Dict[str, Any] = {}

    for key, value in obj.items():
        if key in rules:
            rule = rules[key]
            if rule["is_encrypt"] == 1:
                encrypted_value = encrypt_des(str(value), rule["key"])
                result[rule["obfuscated_name"]] = encrypted_value
            else:
                result[rule["obfuscated_name"]] = value
        else:
            result[key] = value

    return result


async def get_device_id(proxy: str | None = None) -> str:
    """获取设备ID"""
    uid = str(uuid.uuid4())
    pri_id = md5_hash(uid)[:16]
    ep = encrypt_rsa(uid, SKLAND_SM_CONFIG["publicKey"])

    browser = BROWSER_ENV.copy()
    browser.update(
        {
            "vpw": str(uuid.uuid4()),
            "svm": int(time.time() * 1000),
            "trees": str(uuid.uuid4()),
            "pmf": int(time.time() * 1000),
        }
    )

    des_target = {
        **browser,
        "protocol": 102,
        "organization": SKLAND_SM_CONFIG["organization"],
        "appId": SKLAND_SM_CONFIG["appId"],
        "os": "web",
        "version": "3.0.0",
        "sdkver": "3.0.0",
        "box": "",
        "rtype": "all",
        "smid": get_sm_id(),
        "subVersion": "1.0.0",
        "time": 0,
    }
    des_target["tn"] = md5_hash(get_tn(des_target))

    des_result = encrypt_object_by_des_rules(des_target, DES_RULE)
    gzip_result = gzip_compress_object(des_result)
    aes_result = encrypt_aes(gzip_result, pri_id)

    body = {
        "appId": "default",
        "compress": 2,
        "data": aes_result,
        "encode": 5,
        "ep": ep,
        "organization": SKLAND_SM_CONFIG["organization"],
        "os": "web",
    }

    devices_info_url = f"{SKLAND_SM_CONFIG['protocol']}://{SKLAND_SM_CONFIG['apiHost']}{SKLAND_SM_CONFIG['apiPath']}"

    async with httpx.AsyncClient(proxy=get_proxy(proxy)) as client:
        response = await client.post(
            devices_info_url,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )
        resp = response.json()

    if resp.get("code") != 1100:
        raise Exception(f"设备ID计算失败: {resp}")

    return f"B{resp['detail']['deviceId']}"


_cached_device_id = None
_cache_time = datetime.now()


async def get_cached_device_id(proxy: str | None = None) -> str:
    """获取缓存的设备ID"""
    global _cached_device_id, _cache_time

    if _cached_device_id is None or (datetime.now() - _cache_time) > timedelta(hours=1):
        _cached_device_id = await get_device_id(proxy)
        _cache_time = datetime.now()

    return _cached_device_id


async def skland_sign_in(
    token: str,
    app_code: str = "arknights",
    proxy: str | None = None,
) -> dict[str, Any]:
    """森空岛签到"""

    grant_code_url = "https://as.hypergryph.com/user/oauth2/v2/grant"
    cred_code_url = "https://zonai.skland.com/web/v1/user/auth/generate_cred_by_code"
    binding_url = "https://zonai.skland.com/api/v1/game/player/binding"
    arknights_sign_url = "https://zonai.skland.com/api/v1/game/attendance"
    endfield_sign_url = "https://zonai.skland.com/web/v1/game/endfield/attendance"

    header = {
        "cred": "",
        "User-Agent": "Skland/1.21.0 (com.hypergryph.skland; build:102100065; iOS 17.6.0; ) Alamofire/5.7.1",
        "Accept-Encoding": "gzip",
        "Connection": "close",
        "Content-Type": "application/json",
    }
    header_login = header.copy()
    header_for_sign = {
        "platform": "1",
        "timestamp": "",
        "dId": "",
        "vName": "1.21.0",
    }

    def generate_signature(
        token_for_sign: str,
        path: str,
        body_or_query: str,
        custom_header: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str]]:
        """生成请求签名"""
        t = str(int(time.time() * 1000 - 2000))[:-3]
        token_bytes = token_for_sign.encode("utf-8")
        header_ca = dict(custom_header if custom_header else header_for_sign)
        header_ca["timestamp"] = t
        header_ca_str = json.dumps(header_ca, separators=(",", ":"))
        s = path + body_or_query + t + header_ca_str
        hex_s = hmac.new(token_bytes, s.encode("utf-8"), hashlib.sha256).hexdigest()
        md5_hash_value = hashlib.md5(hex_s.encode("utf-8")).hexdigest()
        return md5_hash_value, header_ca

    async def get_sign_header(
        url: str,
        method: str,
        body: dict[str, Any] | None,
        old_header: dict[str, str],
        sign_token: str,
    ) -> dict[str, str]:
        """获取带签名的请求头"""
        h = json.loads(json.dumps(old_header))
        p = parse.urlparse(url)

        device_id = await get_cached_device_id(proxy)
        temp_header_for_sign = dict(header_for_sign)
        temp_header_for_sign["dId"] = device_id

        if method.lower() == "get":
            query = p.query or ""
            sign, header_ca = generate_signature(
                sign_token, p.path, query, temp_header_for_sign
            )
        else:
            body_str = json.dumps(body) if body else ""
            sign, header_ca = generate_signature(
                sign_token, p.path, body_str, temp_header_for_sign
            )

        h["sign"] = sign
        for key, value in header_ca.items():
            h[key] = value

        if "token" in h:
            del h["token"]

        return h

    def copy_header(cred: str, token: str | None = None) -> dict[str, str]:
        """复制请求头并添加cred和token"""
        v = json.loads(json.dumps(header))
        v["cred"] = cred
        if token:
            v["token"] = token
        return v

    async def login_by_token(token_code: str) -> tuple[str, str]:
        """使用token一步步拿到cred和sign_token"""
        try:
            t = json.loads(token_code)
            token_code = t["data"]["content"]
        except Exception:
            pass
        grant_code = await get_grant_code(token_code)
        return await get_cred(grant_code)

    async def get_cred(grant: str) -> tuple[str, str]:
        """通过grant code获取cred和sign_token"""
        device_id = await get_cached_device_id(proxy)

        web_headers = {
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "referer": "https://www.skland.com/",
            "origin": "https://www.skland.com",
            "dId": device_id,
            "platform": "3",
            "timestamp": str(int(time.time())),
            "vName": "1.0.0",
        }

        async with httpx.AsyncClient(proxy=get_proxy(proxy)) as client:
            response = await client.post(
                cred_code_url,
                json={"code": grant, "kind": 1},
                headers=web_headers,
            )
            rsp = response.json()
        if rsp["code"] != 0:
            raise Exception(f"获得cred失败: {rsp.get('message')}")
        sign_token = rsp["data"]["token"]
        cred = rsp["data"]["cred"]
        return cred, sign_token

    async def get_grant_code(token_value: str) -> str:
        """通过token获取grant code"""
        async with httpx.AsyncClient(proxy=get_proxy(proxy)) as client:
            response = await client.post(
                grant_code_url,
                json={"appCode": "4ca99fa6b56cc2ba", "token": token_value, "type": 0},
                headers=header_login,
            )
            rsp = response.json()
        if rsp["status"] != 0:
            raise Exception(
                f"使用token: {token_value[:3]}******{token_value[-3:]} 获得认证代码失败: {rsp.get('msg')}"
            )
        return rsp["data"]["code"]

    async def get_binding_list(cred: str, sign_token: str) -> list[dict[str, Any]]:
        """查询已绑定的角色列表"""
        v: list[dict[str, Any]] = []
        async with httpx.AsyncClient(proxy=get_proxy(proxy)) as client:
            response = await client.get(
                binding_url,
                headers=await get_sign_header(
                    binding_url,
                    "get",
                    None,
                    copy_header(cred, sign_token),
                    sign_token,
                ),
            )
            rsp = response.json()
        if rsp["code"] != 0:
            logger.error(f"请求角色列表出现问题: {rsp['message']}")
            if rsp.get("message") == "用户未登录":
                logger.error("用户登录可能失效了, 请重新登录！")
                return v
        for item in rsp["data"]["list"]:
            if item.get("appCode") != app_code:
                continue
            v.extend(item.get("bindingList"))
        return v

    async def check_attendance_today(
        cred: str,
        sign_token: str,
        uid: str,
        game_id: str | int,
    ) -> bool:
        """检查今天是否已经签到"""
        query_url = f"{arknights_sign_url}?uid={uid}&gameId={game_id}"

        try:
            async with httpx.AsyncClient(proxy=get_proxy(proxy)) as client:
                response = await client.get(
                    query_url,
                    headers=await get_sign_header(
                        query_url,
                        "get",
                        None,
                        copy_header(cred, sign_token),
                        sign_token,
                    ),
                )
                rsp = response.json()

            if rsp["code"] != 0:
                logger.warning(f"检查签到状态失败: {rsp.get('message')}")
                return False

            records = rsp["data"].get("records", [])
            today = time.time() // 86400 * 86400

            for record in records:
                record_time = int(record.get("ts", 0))
                if record_time >= today:
                    return True

            return False
        except Exception as e:
            logger.warning(f"检查签到状态异常: {e}")
            return False

    async def sign_for_arknights(cred: str, sign_token: str) -> dict[str, Any]:
        """方舟签到"""
        characters = await get_binding_list(cred, sign_token)
        success_list: list[str] = []
        duplicate_list: list[str] = []
        failed_list: list[str] = []

        for character in characters:
            character_name = (
                f"{character.get('nickName')}（{character.get('channelName')}）"
            )
            uid = character.get("uid")
            game_id = character.get("channelMasterId")

            if not isinstance(uid, str) or not isinstance(game_id, (str, int)):
                failed_list.append(character_name)
                logger.error(f"{character_name} 缺少有效 uid 或 gameId，跳过签到")
                await asyncio.sleep(1)
                continue

            if await check_attendance_today(cred, sign_token, uid, game_id):
                duplicate_list.append(character_name)
                logger.info(f"{character_name} 今天已经签到过了")
                await asyncio.sleep(1)
                continue

            body = {
                "uid": uid,
                "gameId": game_id,
            }

            try:
                async with httpx.AsyncClient(proxy=get_proxy(proxy)) as client:
                    sign_headers = await get_sign_header(
                        arknights_sign_url,
                        "post",
                        body,
                        copy_header(cred, sign_token),
                        sign_token,
                    )
                    response = await client.post(
                        arknights_sign_url,
                        headers=sign_headers,
                        content=json.dumps(body),
                    )
                    rsp = response.json()

                if rsp["code"] != 0:
                    if rsp.get("message") == "请勿重复签到！":
                        duplicate_list.append(character_name)
                        logger.info(f"{character_name} 重复签到")
                    else:
                        failed_list.append(character_name)
                        logger.error(f"{character_name} 签到失败: {rsp.get('message')}")
                else:
                    success_list.append(character_name)
                    logger.info(f"{character_name} 签到成功")

            except Exception as e:
                failed_list.append(character_name)
                logger.error(f"{character_name} 签到异常: {e}")

            await asyncio.sleep(3)

        return {
            "成功": success_list,
            "重复": duplicate_list,
            "失败": failed_list,
            "总计": len(characters),
        }

    async def do_sign_for_endfield(
        cred: str, sign_token: str, role: dict[str, Any]
    ) -> dict[str, Any]:
        headers = await get_sign_header(
            endfield_sign_url,
            "post",
            None,
            copy_header(cred, sign_token),
            sign_token,
        )
        headers.update(
            {
                "Content-Type": "application/json",
                "sk-game-role": f'3_{role["roleId"]}_{role["serverId"]}',
                "referer": "https://game.skland.com/",
                "origin": "https://game.skland.com/",
            }
        )

        async with httpx.AsyncClient(proxy=get_proxy(proxy)) as client:
            response = await client.post(endfield_sign_url, headers=headers)
            return response.json()

    async def sign_for_endfield(cred: str, sign_token: str) -> dict[str, Any]:
        """终末地签到"""
        characters = await get_binding_list(cred, sign_token)
        success_list: list[str] = []
        duplicate_list: list[str] = []
        failed_list: list[str] = []
        total_count = 0

        for character in characters:
            roles = character.get("roles") or []
            game_name = character.get("gameName")
            channel_name = character.get("channelName")
            if not isinstance(roles, list):
                continue
            total_count += len(roles)

            for role in roles:
                nickname = str(role.get("nickname") or "").strip()
                character_name = f"{nickname}（{channel_name}）"

                try:
                    rsp = await do_sign_for_endfield(cred, sign_token, role)
                    if rsp.get("code") != 0:
                        message = rsp.get("message", "")
                        if (
                            "请勿重复签到" in message
                            or "Please do not sign in again!" in message
                        ):
                            duplicate_list.append(character_name)
                            logger.info(f"{character_name} 重复签到")
                        else:
                            failed_list.append(character_name)
                            logger.error(f"{character_name} 签到失败: {message}")
                    else:
                        award_ids = rsp.get("data", {}).get("awardIds", [])
                        resource_map = rsp.get("data", {}).get("resourceInfoMap", {})
                        awards = []
                        for award in award_ids:
                            award_id = award.get("id")
                            if award_id and award_id in resource_map:
                                resource = resource_map[award_id]
                                awards.append(
                                    f'{resource["name"]}x{resource.get("count", 1)}'
                                )
                        if awards:
                            logger.info(
                                f"[{game_name}] {character_name} 签到成功: {'、'.join(awards)}"
                            )
                        success_list.append(character_name)
                        logger.info(f"{character_name} 签到成功")
                except Exception as e:
                    failed_list.append(character_name)
                    logger.error(f"{character_name} 签到异常: {e}")

                await asyncio.sleep(3)

        return {
            "成功": success_list,
            "重复": duplicate_list,
            "失败": failed_list,
            "总计": total_count,
        }

    try:
        cred, sign_token = await login_by_token(token)
        await asyncio.sleep(1)
        if app_code == "endfield":
            return await sign_for_endfield(cred, sign_token)
        return await sign_for_arknights(cred, sign_token)
    except Exception as e:
        logger.error(f"森空岛签到失败: {e}")
        return {"成功": [], "重复": [], "失败": [], "总计": 0}
