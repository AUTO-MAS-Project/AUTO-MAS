"""Config v2 模式转换语义测试。

覆盖 off / shadow / canary / authoritative 四种模式下的：
- ``LegacyWireAdapter`` 属性互斥性
- ``shadow_write`` 文件后缀行为（off 不写、shadow 写 ``.v2.shadow.toml``、
  canary 写 ``.v2.toml``）
- ``assert_config_v2_startup_mode_ready`` 对四种受支持模式均放行
"""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.configuration import (
    CONFIG_V2_MODE_AUTHORITATIVE,
    CONFIG_V2_MODE_CANARY,
    CONFIG_V2_MODE_OFF,
    CONFIG_V2_MODE_SHADOW,
    assert_config_v2_startup_mode_ready,
)
from app.configuration.compat import (
    SHADOW_SUFFIX,
    V2_SUFFIX,
    LegacyWireAdapter,
)


class _IdentityCodec:
    """直通 codec：legacy 与 wire 同形，用于隔离模式行为。"""

    def encode(self, legacy_data: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(legacy_data)

    def decode(self, wire_data: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(wire_data)


def _build_adapter_with_codec(file_name: str = "Config.json") -> LegacyWireAdapter:
    adapter = LegacyWireAdapter()
    adapter.register_codec(
        file_name,
        _IdentityCodec(),
        secrets_protected=True,
    )
    return adapter


class ModePropertyTransitionTest(unittest.TestCase):
    """四种模式的属性互斥性：同一时刻只有一个 ``is_*`` 为真。"""

    def test_off_mode_properties(self) -> None:
        adapter = _build_adapter_with_codec()
        with patch("app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_OFF):
            self.assertTrue(adapter.is_off)
            self.assertFalse(adapter.is_shadow)
            self.assertFalse(adapter.is_canary)
            self.assertFalse(adapter.is_authoritative)
            self.assertEqual(adapter.mode, CONFIG_V2_MODE_OFF)

    def test_shadow_mode_properties(self) -> None:
        adapter = _build_adapter_with_codec()
        with patch("app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_SHADOW):
            self.assertFalse(adapter.is_off)
            self.assertTrue(adapter.is_shadow)
            self.assertFalse(adapter.is_canary)
            self.assertFalse(adapter.is_authoritative)
            self.assertEqual(adapter.mode, CONFIG_V2_MODE_SHADOW)

    def test_canary_mode_properties(self) -> None:
        adapter = _build_adapter_with_codec()
        with patch("app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_CANARY):
            self.assertFalse(adapter.is_off)
            self.assertFalse(adapter.is_shadow)
            self.assertTrue(adapter.is_canary)
            self.assertFalse(adapter.is_authoritative)
            self.assertEqual(adapter.mode, CONFIG_V2_MODE_CANARY)

    def test_authoritative_mode_properties(self) -> None:
        adapter = _build_adapter_with_codec()
        with patch(
            "app.configuration.compat.CONFIG_V2_MODE",
            CONFIG_V2_MODE_AUTHORITATIVE,
        ):
            self.assertFalse(adapter.is_off)
            self.assertFalse(adapter.is_shadow)
            self.assertFalse(adapter.is_canary)
            self.assertTrue(adapter.is_authoritative)
            self.assertEqual(adapter.mode, CONFIG_V2_MODE_AUTHORITATIVE)


class ShadowWriteFileSuffixTest(unittest.TestCase):
    """不同模式下 shadow_write 必须写出正确的文件后缀或不写。"""

    _PAYLOAD: dict[str, Any] = {"Data": {"Value": "shadow-test"}}

    def test_off_mode_writes_no_file(self) -> None:
        adapter = _build_adapter_with_codec()
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_OFF),
        ):
            legacy_path = Path(temp_dir) / "Config.json"
            result = adapter.shadow_write(legacy_path, self._PAYLOAD)

            self.assertIsNone(result)
            self.assertEqual(list(Path(temp_dir).glob("*.toml")), [])

    def test_shadow_mode_writes_v2_shadow_toml(self) -> None:
        adapter = _build_adapter_with_codec()
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_SHADOW),
        ):
            legacy_path = Path(temp_dir) / "Config.json"
            result = adapter.shadow_write(legacy_path, self._PAYLOAD)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.name, f"Config{SHADOW_SUFFIX}")
            self.assertEqual(
                result.suffixes, [".v2", ".shadow", ".toml"]
            )
            self.assertTrue(result.is_file())
            self.assertFalse(
                (legacy_path.with_suffix(V2_SUFFIX)).exists()
            )

    def test_canary_mode_writes_v2_toml(self) -> None:
        adapter = _build_adapter_with_codec()
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_CANARY),
        ):
            legacy_path = Path(temp_dir) / "Config.json"
            result = adapter.shadow_write(legacy_path, self._PAYLOAD)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.name, f"Config{V2_SUFFIX}")
            self.assertEqual(result.suffixes, [".v2", ".toml"])
            self.assertTrue(result.is_file())
            self.assertFalse(
                (legacy_path.with_suffix(SHADOW_SUFFIX)).exists()
            )

    def test_authoritative_mode_writes_v2_toml_suffix(self) -> None:
        """authoritative 在 adapter 层使用 V2_SUFFIX；服务层门禁由上层拒绝。"""
        adapter = _build_adapter_with_codec()
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "app.configuration.compat.CONFIG_V2_MODE",
                CONFIG_V2_MODE_AUTHORITATIVE,
            ),
        ):
            legacy_path = Path(temp_dir) / "Config.json"
            result = adapter.shadow_write(legacy_path, self._PAYLOAD)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.name, f"Config{V2_SUFFIX}")

    def test_mode_transition_off_to_shadow_changes_output_suffix(
        self,
    ) -> None:
        """同一 adapter 在模式从 off 切到 shadow 后必须开始写出文件。"""
        adapter = _build_adapter_with_codec()
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"

            with patch(
                "app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_OFF
            ):
                off_result = adapter.shadow_write(
                    legacy_path, self._PAYLOAD
                )
            self.assertIsNone(off_result)
            self.assertEqual(list(Path(temp_dir).glob("*.toml")), [])

            with patch(
                "app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_SHADOW
            ):
                shadow_result = adapter.shadow_write(
                    legacy_path, self._PAYLOAD
                )
            self.assertIsNotNone(shadow_result)
            assert shadow_result is not None
            self.assertEqual(
                shadow_result.name, f"Config{SHADOW_SUFFIX}"
            )

    def test_mode_transition_shadow_to_canary_changes_suffix(self) -> None:
        """同一 adapter 在模式从 shadow 切到 canary 后必须改用 V2_SUFFIX。"""
        adapter = _build_adapter_with_codec()
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"

            with patch(
                "app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_SHADOW
            ):
                shadow_result = adapter.shadow_write(
                    legacy_path, self._PAYLOAD
                )
            assert shadow_result is not None
            self.assertEqual(
                shadow_result.name, f"Config{SHADOW_SUFFIX}"
            )

            with patch(
                "app.configuration.compat.CONFIG_V2_MODE", CONFIG_V2_MODE_CANARY
            ):
                canary_result = adapter.shadow_write(
                    legacy_path, self._PAYLOAD
                )
            assert canary_result is not None
            self.assertEqual(canary_result.name, f"Config{V2_SUFFIX}")

            self.assertTrue(shadow_result.is_file())
            self.assertTrue(canary_result.is_file())


