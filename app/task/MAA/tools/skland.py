#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
#   Copyright © 2025 AUTO-MAS Team

#   This file incorporates work covered by the following copyright and
#   permission notice:
#
#       skland-checkin-ghaction Copyright © 2023 Yanstory
#       https://github.com/Yanstory/skland-checkin-ghaction

#       skland-daily-attendance Copyright © 2023-2025 enpitsuLin
#       https://github.com/enpitsuLin/skland-daily-attendance

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
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

from typing import Dict, Any

from app.core import Config
from app.utils.constants import SKLAND_SM_CONFIG, BROWSER_ENV, DES_RULE
from app.utils.logger import get_logger

logger = get_logger("森空岛签到任务")


def md5_hash(data: str) -> str:
    """MD5哈希"""
    return hashlib.md5(data.encode()).hexdigest()


def get_sm_id() -> str:
    """生成数美ID"""
    now = time.localtime()
    _time = time.strftime("%Y%m%d%H%M%S", now)

    # 生成UUID
    uid = str(uuid.uuid4())

    # MD5加密uid
    uid_md5 = md5_hash(uid)

    v = f"{_time}{uid_md5}00"

    # 计算smsk_web
    smsk_web = md5_hash(f"smsk_web_{v}")[:14]

    return f"{v}{smsk_web}0"


def get_tn(obj: Dict[str, Any]) -> str:
    """计算tn值"""
    # 获取并排序对象的所有键
    sorted_keys = sorted(obj.keys())

    # 用于存储处理后的值
    result_list = []

    # 遍历排序后的键
    for key in sorted_keys:
        v = obj[key]

        # 处理数字类型
        if isinstance(v, (int, float)):
            v = str(int(v * 10000))
        # 处理对象类型（递归）
        elif isinstance(v, dict):
            v = get_tn(v)
        else:
            v = str(v)

        result_list.append(v)

    # 将所有结果连接成字符串
    return "".join(result_list)


def encrypt_rsa(message: str, public_key_str: str) -> str:
    """RSA加密"""
    try:
        # 将base64编码的公钥转换为PEM格式
        # 添加换行符以符合PEM格式
        formatted_key = "\n".join(
            [public_key_str[i : i + 64] for i in range(0, len(public_key_str), 64)]
        )
        public_key_pem = (
            f"-----BEGIN PUBLIC KEY-----\n{formatted_key}\n-----END PUBLIC KEY-----"
        )

        # 导入公钥
        key = RSA.import_key(public_key_pem)
        cipher = PKCS1_v1_5.new(key)

        # 加密
        encrypted = cipher.encrypt(message.encode())

        # 返回base64编码的结果
        return base64.b64encode(encrypted).decode()
    except Exception as e:
        raise Exception(f"RSA加密失败: {e}")


def encrypt_des(message: str, key: str) -> str:
    """DES ECB 加密"""

    # 确保密钥长度为8字节
    key_bytes = key.encode()[:8].ljust(8, b"\0")

    # 确保消息长度为8的倍数（DES块大小）
    message_bytes = str(message).encode()
    # 使用null字节填充
    while len(message_bytes) % 8 != 0:
        message_bytes += b"\0"

    # DES ECB 加密
    cipher = DES.new(key_bytes, DES.MODE_ECB)
    encrypted = cipher.encrypt(message_bytes)

    # 返回base64编码的结果
    return base64.b64encode(encrypted).decode()


def gzip_compress_object(obj: Dict[str, Any]) -> str:
    """GZIP压缩对象"""
    # 转换为JSON字符串，添加空格以匹配JavaScript的格式
    json_str = json.dumps(obj, separators=(", ", ": "))

    # GZIP压缩
    compressed = gzip.compress(json_str.encode())

    # 设置Python gzip OS FLG为Unknown
    compressed_bytes = bytearray(compressed)
    if len(compressed_bytes) > 9:
        compressed_bytes[9] = 19  # Python gzip OS FLG = Unknown

    # 转换为base64
    return base64.b64encode(compressed_bytes).decode()


