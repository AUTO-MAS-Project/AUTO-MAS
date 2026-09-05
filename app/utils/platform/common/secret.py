from app.utils.platform.common.errors import UnsupportedPlatformError


def supports_secret_storage() -> bool:
    """当前平台是否提供配置层所需的密文存储能力。"""

    return False


def is_secret_storage_error(error: BaseException) -> bool:
    """判断异常是否表示平台不支持密文存储。"""

    return isinstance(error, UnsupportedPlatformError) and getattr(
        error, "capability", None
    ) == "secret"


def dpapi_encrypt(note: str, *args, **kwargs) -> str:
    if note == "":
        return ""
    raise UnsupportedPlatformError("secret")


def dpapi_decrypt(note: str, *args, **kwargs) -> str:
    if note == "":
        return ""
    raise UnsupportedPlatformError("secret")