class StartupModeGateTest(unittest.TestCase):
    """四种受支持模式都可启动，authoritative 为生产默认值。"""

    def test_off_mode_passes_gate(self) -> None:
        assert_config_v2_startup_mode_ready(CONFIG_V2_MODE_OFF)

    def test_shadow_mode_passes_gate(self) -> None:
        assert_config_v2_startup_mode_ready(CONFIG_V2_MODE_SHADOW)

    def test_canary_mode_passes_gate(self) -> None:
        assert_config_v2_startup_mode_ready(CONFIG_V2_MODE_CANARY)

    def test_authoritative_mode_passes_gate(self) -> None:
        assert_config_v2_startup_mode_ready(
            CONFIG_V2_MODE_AUTHORITATIVE
        )

    def test_none_mode_uses_process_default_and_may_pass(self) -> None:
        """``mode=None`` 时使用进程级 ``CONFIG_V2_MODE`` 默认值。"""
        import app.configuration as config_module

        default_mode = config_module.CONFIG_V2_MODE
        self.assertIn(
            default_mode,
            {
                CONFIG_V2_MODE_OFF,
                CONFIG_V2_MODE_SHADOW,
                CONFIG_V2_MODE_CANARY,
                CONFIG_V2_MODE_AUTHORITATIVE,
            },
        )
        assert_config_v2_startup_mode_ready(None)


class AuthoritativeModeBlockTransitionTest(unittest.IsolatedAsyncioTestCase):
    """authoritative 必须在 legacy 副作用发生前 fail-closed。"""

    async def test_authoritative_load_blocks_before_legacy_read(self) -> None:
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"
            legacy_path.write_text(
                '{"Data": {"Value": "never-touched"}}',
                encoding="utf-8",
            )

            service = ConfigService()
            with (
                patch(
                    "app.core.config_service.CONFIG_V2_MODE",
                    CONFIG_V2_MODE_AUTHORITATIVE,
                ),
                patch(
                    "app.configuration.compat.CONFIG_V2_MODE",
                    CONFIG_V2_MODE_AUTHORITATIVE,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "initialized by NativeConfigFacade",
                ):
                    await service._authoritative_load()

            self.assertEqual(
                legacy_path.read_text(encoding="utf-8"),
                '{"Data": {"Value": "never-touched"}}',
            )

    async def test_authoritative_save_blocks_before_shadow_write(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"
            service = ConfigService()
            with (
                patch(
                    "app.core.config_service.CONFIG_V2_MODE",
                    CONFIG_V2_MODE_AUTHORITATIVE,
                ),
                patch(
                    "app.configuration.compat.CONFIG_V2_MODE",
                    CONFIG_V2_MODE_AUTHORITATIVE,
                ),
                patch(
                    "app.core.config_service.legacy_adapter.shadow_write"
                ) as shadow_write,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "rejects legacy JSON-first saves",
                ):
                    await service.save_config(
                        legacy_path,
                        {"Data": {"Value": "blocked"}},
                    )

            shadow_write.assert_not_called()
            self.assertFalse(legacy_path.exists())


if __name__ == "__main__":
    unittest.main()
