"""
森空岛设备ID生成器
基于 skland-daily-attendance 项目的实现
"""

import json
import time
import uuid
import hashlib
import gzip
import base64
from typing import Dict, Any
import httpx
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.Util.Padding import pad


# 数美科技配置
SKLAND_SM_CONFIG = {
    "organization": "UWXspnCCJN4sfYlNfqps",
    "appId": "default",
    "publicKey": "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCmxMNr7n8ZeT0tE1R9j/mPixoinPkeM+k4VGIn/s0k7N5rJAfnZ0eMER+QhwFvshzo0LNmeUkpR8uIlU/GEVr8mN28sKmwd2gpygqj0ePnBmOW4v0ZVwbSYK+izkhVFk2V/doLoMbWy6b+UnA8mkjvg0iYWRByfRsK2gdl7llqCwIDAQAB",
    "protocol": "https",
    "apiHost": "fp-it.portal101.cn",
    "apiPath": "/deviceprofile/v4",
}

# 浏览器环境模拟
BROWSER_ENV = {
    "plugins": "MicrosoftEdgePDFPluginPortableDocumentFormatinternal-pdf-viewer1,MicrosoftEdgePDFViewermhjfbmdgcfjbbpaeojofohoefgiehjai1",
    "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "canvas": "259ffe69",  # 基于浏览器的canvas获得的值
    "timezone": -480,  # 时区
    "platform": "Win32",
    "url": "https://www.skland.com/",  # 固定值
    "referer": "",
    "res": "1920_1080_24_1.25",  # 屏幕宽度_高度_色深_window.devicePixelRatio
    "clientSize": "0_0_1080_1920_1920_1080_1920_1080",
    "status": "0011",  # 不知道在干啥
}

# DES加密规则
DES_RULE = {
    "appId": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "uy7mzc4h",
        "obfuscated_name": "xx",
    },
    "box": {
        "is_encrypt": 0,
        "obfuscated_name": "jf",
    },
    "canvas": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "snrn887t",
        "obfuscated_name": "yk",
    },
    "clientSize": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "cpmjjgsu",
        "obfuscated_name": "zx",
    },
    "organization": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "78moqjfc",
        "obfuscated_name": "dp",
    },
    "os": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "je6vk6t4",
        "obfuscated_name": "pj",
    },
    "platform": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "pakxhcd2",
        "obfuscated_name": "gm",
    },
    "plugins": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "v51m3pzl",
        "obfuscated_name": "kq",
    },
    "pmf": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "2mdeslu3",
        "obfuscated_name": "vw",
    },
    "protocol": {
        "is_encrypt": 0,
        "obfuscated_name": "protocol",
    },
    "referer": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "y7bmrjlc",
        "obfuscated_name": "ab",
    },
    "res": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "whxqm2a7",
        "obfuscated_name": "hf",
    },
    "rtype": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "x8o2h2bl",
        "obfuscated_name": "lo",
    },
    "sdkver": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "9q3dcxp2",
        "obfuscated_name": "sc",
    },
    "status": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "2jbrxxw4",
        "obfuscated_name": "an",
    },
    "subVersion": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "eo3i2puh",
        "obfuscated_name": "ns",
    },
    "svm": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "fzj3kaeh",
        "obfuscated_name": "qr",
    },
    "time": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "q2t3odsk",
        "obfuscated_name": "nb",
    },
    "timezone": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "1uv05lj5",
        "obfuscated_name": "as",
    },
    "tn": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "x9nzj1bp",
        "obfuscated_name": "py",
    },
    "trees": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "acfs0xo4",
        "obfuscated_name": "pi",
    },
    "ua": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "k92crp1t",
        "obfuscated_name": "bj",
    },
    "url": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "y95hjkoo",
        "obfuscated_name": "cf",
    },
    "version": {
        "is_encrypt": 0,
        "obfuscated_name": "version",
    },
    "vpw": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "r9924ab5",
        "obfuscated_name": "ca",
    },
}


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
    from Crypto.Cipher import DES

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
_cache_time = 0
CACHE_DURATION = 3600  # 1小时


async def get_cached_device_id() -> str:
    """获取缓存的设备ID"""
    global _cached_device_id, _cache_time

    current_time = time.time()
    if _cached_device_id is None or (current_time - _cache_time) > CACHE_DURATION:
        _cached_device_id = await get_device_id()
        _cache_time = current_time

    return _cached_device_id