def encrypt_aes(message: str, key: str) -> str:
    """AES CBC加密"""
    iv = b"0102030405060708"  # 固定IV

    # 确保密钥长度为16字节
    key_bytes = key.encode()[:16].ljust(16, b"\0")

    # 加密
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    padded_data = pad(message.encode(), AES.block_size)
    encrypted = cipher.encrypt(padded_data)

    # 转换为十六进制字符串
    return encrypted.hex()


def encrypt_object_by_des_rules(
    obj: Dict[str, Any], rules: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """根据DES规则加密对象"""
    result = {}

    for key, value in obj.items():
        if key in rules:
            rule = rules[key]
            if rule["is_encrypt"] == 1:
                # 需要加密
                encrypted_value = encrypt_des(str(value), rule["key"])
                result[rule["obfuscated_name"]] = encrypted_value
            else:
                # 不加密，直接使用混淆名称
                result[rule["obfuscated_name"]] = value
        else:
            result[key] = value

    return result


async def get_device_id() -> str:
    """获取设备ID"""
    # 生成 UUID 并计算 priId
    uid = str(uuid.uuid4())
    pri_id = md5_hash(uid)[:16]

    # RSA加密
    ep = encrypt_rsa(uid, SKLAND_SM_CONFIG["publicKey"])

    # 准备浏览器环境数据
    browser = BROWSER_ENV.copy()
    browser.update(
        {
            "vpw": str(uuid.uuid4()),
            "svm": int(time.time() * 1000),
            "trees": str(uuid.uuid4()),
            "pmf": int(time.time() * 1000),
        }
    )

    # 准备加密目标数据
    des_target = {
        **browser,
        "protocol": 102,
        "organization": SKLAND_SM_CONFIG["organization"],
        "appId": SKLAND_SM_CONFIG["appId"],
        "os": "web",
        "version": "3.0.0",
        "sdkver": "3.0.0",
        "box": "",  # 首次请求为空
        "rtype": "all",
        "smid": get_sm_id(),
        "subVersion": "1.0.0",
        "time": 0,
    }

    # 计算并添加 tn
    des_target["tn"] = md5_hash(get_tn(des_target))

    # DES 加密（这里实际上是重命名）
    des_result = encrypt_object_by_des_rules(des_target, DES_RULE)

    # GZIP 压缩
    gzip_result = gzip_compress_object(des_result)

    # AES 加密
    aes_result = encrypt_aes(gzip_result, pri_id)

    # 准备请求体
    body = {
        "appId": "default",
        "compress": 2,
        "data": aes_result,
        "encode": 5,
        "ep": ep,
        "organization": SKLAND_SM_CONFIG["organization"],
        "os": "web",
    }

    # 发送请求
    devices_info_url = f"{SKLAND_SM_CONFIG['protocol']}://{SKLAND_SM_CONFIG['apiHost']}{SKLAND_SM_CONFIG['apiPath']}"

    async with httpx.AsyncClient() as client:
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


# 缓存设备ID以避免频繁计算
_cached_device_id = None
_cache_time = datetime.now()


async def get_cached_device_id() -> str:
    """获取缓存的设备ID"""
    global _cached_device_id, _cache_time

    current_time = time.time()
    if _cached_device_id is None or (datetime.now() - _cache_time) > timedelta(hours=1):
        _cached_device_id = await get_device_id()
        _cache_time = datetime.now()

    return _cached_device_id


async def skland_sign_in(token) -> dict:
    """森空岛签到"""

    app_code = "4ca99fa6b56cc2ba"
    # 用于获取grant code
    grant_code_url = "https://as.hypergryph.com/user/oauth2/v2/grant"
    # 用于获取cred - 更新为新的Web端点
    cred_code_url = "https://zonai.skland.com/web/v1/user/auth/generate_cred_by_code"
    # 查询角色绑定
    binding_url = "https://zonai.skland.com/api/v1/game/player/binding"
    # 签到接口
    sign_url = "https://zonai.skland.com/api/v1/game/attendance"

    # 基础请求头
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
        token_for_sign: str, path, body_or_query, custom_header=None
    ):
        """
        生成请求签名

        :param token_for_sign: 用于加密的token
        :param path: 请求路径（如 /api/v1/game/player/binding）
        :param body_or_query: GET用query字符串, POST用body字符串
        :param custom_header: 自定义签名头部（可选）
        :return: (sign, 新的header_for_sign字典)
        """

        # 时间戳减去2秒以防服务器时间不一致，按照JS的实现方式
        # (Date.now() - 2 * MILLISECOND_PER_SECOND).toString().slice(0, -3)
        t = str(int(time.time() * 1000 - 2000))[:-3]  # 去掉毫秒部分
        token_bytes = token_for_sign.encode("utf-8")

        # 使用自定义头部或默认头部
        header_ca = dict(custom_header if custom_header else header_for_sign)
        header_ca["timestamp"] = t
        header_ca_str = json.dumps(header_ca, separators=(",", ":"))

        # 按照新的规范拼接字符串
        s = path + body_or_query + t + header_ca_str

        # HMAC-SHA256 + MD5得到最终sign
        hex_s = hmac.new(token_bytes, s.encode("utf-8"), hashlib.sha256).hexdigest()
        md5_hash = hashlib.md5(hex_s.encode("utf-8")).hexdigest()
        return md5_hash, header_ca

    async def get_sign_header(url: str, method, body, old_header, sign_token):
        """
        获取带签名的请求头

        :param url: 请求完整url
        :param method: 请求方式 GET/POST
        :param body: POST请求体或GET时为None
        :param old_header: 原始请求头
        :param sign_token: 当前会话的签名token
        :return: 新请求头
        """

        h = json.loads(json.dumps(old_header))
        p = parse.urlparse(url)

        # 获取设备ID并创建临时签名头
        device_id = await get_cached_device_id()
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

        # 添加签名和其他头部
        h["sign"] = sign
        for key, value in header_ca.items():
            h[key] = value

        # 重要：删除token头部，这是新API的要求
        if "token" in h:
            del h["token"]

        return h

    def copy_header(cred, token=None):
        """
        复制请求头并添加cred和token

        :param cred: 当前会话的cred
        :param token: 当前会话的token（用于签名）
        :return: 新的请求头
        """
        v = json.loads(json.dumps(header))
        v["cred"] = cred
        if token:
            v["token"] = token
        return v

    async def login_by_token(token_code):
        """
        使用token一步步拿到cred和sign_token

        :param token_code: 你的skyland token
        :return: (cred, sign_token)
        """
        try:
            # token为json对象时提取data.content
            t = json.loads(token_code)
            token_code = t["data"]["content"]
        except:
            pass
        grant_code = await get_grant_code(token_code)
        return await get_cred(grant_code)

    async def get_cred(grant):
        """
        通过grant code获取cred和sign_token

        :param grant: grant code
        :return: (cred, sign_token)
        """

        # 获取设备ID
        device_id = await get_cached_device_id()

        # Web端点需要特殊的请求头
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

        async with httpx.AsyncClient(proxy=Config.get_proxy()) as client:
            response = await client.post(
                cred_code_url, json={"code": grant, "kind": 1}, headers=web_headers
            )
            rsp = response.json()
        if rsp["code"] != 0:
            raise Exception(f"获得cred失败: {rsp.get('message')}")
        sign_token = rsp["data"]["token"]
        cred = rsp["data"]["cred"]
        return cred, sign_token

    async def get_grant_code(token):
        """
        通过token获取grant code

        :param token: 你的skyland token
        :return: grant code
        """
        async with httpx.AsyncClient(proxy=Config.get_proxy()) as client:
            response = await client.post(
                grant_code_url,
                json={"appCode": app_code, "token": token, "type": 0},
                headers=header_login,
            )
            rsp = response.json()
        if rsp["status"] != 0:
            raise Exception(
                f"使用token: {token[:3]}******{token[-3:]} 获得认证代码失败: {rsp.get('msg')}"
            )
        return rsp["data"]["code"]

    async def get_binding_list(cred, sign_token):
        """
        查询已绑定的角色列表

        :param cred: 当前cred
        :param sign_token: 当前sign_token
        :return: 角色列表
        """
        v = []
        async with httpx.AsyncClient(proxy=Config.get_proxy()) as client:
            response = await client.get(
                binding_url,
                headers=await get_sign_header(
                    binding_url, "get", None, copy_header(cred, sign_token), sign_token
                ),
            )
            rsp = response.json()
        if rsp["code"] != 0:
            logger.error(f"请求角色列表出现问题: {rsp['message']}")
            if rsp.get("message") == "用户未登录":
                logger.error(f"用户登录可能失效了, 请重新登录！")
                return v
        # 只取明日方舟（arknights）的绑定账号
        for i in rsp["data"]["list"]:
            if i.get("appCode") != "arknights":
                continue
            v.extend(i.get("bindingList"))
        return v

    async def check_attendance_today(cred, sign_token, uid, game_id) -> bool:
        """
        检查今天是否已经签到

        :param cred: 当前cred
        :param sign_token: 当前sign_token
        :param uid: 角色uid
        :param game_id: 游戏ID
        :return: True表示今天已签到，False表示未签到
        """
        query_params = {"uid": uid, "gameId": game_id}
        query_url = f"{sign_url}?uid={uid}&gameId={game_id}"

        try:
            async with httpx.AsyncClient(proxy=Config.get_proxy()) as client:
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

            # 检查今天是否已经签到
            records = rsp["data"].get("records", [])
            today = time.time() // 86400 * 86400  # 今天0点的时间戳

            for record in records:
                record_time = int(record.get("ts", 0))
                if record_time >= today:
                    return True

            return False
        except Exception as e:
            logger.warning(f"检查签到状态异常: {e}")
            return False

    async def do_sign(cred, sign_token) -> dict:
        """
        对所有绑定的角色进行签到

        :param cred: 当前cred
        :param sign_token: 当前sign_token
        :return: 签到结果字典
        """

        characters = await get_binding_list(cred, sign_token)
        result = {"成功": [], "重复": [], "失败": [], "总计": len(characters)}

        for character in characters:
            character_name = (
                f"{character.get('nickName')}（{character.get('channelName')}）"
            )
            uid = character.get("uid")
            game_id = character.get("channelMasterId")

            # 先检查今天是否已经签到
            if await check_attendance_today(cred, sign_token, uid, game_id):
                result["重复"].append(character_name)
                logger.info(f"{character_name} 今天已经签到过了")
                await asyncio.sleep(1)
                continue

            body = {
                "uid": uid,
                "gameId": game_id,
            }

            try:
                async with httpx.AsyncClient(proxy=Config.get_proxy()) as client:
                    sign_headers = await get_sign_header(
                        sign_url,
                        "post",
                        body,
                        copy_header(cred, sign_token),
                        sign_token,
                    )
                    response = await client.post(
                        sign_url,
                        headers=sign_headers,
                        content=json.dumps(body),  # 使用content而不是json参数避免冲突
                    )
                    rsp = response.json()

                if rsp["code"] != 0:
                    if rsp.get("message") == "请勿重复签到！":
                        result["重复"].append(character_name)
                        logger.info(f"{character_name} 重复签到")
                    else:
                        result["失败"].append(character_name)
                        logger.error(f"{character_name} 签到失败: {rsp.get('message')}")
                else:
                    result["成功"].append(character_name)
                    logger.info(f"{character_name} 签到成功")

            except Exception as e:
                result["失败"].append(character_name)
                logger.error(f"{character_name} 签到异常: {e}")

            await asyncio.sleep(3)

        return result

    # 主流程
    try:
        # 拿到cred和sign_token
        cred, sign_token = await login_by_token(token)
        await asyncio.sleep(1)
        # 依次签到
        return await do_sign(cred, sign_token)
    except Exception as e:
        logger.exception(f"森空岛签到失败: {e}")
        return {"成功": [], "重复": [], "失败": [], "总计": 0}
