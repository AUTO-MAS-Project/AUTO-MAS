import base64

from app.utils.platform.common.errors import UnsupportedPlatformError

_SECRET_STORAGE_PROBE = "AUTO-MAS secret storage probe"


def _win32crypt():
    # pywin32 只装在宿主进程的环境里；MaaFW 内置 runner worker 跑在运行池的隔离
    # venv 中，那里没有它。顶层 import 会让 worker 一 import 本仓的 app.utils
    # 就崩，所以推迟到真正加解密时再 import。
    import win32crypt

    return win32crypt


def dpapi_encrypt(
    note: str, description: None | str = None, entropy: None | bytes = None
) -> str:
    """使用Windows DPAPI加密数据"""

    if note == "":
        return ""

    encrypted = _win32crypt().CryptProtectData(
        note.encode("utf-8"), description, entropy, None, None, 0
    )
    return base64.b64encode(encrypted).decode("utf-8")


def dpapi_decrypt(note: str, entropy: None | bytes = None) -> str:
    """使用Windows DPAPI解密数据"""

    if note == "":
        return ""

    decrypted = _win32crypt().CryptUnprotectData(
        base64.b64decode(note), entropy, None, None, 0
    )
    return decrypted[1].decode("utf-8")


def supports_secret_storage() -> bool:
    """检测 Windows DPAPI 是否可供当前进程使用。"""

    try:
        encrypted = dpapi_encrypt(_SECRET_STORAGE_PROBE)
        return bool(encrypted and dpapi_decrypt(encrypted) == _SECRET_STORAGE_PROBE)
    except Exception:
        return False


def is_secret_storage_error(error: BaseException) -> bool:
    """判断异常是否表示平台不支持密文存储。"""

    return isinstance(error, UnsupportedPlatformError) and getattr(
        error, "capability", None
    ) == "secret"
