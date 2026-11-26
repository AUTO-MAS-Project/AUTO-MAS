"""仅桌面分身使用的当前 Windows 用户凭据。"""

import base64
import ctypes as C
import json
from ctypes import wintypes as W
from dataclasses import dataclass, field
from pathlib import Path

from app.utils.common.io import atomic_write

from .native import SYSTEM32, bind, handle_scope


class CredentialError(RuntimeError):
    def __init__(self, code: str, *, native_code: int | None = None) -> None:
        self.code = code
        self.native_code = native_code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Credential:
    account: str
    password: str = field(repr=False)

    @property
    def rdp_identity(self) -> tuple[str, str]:
        domain, separator, user = self.account.partition("\\")
        return (domain, user) if separator else ("", domain)


def validate(credential: Credential) -> None:
    """校验本机登录密码，并确认账户与本进程的 Windows 用户一致。"""
    import win32api
    import win32con
    import win32security
    from pywintypes import error

    domain, user = credential.rdp_identity
    if (
        not user
        or not credential.password
        or any(
            "\0" in value or len(value) > 512
            for value in (domain, user, credential.password)
        )
    ):
        raise CredentialError("password_invalid")
    try:
        with (
            handle_scope(
                win32security.LogonUser(
                    user,
                    domain or None,
                    credential.password,
                    win32con.LOGON32_LOGON_INTERACTIVE,
                    win32con.LOGON32_PROVIDER_DEFAULT,
                )
            ) as token,
            handle_scope(
                win32security.OpenProcessToken(
                    win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
                )
            ) as current,
        ):
            if _sid(token) != _sid(current):
                raise CredentialError("account_mismatch")
    except error as exc:
        # 限制向 IPC 传递的值，异常文本可能含账户信息。
        code = "account_locked" if exc.winerror == 1909 else "password_invalid"
        raise CredentialError(code, native_code=exc.winerror) from None


def _sid(token) -> str:
    import win32security

    sid, _ = win32security.GetTokenInformation(token, win32security.TokenUser)
    return win32security.ConvertSidToStringSid(sid)


def current_identity() -> tuple[str, str]:
    import win32api
    import win32con
    import win32security

    with handle_scope(
        win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
    ) as token:
        sid = _sid(token)
    return win32api.GetUserNameEx(2), sid


def protect(data: bytearray, *, decrypt: bool = False) -> bytes | bytearray:
    """通过 CNG DPAPI 的 LOCAL=user 描述符处理一个分身凭据。"""
    ncrypt = C.WinDLL("ncrypt", winmode=SYSTEM32)
    kernel = C.WinDLL("kernel32", winmode=SYSTEM32)
    descriptor = W.HANDLE()
    output = C.c_void_p()
    length = W.ULONG()
    source = (C.c_ubyte * len(data)).from_buffer(data)
    code = 0
    try:
        if decrypt:
            unprotect = bind(
                ncrypt,
                "NCryptUnprotectSecret",
                W.LONG,
                C.POINTER(W.HANDLE),
                W.DWORD,
                C.c_void_p,
                W.ULONG,
                C.c_void_p,
                W.HWND,
                C.POINTER(C.c_void_p),
                C.POINTER(W.ULONG),
            )
            code = unprotect(
                None,
                0x40,
                source,
                len(data),
                None,
                None,
                C.byref(output),
                C.byref(length),
            )
        else:
            create = bind(
                ncrypt,
                "NCryptCreateProtectionDescriptor",
                W.LONG,
                W.LPCWSTR,
                W.DWORD,
                C.POINTER(W.HANDLE),
            )
            code = create("LOCAL=user", 0, C.byref(descriptor))
            if code == 0:
                encrypt = bind(
                    ncrypt,
                    "NCryptProtectSecret",
                    W.LONG,
                    W.HANDLE,
                    W.DWORD,
                    C.c_void_p,
                    W.ULONG,
                    C.c_void_p,
                    W.HWND,
                    C.POINTER(C.c_void_p),
                    C.POINTER(W.ULONG),
                )
                code = encrypt(
                    descriptor,
                    0x40,
                    source,
                    len(data),
                    None,
                    None,
                    C.byref(output),
                    C.byref(length),
                )
        if code or not output or not length.value:
            raise CredentialError(
                "credential_unreadable" if decrypt else "credential_save_failed",
                native_code=code,
            )
        if not decrypt:
            return C.string_at(output, length.value)
        clear = bytearray(length.value)
        C.memmove((C.c_ubyte * len(clear)).from_buffer(clear), output, len(clear))
        return clear
    finally:
        if output:
            if decrypt:
                C.memset(output, 0, length.value)
            bind(kernel, "LocalFree", W.HANDLE, W.HANDLE)(output)
        if descriptor:
            bind(ncrypt, "NCryptCloseProtectionDescriptor", W.LONG, W.HANDLE)(
                descriptor
            )


def load(path: Path, account: str) -> Credential | None:
    try:
        with path.open("rb") as stream:
            payload = json.loads(stream.read(65537))
        encoded = payload[account]
        encrypted = bytearray(base64.b64decode(encoded, validate=True))
        if not 0 < len(encrypted) <= 65536:
            raise ValueError
        clear = protect(encrypted, decrypt=True)
        try:
            return Credential(account, clear.decode("utf-8"))
        finally:
            clear[:] = b"\0" * len(clear)
    except (FileNotFoundError, KeyError):
        return None
    except (OSError, TypeError, ValueError):
        raise CredentialError("credential_unreadable") from None


def encode(credential: Credential) -> str:
    clear = bytearray(credential.password, "utf-8")
    try:
        return base64.b64encode(protect(clear)).decode("ascii")
    finally:
        clear[:] = b"\0" * len(clear)


def save(path: Path, account: str, encoded: str) -> None:
    try:
        atomic_write(path, json.dumps({account: encoded}).encode("utf-8"))
    except OSError:
        raise CredentialError("credential_save_failed") from None
