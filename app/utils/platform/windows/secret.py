import base64

from app.utils.platform.common.errors import UnsupportedPlatformError
from app.utils.platform.common.secret import looks_like_dpapi_blob

__all__ = [
    "looks_like_dpapi_blob",
    "dpapi_encrypt",
    "dpapi_decrypt",
    "supports_secret_storage",
    "is_secret_storage_error",
]

_SECRET_STORAGE_PROBE = "AUTO-MAS secret storage probe"

# 默认的 DPAPI 作用域绑定当前 Windows 账户，同一台机器上的另一个账户解不开。
# 一份安装被多个本地账户共用时（配置目录只有一份），换账户启动就会读不出已存的
# 账号密码。改用机器作用域后同机各账户都能解密；解密侧不需要对应改动，作用域写在
# 密文里，CryptUnprotectData 与 .NET ProtectedData 都会忽略调用方传入的作用域，
# 因此既能读回旧的用户态密文，SRA 也能照常解开 MAS 写给它的密文。
CRYPTPROTECT_LOCAL_MACHINE = 0x4


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
        note.encode("utf-8"),
        description,
        entropy,
        None,
        None,
        CRYPTPROTECT_LOCAL_MACHINE,
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

    return (
        isinstance(error, UnsupportedPlatformError)
        and getattr(error, "capability", None) == "secret"
    )
