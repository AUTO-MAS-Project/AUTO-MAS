#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA

#   This file incorporates work covered by the following copyright and
#   permission notice:
#
#       skland-checkin-ghaction Copyright © 2023 Yanstory
#       https://github.com/Yanstory/skland-checkin-ghaction

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import time
import json
import hmac
import asyncio
import hashlib
import requests
from urllib import parse

from app.core import Config
from app.utils.logger import get_logger

logger = get_logger("森空岛签到任务")


async def skland_sign_in(token) -> dict:
    """森空岛签到"""

    app_code = "4ca99fa6b56cc2ba"
    # 用于获取grant code
    grant_code_url = "https://as.hypergryph.com/user/oauth2/v2/grant"
    # 用于获取cred
    cred_code_url = "https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code"
    # 查询角色绑定
    binding_url = "https://zonai.skland.com/api/v1/game/player/binding"
    # 签到接口
    sign_url = "https://zonai.skland.com/api/v1/game/attendance"

    # 基础请求头
    header = {
        "cred": "",
        "User-Agent": "Skland/1.5.1 (com.hypergryph.skland; build:100501001; Android 34;) Okhttp/4.11.0",
        "Accept-Encoding": "gzip",
        "Connection": "close",
    }
    header_login = header.copy()
    header_for_sign = {
        "platform": "1",
        "timestamp": "",
        "dId": "",
        "vName": "1.5.1",
    }

    def generate_signature(token_for_sign: str, path, body_or_query):
        """
        生成请求签名

        :param token_for_sign: 用于加密的token
        :param path: 请求路径（如 /api/v1/game/player/binding）
        :param body_or_query: GET用query字符串, POST用body字符串
        :return: (sign, 新的header_for_sign字典)
        """

        t = str(int(time.time()) - 2)  # 时间戳, -2秒以防服务器时间不一致
        token_bytes = token_for_sign.encode("utf-8")
        header_ca = dict(header_for_sign)
        header_ca["timestamp"] = t
        header_ca_str = json.dumps(header_ca, separators=(",", ":"))
        s = path + body_or_query + t + header_ca_str  # 拼接原始字符串
        # HMAC-SHA256 + MD5得到最终sign
        hex_s = hmac.new(token_bytes, s.encode("utf-8"), hashlib.sha256).hexdigest()
        md5 = hashlib.md5(hex_s.encode("utf-8")).hexdigest()
        return md5, header_ca

    def get_sign_header(url: str, method, body, old_header, sign_token):
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
        if method.lower() == "get":
            sign, header_ca = generate_signature(sign_token, p.path, p.query)
        else:
            sign, header_ca = generate_signature(
                sign_token, p.path, json.dumps(body) if body else ""
            )
        h["sign"] = sign
        for i in header_ca:
            h[i] = header_ca[i]
        return h

    def copy_header(cred):
        """
        复制请求头并添加cred

        :param cred: 当前会话的cred
        :return: 新的请求头
        """
        v = json.loads(json.dumps(header))
        v["cred"] = cred
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

        rsp = requests.post(
            cred_code_url,
            json={"code": grant, "kind": 1},
            headers=header_login,
            proxies=Config.get_proxies(),
        ).json()
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
        rsp = requests.post(
            grant_code_url,
            json={"appCode": app_code, "token": token, "type": 0},
            headers=header_login,
            proxies=Config.get_proxies(),
        ).json()
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
        rsp = requests.get(
            binding_url,
            headers=get_sign_header(
                binding_url, "get", None, copy_header(cred), sign_token
            ),
            proxies=Config.get_proxies(),
        ).json()
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

            body = {
                "uid": character.get("uid"),
                "gameId": character.get("channelMasterId"),
            }
            rsp = requests.post(
                sign_url,
                headers=get_sign_header(
                    sign_url, "post", body, copy_header(cred), sign_token
                ),
                json=body,
                proxies=Config.get_proxies(),
            ).json()

            if rsp["code"] != 0:

                result[
                    "重复" if rsp.get("message") == "请勿重复签到！" else "失败"
                ].append(
                    f"{character.get("nickName")}（{character.get("channelName")}）"
                )

            else:

                result["成功"].append(
                    f"{character.get("nickName")}（{character.get("channelName")}）"
                )

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
