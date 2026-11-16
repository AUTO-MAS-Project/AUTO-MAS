"""更改加密作用域后，当前用户仍能读取以前保存的 DPAPI 密文。"""

from __future__ import annotations

import base64

import pytest

from app.utils import IS_WINDOWS
from app.utils import secret as _utils_secret


@pytest.mark.skipif(not IS_WINDOWS, reason="仅 Windows 走 DPAPI 实现")
def test_legacy_user_scope_ciphertext_still_decrypts() -> None:
    """改用机器作用域后，此前写下的用户作用域密文必须照常读回。"""

    import win32crypt

    from app.utils.windows.secret import dpapi_decrypt

    legacy_blob = win32crypt.CryptProtectData(
        "legacy-password".encode("utf-8"), None, None, None, None, 0
    )
    legacy = base64.b64encode(legacy_blob).decode("utf-8")

    assert _utils_secret.looks_like_dpapi_blob(legacy) is True
    assert dpapi_decrypt(legacy) == "legacy-password"
