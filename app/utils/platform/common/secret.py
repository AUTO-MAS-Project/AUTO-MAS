import base64

from app.utils.platform.common.errors import UnsupportedPlatformError

__all__ = [
    "looks_like_dpapi_blob",
    "dpapi_encrypt",
    "dpapi_decrypt",
    "supports_secret_storage",
    "is_secret_storage_error",
]

# DPAPI 密文固定以 4 字节版本号加 16 字节 provider GUID 开头，
# 用户态与机器态密文的这 20 字节完全一致。
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


def supports_secret_storage() -> bool:
    """当前平台是否提供配置层所需的密文存储能力。"""

    return False


def is_secret_storage_error(error: BaseException) -> bool:
    """判断异常是否表示平台不支持密文存储。"""

    return (
        isinstance(error, UnsupportedPlatformError)
        and getattr(error, "capability", None) == "secret"
    )


def dpapi_encrypt(note: str, *args, **kwargs) -> str:
    if note == "":
        return ""
    raise UnsupportedPlatformError("secret")


def dpapi_decrypt(note: str, *args, **kwargs) -> str:
    if note == "":
        return ""
    raise UnsupportedPlatformError("secret")
