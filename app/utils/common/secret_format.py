"""历史 DPAPI 密文的纯格式识别；不调用平台存储能力。"""

import base64

_DPAPI_BLOB_PREFIX = b"\x01\x00\x00\x00" + bytes.fromhex(
    "d08c9ddf0115d1118c7a00c04fc297eb"
)


def looks_like_dpapi_blob(value: object) -> bool:
    """按结构判断一个值是否为 DPAPI 密文，不关心本机能否解开。

    同一台机器上另一个 Windows 账户写的密文，本账户解不开，但它依然是密文，
    必须原样保留；只有真正的明文才需要加密。
    """

    if not isinstance(value, str) or not value:
        return False
    try:
        blob = base64.b64decode(value, validate=True)
    except ValueError:
        return False
    return blob.startswith(_DPAPI_BLOB_PREFIX)
