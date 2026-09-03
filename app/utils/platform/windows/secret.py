import base64


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
