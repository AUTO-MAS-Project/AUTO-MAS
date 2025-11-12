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
import hmac
import asyncio
import hashlib
import httpx
from urllib import parse

from app.core import Config
from app.utils.logger import get_logger
from app.utils.device_id import get_cached_device_id

logger = get_logger("森空岛签到任务")


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
