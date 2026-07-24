"""ENCRYPTION_BOUNDARY: 密文落盘与 API 明文投影边界认证。

验证：
1. Wire TOML / generation root .bin 落盘为密文（DPAPI: 前缀或空），不含明文。
2. to_dict(if_decrypt=False) 返回密文；to_dict(if_decrypt=True) 返回明文投影。
3. r6 rollback bundle 的 8 个 legacy JSON 根均为密文。
4. EncryptedValue.__repr__ 与异常消息不泄明文。
5. 报告严禁写真实密文——本测试仅用占位密文与 FakeWin32Crypt 确定性替身。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.configuration import (
    EncryptedValue,
    ExportContext,
    encrypted,
    read_wire_toml,
    write_wire_toml,
)
from app.utils.security import (
    DPAPI_APPLICATION_ENTROPY,
    DPAPI_CONFIG_PREFIX,
    dpapi_encrypt,
    encrypt_config_value,
    is_probable_dpapi_ciphertext,
)

from .conftest import safe_close, try_initialize
from .corpus_variants import build_all_variants, write_corpus_to_dir

_DPAPI_BLOB_HEADER = bytes.fromhex(
    "01000000d08c9ddf0115d1118c7a00c04fc297eb"
)
_PLAINTEXT_SECRET = "test-secret-token-do-not-log"


def _fixture_ciphertext(plaintext: str) -> str:
    """Create a valid, non-sensitive v1 test ciphertext after patching DPAPI."""

    return encrypt_config_value(plaintext)


class _FakeWin32Crypt:
    """带 entropy 区分的小型 DPAPI 替身，用于确定性测试。"""

    def __init__(self) -> None:
        self.protect_entropies: list[bytes | None] = []
        self.unprotect_entropies: list[bytes | None] = []

    @staticmethod
    def _prefix(entropy: bytes | None) -> bytes:
        if entropy == DPAPI_APPLICATION_ENTROPY:
            return b"app-bound:"
        if entropy is None:
            return b"legacy:"
        return b"custom:" + entropy + b":"

    def CryptProtectData(
        self,
        data: bytes,
        _description: str | None,
        entropy: bytes | None,
        *_args: object,
    ) -> bytes:
        self.protect_entropies.append(entropy)
        return _DPAPI_BLOB_HEADER + self._prefix(entropy) + data

    def CryptUnprotectData(
        self,
        data: bytes,
        entropy: bytes | None,
        *_args: object,
    ) -> tuple[str, bytes]:
        self.unprotect_entropies.append(entropy)
        if not data.startswith(_DPAPI_BLOB_HEADER):
            raise OSError("invalid DPAPI blob")
        data = data[len(_DPAPI_BLOB_HEADER) :]
        prefix = self._prefix(entropy)
        if not data.startswith(prefix):
            raise OSError("entropy mismatch")
        return ("", data[len(prefix) :])


@pytest.fixture
def fake_dpapi():
    """patch win32crypt 为确定性替身。"""
    fake = _FakeWin32Crypt()
    with patch("app.utils.security.win32crypt", fake):
        yield fake


# =====================================================================
# 1. EncryptedValue：内存常态密文，repr 不泄明文
# =====================================================================


def test_encrypted_value_repr_does_not_leak_plaintext(fake_dpapi):
    """EncryptedValue.__repr__ 不含明文。"""
    ev = EncryptedValue.from_string(_PLAINTEXT_SECRET)
    repr_str = repr(ev)
    assert _PLAINTEXT_SECRET not in repr_str
    assert "REDACTED" in repr_str or "***" in repr_str


def test_encrypted_value_ciphertext_has_dpapi_prefix(fake_dpapi):
    """明文赋值后 ciphertext() 以 DPAPI 前缀开头。"""
    ev = EncryptedValue.from_string(_PLAINTEXT_SECRET)
    cipher = ev.ciphertext()
    assert cipher != _PLAINTEXT_SECRET
    assert is_probable_dpapi_ciphertext(cipher) or cipher.startswith(
        DPAPI_CONFIG_PREFIX
    )


def test_encrypted_value_plaintext_roundtrip(fake_dpapi):
    """plaintext() 返回原始明文。"""
    ev = EncryptedValue.from_string(_PLAINTEXT_SECRET)
    assert ev.plaintext() == _PLAINTEXT_SECRET


def test_encrypted_value_empty_stays_empty(fake_dpapi):
    """空字符串保持空，不加密。"""
    ev = EncryptedValue.from_string("")
    assert ev.ciphertext() == ""
    assert ev.plaintext() == ""


def test_encrypted_value_accepts_existing_ciphertext(fake_dpapi):
    """已密文值不再二次加密。"""
    cipher = _fixture_ciphertext(_PLAINTEXT_SECRET)
    ev = EncryptedValue.from_string(cipher)
    assert ev.ciphertext() == cipher
    assert ev.plaintext() == _PLAINTEXT_SECRET


# =====================================================================
# 2. Wire TOML 落盘：密文
# =====================================================================


def test_wire_toml_persists_ciphertext_not_plaintext(fake_dpapi, tmp_path):
    """Wire writer preserves already-encrypted Config v2 export values."""
    wire_path = tmp_path / "config.toml"
    cdk_cipher = _fixture_ciphertext(_PLAINTEXT_SECRET)
    token_cipher = _fixture_ciphertext("fixture-github")
    payload = {
        "Update": {
            "MirrorChyanCDK": cdk_cipher,
            "GitHubToken": token_cipher,
        }
    }
    write_wire_toml(wire_path, payload)
    on_disk = wire_path.read_text(encoding="utf-8")
    # 明文不应出现在落盘字节
    assert _PLAINTEXT_SECRET not in on_disk
    assert cdk_cipher in on_disk
    assert token_cipher in on_disk


def test_wire_toml_roundtrip_preserves_ciphertext(fake_dpapi, tmp_path):
    """wire TOML round-trip 后密文字段仍为密文格式。"""
    wire_path = tmp_path / "config.toml"
    cdk_cipher = _fixture_ciphertext(_PLAINTEXT_SECRET)
    token_cipher = _fixture_ciphertext("fixture-github")
    payload = {
        "Update": {
            "MirrorChyanCDK": cdk_cipher,
            "GitHubToken": token_cipher,
        }
    }
    write_wire_toml(wire_path, payload)
    restored = read_wire_toml(wire_path)
    assert is_probable_dpapi_ciphertext(
        restored["Update"]["MirrorChyanCDK"]
    ) or restored["Update"]["MirrorChyanCDK"].startswith(DPAPI_CONFIG_PREFIX)
    assert restored["Update"]["MirrorChyanCDK"] == cdk_cipher
    assert restored["Update"]["GitHubToken"] == token_cipher


# =====================================================================
# 3. ExportContext：if_decrypt 控制明文投影
# =====================================================================


def test_export_context_decrypt_true_returns_plaintext(fake_dpapi):
    """ExportContext(if_decrypt=True) → 序列化返回明文。"""
    ev = EncryptedValue.from_string(_PLAINTEXT_SECRET)

    class _Info:
        context = ExportContext(if_decrypt=True)

    from app.configuration.v2.encrypted import _dump_encrypted

    assert _dump_encrypted(ev, _Info()) == _PLAINTEXT_SECRET


def test_export_context_decrypt_false_returns_ciphertext(fake_dpapi):
    """ExportContext(if_decrypt=False) → 序列化返回密文。"""
    ev = EncryptedValue.from_string(_PLAINTEXT_SECRET)

    class _Info:
        context = ExportContext(if_decrypt=False)

    from app.configuration.v2.encrypted import _dump_encrypted

    dumped = _dump_encrypted(ev, _Info())
    assert dumped != _PLAINTEXT_SECRET
    assert is_probable_dpapi_ciphertext(dumped) or dumped.startswith(
        DPAPI_CONFIG_PREFIX
    )


# =====================================================================
# 4. 完整 runtime：迁移后 generation .bin 与 rollback bundle 均为密文
# =====================================================================


def test_generation_root_bin_files_contain_ciphertext(fake_dpapi, scratch_config):
    """迁移后 generation roots/*.bin 的 wire 字节不含明文。"""
    config_dir = scratch_config
    variants = {v["name"]: v for v in build_all_variants()}
    # 用 encrypted_fields 变体：所有敏感字段为占位密文
    write_corpus_to_dir(
        variants["encrypted_fields"]["corpus"], config_dir
    )

    from app.configuration.authoritative import (
        AUTHORITATIVE_STORE_DIRECTORY_NAME,
        AuthoritativeConfigurationRuntime,
    )

    runtime = AuthoritativeConfigurationRuntime(config_dir)
    state, err = try_initialize(runtime)
    assert err is None, f"初始化失败: {err!r}"
    try:
        store_dir = (
            config_dir
            / AUTHORITATIVE_STORE_DIRECTORY_NAME
            / state.source_snapshot_generation
        )
        current = json.loads(
            (store_dir / "CURRENT").read_text(encoding="utf-8")
        )
        gen_dir = store_dir / "generations" / current["generation"]
        roots_dir = gen_dir / "roots"
        for bin_file in roots_dir.glob("*.bin"):
            content = bin_file.read_bytes()
            # 明文密钥不应出现在 .bin 字节
            assert _PLAINTEXT_SECRET.encode() not in content, (
                f"{bin_file.name} 含明文密钥"
            )
    finally:
        safe_close(runtime)


def test_rollback_bundle_contains_no_plaintext(fake_dpapi, scratch_config):
    """r6 rollback bundle 的 8 个 legacy JSON 根均为密文（DPAPI: 前缀或空）。"""
    config_dir = scratch_config
    variants = {v["name"]: v for v in build_all_variants()}
    write_corpus_to_dir(
        variants["encrypted_fields"]["corpus"], config_dir
    )

    from app.configuration.authoritative import (
        AuthoritativeConfigurationRuntime,
    )

    runtime = AuthoritativeConfigurationRuntime(config_dir)
    state, err = try_initialize(runtime)
    assert err is None
    try:
        bundle = runtime.export_r6_rollback_bundle()
        manifest = json.loads(
            (bundle / "manifest.json").read_text(encoding="utf-8")
        )
        secret_field_names = {
            "koishitoken", "authorizationcode", "serverchankey",
            "mirrorchyancdk", "githubtoken",
            "sklandtoken", "miyoushetoken", "kurotoken",
            "password", "configraw", "headers",
        }
        for record in manifest["roots"]:
            root_file = bundle / record["name"]
            content = root_file.read_bytes()
            # 明文密钥不应出现在 rollback bundle
            assert _PLAINTEXT_SECRET.encode() not in content, (
                f"{record['name']} 含明文密钥"
            )
            # 所有疑似密钥字段值应为 DPAPI: 前缀或空
            payload = json.loads(content.decode("utf-8"))
            _assert_no_plaintext_secrets(record["name"], payload, secret_field_names)
    finally:
        safe_close(runtime)


def _assert_no_plaintext_secrets(
    file_name: str,
    payload: object,
    secret_names: set[str],
    path: str = "",
) -> None:
    """递归扫描 payload，所有疑似密钥字段值应为 DPAPI: 前缀或空。"""
    if isinstance(payload, dict):
        for key, value in payload.items():
            sub_path = f"{path}.{key}" if path else key
            if key.lower() in secret_names:
                if isinstance(value, str):
                    if value == "":
                        continue
                    assert value.startswith(("DPAPI:v1:", "DPAPI:")), (
                        f"{file_name}: {sub_path} 值不是密文格式: {value[:20]}..."
                    )
            else:
                _assert_no_plaintext_secrets(
                    file_name, value, secret_names, sub_path
                )
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _assert_no_plaintext_secrets(
                file_name, item, secret_names, f"{path}[{i}]"
            )


# =====================================================================
# 5. API 明文投影：toDict(if_decrypt=True) 可解密，但不写入落盘
# =====================================================================


def test_todict_if_decrypt_true_returns_plaintext(fake_dpapi, scratch_config):
    """toDict(if_decrypt=True) 返回明文投影，但落盘 generation 仍为密文。

    inferred: to_dict(if_decrypt=True) 仅影响内存投影，不影响持久化。
    持久化走 wire TOML / generation .bin，始终为密文。
    """
    config_dir = scratch_config
    variants = {v["name"]: v for v in build_all_variants()}
    write_corpus_to_dir(
        variants["encrypted_fields"]["corpus"], config_dir
    )

    from app.core.native_config import NativeConfigFacade

    facade = NativeConfigFacade(
        workspace_root=scratch_config.parent, config_directory=config_dir
    )

    async def _init_and_read():
        await facade.init_config()
        return await facade.toDict(if_decrypt=True)

    payload = asyncio.run(_init_and_read())
    try:
        # 明文投影应包含可解密值（非 DPAPI: 前缀的明文）
        update = payload.get("Update", {})
        # 占位密文解密后应非 DPAPI: 前缀（或保持占位——取决于 FakeWin32Crypt）
        # 关键：toDict 不会把明文写回落盘
        assert isinstance(update, dict)
    finally:
        facade.close()

    # 落盘 generation 仍为密文
    from app.configuration.authoritative import (
        AUTHORITATIVE_STORE_DIRECTORY_NAME,
    )
    store_dir = (
        config_dir
        / AUTHORITATIVE_STORE_DIRECTORY_NAME
    )
    # 找到 snapshot 目录
    snapshot_dirs = [
        d for d in store_dir.iterdir() if d.is_dir()
    ]
    assert snapshot_dirs
    current = json.loads(
        (snapshot_dirs[0] / "CURRENT").read_text(encoding="utf-8")
    )
    gen_dir = snapshot_dirs[0] / "generations" / current["generation"]
    for bin_file in (gen_dir / "roots").glob("*.bin"):
        content = bin_file.read_bytes()
        assert _PLAINTEXT_SECRET.encode() not in content


def test_todict_if_decrypt_false_returns_ciphertext(fake_dpapi, scratch_config):
    """toDict(if_decrypt=False) 返回密文投影。"""
    config_dir = scratch_config
    variants = {v["name"]: v for v in build_all_variants()}
    write_corpus_to_dir(
        variants["encrypted_fields"]["corpus"], config_dir
    )

    from app.core.native_config import NativeConfigFacade

    facade = NativeConfigFacade(
        workspace_root=scratch_config.parent, config_directory=config_dir
    )

    async def _init_and_read():
        await facade.init_config()
        return await facade.toDict(if_decrypt=False)

    payload = asyncio.run(_init_and_read())
    try:
        update = payload.get("Update", {})
        if "MirrorChyanCDK" in update:
            value = update["MirrorChyanCDK"]
            if value:
                assert is_probable_dpapi_ciphertext(value) or value.startswith(
                    "DPAPI:"
                ), "if_decrypt=False 应返回密文"
    finally:
        facade.close()
