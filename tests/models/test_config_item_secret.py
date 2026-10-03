"""`EncryptValidator` 配置项对存量密文的处理口径。

一份安装的 `config/` 只有一份，同一台机器上换个 Windows 账户启动，读到的就是本账户
解不开的密文。这类值必须原样保留：它既不是明文，也不是坏数据，只是钥匙不在手上。

回归的是「每次更新后账号密码变成一串密文」——换账户启动时 `load()` 把解不开的密文当
成明文又加密一层，再顺着脏标记写回配置文件，原密码从此不可恢复。
"""

from __future__ import annotations

import base64

import pytest

from app.models.ConfigBase import (
    UNREADABLE_SECRET_PLACEHOLDER,
    ConfigItem,
    EncryptValidator,
)
from app.utils.platform import IS_WINDOWS

pytestmark = pytest.mark.skipif(not IS_WINDOWS, reason="仅 Windows 走 DPAPI 实现")


@pytest.fixture
def foreign_ciphertext() -> str:
    """构造一个结构合法、但本账户解不开的密文。

    取一份真实密文，把其中的 master key GUID 抹掉：从本账户看过去，另一个
    Windows 账户写的密文就是这个样子——头部合法，钥匙找不到。
    """

    import win32crypt

    real = win32crypt.CryptProtectData(
        "another-account-password".encode("utf-8"), None, None, None, None, 0
    )
    broken = real[:20] + bytes(16) + real[36:]
    return base64.b64encode(broken).decode("utf-8")


@pytest.fixture
def password_item() -> ConfigItem:
    return ConfigItem("Info", "Password", "", EncryptValidator())


def _load(item: ConfigItem, disk_value: str) -> None:
    """模拟 ConfigBase.load()：把配置文件里的原始值喂给配置项。"""

    item.setValue(disk_value)


def test_foreign_ciphertext_is_never_re_encrypted(
    password_item: ConfigItem, foreign_ciphertext: str
) -> None:
    _load(password_item, foreign_ciphertext)

    # 落盘口径必须与配置文件里的原值逐字相同，否则 load() 会判定脏数据并写回，
    # 把另一个账户的密码永久覆盖掉。
    assert password_item.getValue(if_decrypt=False) == foreign_ciphertext


def test_foreign_ciphertext_reads_back_as_placeholder(
    password_item: ConfigItem, foreign_ciphertext: str
) -> None:
    _load(password_item, foreign_ciphertext)

    assert password_item.getValue(if_decrypt=True) == UNREADABLE_SECRET_PLACEHOLDER


def test_password_can_be_re_entered_over_foreign_ciphertext(
    password_item: ConfigItem, foreign_ciphertext: str
) -> None:
    """密文解不开时，用户至少还能重新填一遍，不能连覆盖都做不到。"""

    _load(password_item, foreign_ciphertext)

    password_item.setValue("brand-new-password")

    assert password_item.getValue(if_decrypt=True) == "brand-new-password"


def test_own_ciphertext_survives_load_unchanged(password_item: ConfigItem) -> None:
    from app.utils.platform.windows.secret import dpapi_encrypt

    stored = dpapi_encrypt("my-real-password")

    _load(password_item, stored)

    assert password_item.getValue(if_decrypt=False) == stored
    assert password_item.getValue(if_decrypt=True) == "my-real-password"


def test_legacy_user_scope_ciphertext_survives_load_unchanged(
    password_item: ConfigItem,
) -> None:
    """机器作用域上线前写下的密文，加载后不得被改写。"""

    import win32crypt

    legacy_blob = win32crypt.CryptProtectData(
        "legacy-password".encode("utf-8"), None, None, None, None, 0
    )
    legacy = base64.b64encode(legacy_blob).decode("utf-8")

    _load(password_item, legacy)

    assert password_item.getValue(if_decrypt=False) == legacy
    assert password_item.getValue(if_decrypt=True) == "legacy-password"


def test_plaintext_input_is_encrypted(password_item: ConfigItem) -> None:
    from app.utils.platform.common.secret import looks_like_dpapi_blob

    password_item.setValue("typed-by-the-user")

    stored = password_item.getValue(if_decrypt=False)
    assert looks_like_dpapi_blob(stored) is True
    assert stored != "typed-by-the-user"
    assert password_item.getValue(if_decrypt=True) == "typed-by-the-user"


def test_empty_value_stays_empty(password_item: ConfigItem) -> None:
    password_item.setValue("")

    assert password_item.getValue(if_decrypt=False) == ""
    assert password_item.getValue(if_decrypt=True) == ""
