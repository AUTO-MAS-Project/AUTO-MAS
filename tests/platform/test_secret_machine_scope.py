"""配置层密文的作用域与结构判别。

一份安装的 `config/` 只有一份，但同一台机器上可能有多个 Windows 账户轮流启动它。
DPAPI 默认把密钥绑到当前账户，换账户就解不开已存的账号密码，因此加密固定走机器
作用域；解密侧不需要对应改动，作用域写在密文里。

`looks_like_dpapi_blob` 是配置层区分「已加密的存量密文」与「用户新填的明文」的唯一
依据，必须只看结构、不看本机能否解开。
"""

from __future__ import annotations

import base64

import pytest

from app.utils.platform import IS_WINDOWS
from app.utils.platform.common.secret import looks_like_dpapi_blob

# 真实 DPAPI 密文固定的开头：4 字节版本号 + 16 字节 provider GUID。
# 用户作用域与机器作用域的这 20 字节完全一致。
_REAL_BLOB_HEADER = bytes.fromhex("01000000") + bytes.fromhex(
    "d08c9ddf0115d1118c7a00c04fc297eb"
)


def _blob(payload: bytes = b"\x00" * 64) -> str:
    return base64.b64encode(_REAL_BLOB_HEADER + payload).decode("utf-8")


def test_real_blob_header_is_recognized() -> None:
    assert looks_like_dpapi_blob(_blob()) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "my-plain-password",
        "不是 base64 的中文明文",
        # 合法 base64，但开头不是 DPAPI 的 provider GUID
        base64.b64encode(b"\x01\x00\x00\x00" + b"\xab" * 32).decode("utf-8"),
        # 长度不足以容纳 20 字节头部
        base64.b64encode(b"\x01\x00\x00\x00").decode("utf-8"),
    ],
)
def test_non_ciphertext_values_are_treated_as_plaintext(value: str) -> None:
    assert looks_like_dpapi_blob(value) is False


@pytest.mark.parametrize("value", [None, 123, b"bytes", ["list"]])
def test_non_string_values_are_rejected(value: object) -> None:
    assert looks_like_dpapi_blob(value) is False


@pytest.mark.skipif(not IS_WINDOWS, reason="仅 Windows 走 DPAPI 实现")
def test_encrypt_uses_machine_scope() -> None:
    """加密必须带机器作用域标志，否则换个 Windows 账户就读不出密码。"""

    from app.utils.platform.windows import secret as windows_secret

    captured: dict[str, object] = {}

    class _FakeWin32Crypt:
        @staticmethod
        def CryptProtectData(data, description, entropy, reserved, prompt, flags):
            captured["flags"] = flags
            return b"blob"

    original = windows_secret._win32crypt
    windows_secret._win32crypt = lambda: _FakeWin32Crypt()
    try:
        windows_secret.dpapi_encrypt("secret")
    finally:
        windows_secret._win32crypt = original

    assert captured["flags"] == windows_secret.CRYPTPROTECT_LOCAL_MACHINE


@pytest.mark.skipif(not IS_WINDOWS, reason="仅 Windows 走 DPAPI 实现")
def test_machine_scope_ciphertext_round_trips() -> None:
    from app.utils.platform.windows.secret import dpapi_decrypt, dpapi_encrypt

    ciphertext = dpapi_encrypt("账号密码 with ascii")

    assert looks_like_dpapi_blob(ciphertext) is True
    assert dpapi_decrypt(ciphertext) == "账号密码 with ascii"


@pytest.mark.skipif(not IS_WINDOWS, reason="仅 Windows 走 DPAPI 实现")
def test_legacy_user_scope_ciphertext_still_decrypts() -> None:
    """改用机器作用域后，此前写下的用户作用域密文必须照常读回。"""

    import win32crypt

    from app.utils.platform.windows.secret import dpapi_decrypt

    legacy_blob = win32crypt.CryptProtectData(
        "legacy-password".encode("utf-8"), None, None, None, None, 0
    )
    legacy = base64.b64encode(legacy_blob).decode("utf-8")

    assert looks_like_dpapi_blob(legacy) is True
    assert dpapi_decrypt(legacy) == "legacy-password"
