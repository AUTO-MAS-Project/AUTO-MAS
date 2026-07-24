"""DPAPI application-entropy binding and legacy migration regressions."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Annotated
from unittest import IsolatedAsyncioTestCase, TestCase, skipUnless
from unittest.mock import patch

from pydantic import Field

from app.configuration import (
    ConfigEntry,
    ConfigGroup,
    EncryptedValue,
    config_manager,
    encrypted,
    read_wire_toml,
    write_wire_toml,
)
from app.models.ConfigBase import (
    ConfigBase,
    ConfigItem,
    EncryptedConfigValueError,
    EncryptValidator,
    MultipleConfig,
)
from app.utils.security import (
    DPAPI_APPLICATION_ENTROPY,
    DPAPI_CONFIG_PREFIX,
    DPAPIProtectionError,
    decrypt_config_value,
    decrypt_config_value_with_status,
    dpapi_decrypt,
    dpapi_decrypt_with_status,
    dpapi_encrypt,
    encrypt_config_value,
)

_DPAPI_BLOB_HEADER = bytes.fromhex(
    "01000000d08c9ddf0115d1118c7a00c04fc297eb"
)


class _FakeWin32Crypt:
    """Small integrity-checking DPAPI stand-in with entropy separation."""

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


class _SecretConfig(ConfigBase):
    def __init__(self) -> None:
        self.Secret_Token = ConfigItem(
            "Secret",
            "Token",
            "",
            EncryptValidator(),
        )
        super().__init__()


class _SecretCollectionRoot(ConfigBase):
    def __init__(self) -> None:
        self.Children = MultipleConfig([_SecretConfig])
        super().__init__()


class _V2SecretGroup(ConfigGroup):
    token: Annotated[str, encrypted()] = ""


class _V2SecretEntry(ConfigEntry):
    secrets: _V2SecretGroup = Field(default_factory=_V2SecretGroup)


class TestDPAPIApplicationEntropy(TestCase):
    def setUp(self) -> None:
        self.fake = _FakeWin32Crypt()
        self.patcher = patch("app.utils.security.win32crypt", self.fake)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_default_encrypt_and_decrypt_use_application_entropy(self) -> None:
        ciphertext = dpapi_encrypt("bound-secret")
        result = dpapi_decrypt_with_status(ciphertext)

        self.assertEqual(result.plaintext, "bound-secret")
        self.assertFalse(result.needs_migration)
        self.assertEqual(self.fake.protect_entropies, [DPAPI_APPLICATION_ENTROPY])
        self.assertEqual(self.fake.unprotect_entropies, [DPAPI_APPLICATION_ENTROPY])

    def test_legacy_cipher_is_readable_and_reports_migration(self) -> None:
        ciphertext = dpapi_encrypt("legacy-secret", entropy=None)
        self.fake.unprotect_entropies.clear()

        result = dpapi_decrypt_with_status(ciphertext)

        self.assertEqual(result.plaintext, "legacy-secret")
        self.assertTrue(result.needs_migration)
        self.assertEqual(
            self.fake.unprotect_entropies,
            [DPAPI_APPLICATION_ENTROPY, None],
        )
        self.assertNotIn("legacy-secret", repr(result))
        self.assertNotIn(ciphertext, repr(result))

    def test_explicit_entropy_none_is_an_exact_legacy_operation(self) -> None:
        ciphertext = dpapi_encrypt("legacy-secret", entropy=None)
        self.fake.unprotect_entropies.clear()

        self.assertEqual(dpapi_decrypt(ciphertext, entropy=None), "legacy-secret")
        self.assertEqual(self.fake.unprotect_entropies, [None])

    def test_damaged_cipher_raises_redacted_error_after_bounded_fallback(self) -> None:
        ciphertext = base64.b64encode(
            _DPAPI_BLOB_HEADER + b"damaged-payload"
        ).decode("ascii")

        with self.assertRaises(DPAPIProtectionError) as raised:
            dpapi_decrypt_with_status(ciphertext)

        self.assertEqual(
            self.fake.unprotect_entropies,
            [DPAPI_APPLICATION_ENTROPY, None],
        )
        self.assertNotIn(ciphertext, str(raised.exception))
        self.assertNotIn(ciphertext, repr(raised.exception))

    def test_invalid_base64_never_reaches_dpapi_or_echoes_input(self) -> None:
        invalid = "not base64 or a secret!"

        with self.assertRaises(DPAPIProtectionError) as raised:
            dpapi_decrypt_with_status(invalid)

        self.assertEqual(self.fake.unprotect_entropies, [])
        self.assertNotIn(invalid, str(raised.exception))

    def test_shared_config_envelope_is_versioned(self) -> None:
        ciphertext = encrypt_config_value("versioned-secret")
        result = decrypt_config_value_with_status(ciphertext)

        self.assertTrue(ciphertext.startswith(DPAPI_CONFIG_PREFIX))
        self.assertEqual(result.plaintext, "versioned-secret")
        self.assertFalse(result.needs_migration)

    def test_legacy_v2_envelope_reports_format_migration(self) -> None:
        legacy = "DPAPI:" + dpapi_encrypt("legacy-v2-secret", entropy=None)

        result = decrypt_config_value_with_status(legacy)

        self.assertEqual(result.plaintext, "legacy-v2-secret")
        self.assertTrue(result.needs_migration)

    def test_damaged_current_envelope_never_falls_back_to_legacy_entropy(
        self,
    ) -> None:
        damaged = DPAPI_CONFIG_PREFIX + base64.b64encode(
            _DPAPI_BLOB_HEADER + b"damaged-current-payload"
        ).decode("ascii")

        with self.assertRaises(DPAPIProtectionError):
            decrypt_config_value_with_status(damaged)

        self.assertEqual(self.fake.unprotect_entropies, [DPAPI_APPLICATION_ENTROPY])


@skipUnless(os.name == "nt", "Windows DPAPI is required")
class TestRealWindowsDPAPIApplicationEntropy(TestCase):
    def test_application_binding_and_legacy_fallback_use_real_dpapi(self) -> None:
        secret = f"auto-mas-dpapi-regression-{uuid.uuid4()}"
        application_ciphertext = dpapi_encrypt(secret)
        legacy_ciphertext = dpapi_encrypt(secret, entropy=None)

        self.assertEqual(dpapi_decrypt(application_ciphertext), secret)
        with self.assertRaises(DPAPIProtectionError):
            dpapi_decrypt(application_ciphertext, entropy=None)

        legacy_result = dpapi_decrypt_with_status(legacy_ciphertext)
        self.assertEqual(legacy_result.plaintext, secret)
        self.assertTrue(legacy_result.needs_migration)


class TestLegacyConfigEntropyMigration(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.fake = _FakeWin32Crypt()
        self.patcher = patch("app.utils.security.win32crypt", self.fake)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    async def test_connect_migrates_legacy_cipher_and_preserves_plaintext_boundary(
        self,
    ) -> None:
        secret = "front-end-visible-only"
        legacy_ciphertext = dpapi_encrypt(secret, entropy=None)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Config.json"
            path.write_text(
                json.dumps({"Secret": {"Token": legacy_ciphertext}}),
                encoding="utf-8",
            )
            config = _SecretConfig()

            with patch("app.models.ConfigBase.logger.info") as audit_log:
                await config.connect(path)

            persisted = json.loads(path.read_text(encoding="utf-8"))
            migrated_ciphertext = persisted["Secret"]["Token"]
            self.assertNotEqual(migrated_ciphertext, legacy_ciphertext)
            self.assertTrue(migrated_ciphertext.startswith(DPAPI_CONFIG_PREFIX))
            self.assertNotIn(secret, path.read_text(encoding="utf-8"))
            self.assertEqual(decrypt_config_value(migrated_ciphertext), secret)
            self.assertFalse(
                decrypt_config_value_with_status(
                    migrated_ciphertext
                ).needs_migration
            )
            self.assertEqual(config.get("Secret", "Token"), secret)
            self.assertEqual(
                (await config.toDict())["Secret"]["Token"],
                secret,
            )
            self.assertEqual(
                (await config.toDict(if_decrypt=False))["Secret"]["Token"],
                migrated_ciphertext,
            )

            audit_arguments = repr(audit_log.call_args_list)
            self.assertNotIn(secret, audit_arguments)
            self.assertNotIn(legacy_ciphertext, audit_arguments)
            self.assertNotIn(migrated_ciphertext, audit_arguments)

    async def test_nested_collection_propagates_persisted_migration_context(
        self,
    ) -> None:
        secret = "nested-secret"
        legacy_ciphertext = dpapi_encrypt(secret, entropy=None)
        child_uid = str(uuid.uuid4())
        payload = {
            "SubConfigsInfo": {
                "Children": {
                    "instances": [{"uid": child_uid, "type": "_SecretConfig"}],
                    child_uid: {"Secret": {"Token": legacy_ciphertext}},
                }
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "NestedConfig.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            config = _SecretCollectionRoot()

            await config.connect(path)

            persisted = json.loads(path.read_text(encoding="utf-8"))
            migrated = persisted["SubConfigsInfo"]["Children"][child_uid]["Secret"][
                "Token"
            ]
            self.assertNotEqual(migrated, legacy_ciphertext)
            self.assertTrue(migrated.startswith(DPAPI_CONFIG_PREFIX))
            self.assertEqual(decrypt_config_value(migrated), secret)

    async def test_damaged_persisted_cipher_is_never_replaced_or_rewritten(
        self,
    ) -> None:
        damaged = base64.b64encode(
            _DPAPI_BLOB_HEADER + b"damaged-payload"
        ).decode("ascii")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Config.json"
            original = json.dumps({"Secret": {"Token": damaged}}).encode("utf-8")
            path.write_bytes(original)
            config = _SecretConfig()

            with self.assertRaises(EncryptedConfigValueError) as raised:
                await config.connect(path)

            self.assertEqual(path.read_bytes(), original)
            self.assertNotIn(damaged, str(raised.exception))
            self.assertNotIn("数据损坏", path.read_text(encoding="utf-8"))

    async def test_explicit_plaintext_assignment_can_replace_damaged_memory_value(
        self,
    ) -> None:
        damaged = base64.b64encode(b"damaged-dpapi-blob").decode("ascii")
        config = _SecretConfig()
        config.Secret_Token.value = damaged

        changed = config.Secret_Token.setValue("explicit-replacement")

        self.assertTrue(changed)
        self.assertEqual(config.Secret_Token.getValue(), "explicit-replacement")
        self.assertNotEqual(config.Secret_Token.getValue(if_decrypt=False), damaged)


class TestConfigV2EntropyMigration(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.fake = _FakeWin32Crypt()
        self.patcher = patch("app.utils.security.win32crypt", self.fake)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    async def test_legacy_v2_cipher_is_rewrapped_and_flushed_with_outcome(
        self,
    ) -> None:
        secret = "v2-legacy-secret"
        legacy = "DPAPI:" + dpapi_encrypt(secret, entropy=None)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ConfigV2.toml"
            write_wire_toml(path, {"secrets": {"token": legacy}})
            entry = _V2SecretEntry.build(file=path)
            try:
                await entry.activate()
                stored = entry.secrets.__dict__["token"]
                self.assertIsInstance(stored, EncryptedValue)
                self.assertEqual(
                    stored.migration_outcome(),
                    "legacy_dpapi_rewrapped_to_v1",
                )

                await config_manager.flush()
                persisted = read_wire_toml(path)["secrets"]["token"]
                self.assertTrue(persisted.startswith(DPAPI_CONFIG_PREFIX))
                self.assertEqual(decrypt_config_value(persisted), secret)
                self.assertNotIn(secret, path.read_text(encoding="utf-8"))
                self.assertEqual(entry.model_dump()["secrets"]["token"], secret)
            finally:
                await config_manager.dispose_node(entry)

    async def test_legacy_configbase_raw_cipher_is_rewrapped_by_v2(self) -> None:
        secret = "legacy-configbase-secret"
        legacy = dpapi_encrypt(secret, entropy=None)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ConfigV2.toml"
            write_wire_toml(path, {"secrets": {"token": legacy}})
            entry = _V2SecretEntry.build(file=path)
            try:
                await entry.activate()
                stored = entry.secrets.__dict__["token"]
                self.assertIsInstance(stored, EncryptedValue)
                self.assertEqual(
                    stored.migration_outcome(),
                    "legacy_dpapi_rewrapped_to_v1",
                )

                await config_manager.flush()
                persisted = read_wire_toml(path)["secrets"]["token"]
                self.assertTrue(persisted.startswith(DPAPI_CONFIG_PREFIX))
                self.assertEqual(decrypt_config_value(persisted), secret)
            finally:
                await config_manager.dispose_node(entry)

    async def test_damaged_v2_cipher_keeps_original_file_unchanged(self) -> None:
        damaged = DPAPI_CONFIG_PREFIX + base64.b64encode(
            _DPAPI_BLOB_HEADER + b"damaged-v2-payload"
        ).decode("ascii")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ConfigV2.toml"
            write_wire_toml(path, {"secrets": {"token": damaged}})
            original = path.read_bytes()
            entry = _V2SecretEntry.build(file=path)
            try:
                with self.assertRaises(Exception) as raised:
                    await entry.activate()
                self.assertEqual(path.read_bytes(), original)
                rendered = f"{raised.exception!s} {raised.exception!r}"
                self.assertNotIn(damaged, rendered)
            finally:
                await config_manager.dispose_node(entry)
