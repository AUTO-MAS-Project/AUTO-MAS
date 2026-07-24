"""迁移语料的完整 round-trip 认证测试。

验证脱敏 legacy 语料经过 ``legacy_production_roots_to_wire`` →
``production_wire_roots_to_legacy`` 的完整往返，并覆盖 TOML 序列化保真度、
空根迁移、未知字段 fail-closed 以及 shadow 写入路径。
"""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.configuration.compat import (
    SHADOW_SUFFIX,
    LegacyWireAdapter,
)
from app.configuration.production import (
    PRODUCTION_ROOT_FILES,
    PRODUCTION_ROOT_NAMES,
    ProductionRootSetError,
    legacy_production_roots_to_wire,
    production_wire_roots_to_legacy,
)
from app.configuration.v2.wire import (
    read_wire_toml,
    serialize_wire_toml,
    write_wire_toml,
)

from .corpus import build_desensitized_legacy_corpus


def _empty_legacy_roots() -> dict[str, object]:
    """与 ``tests.configuration.test_production_roots`` 相同的空根工厂。"""
    return {file_name: {} for file_name in PRODUCTION_ROOT_FILES.values()}


def _strip_tools_sub_configs_info(roots: dict[str, object]) -> dict[str, object]:
    """ToolsConfig.SubConfigsInfo 不被 Config v2 持久化，round-trip 后丢失。

    在比较前从原语料中移除该字段，使比较只覆盖被 v2 真正保留的路径。
    """
    stripped = copy.deepcopy(roots)
    tools = stripped.get("ToolsConfig.json")
    if isinstance(tools, dict) and "SubConfigsInfo" in tools:
        del tools["SubConfigsInfo"]
    return stripped


class MigrationCorpusRoundTripTest(unittest.TestCase):
    """语料 legacy → wire → legacy 必须在规范化形状上等价。"""

    def test_legacy_to_wire_to_legacy_roundtrip(self) -> None:
        corpus = build_desensitized_legacy_corpus()
        self.assertEqual(
            set(corpus), set(PRODUCTION_ROOT_FILES.values())
        )

        wire = legacy_production_roots_to_wire(corpus)
        self.assertEqual(tuple(wire), PRODUCTION_ROOT_NAMES)

        restored = production_wire_roots_to_legacy(wire)
        self.assertEqual(set(restored), set(PRODUCTION_ROOT_FILES.values()))

        expected = _strip_tools_sub_configs_info(dict(corpus))
        for file_name in PRODUCTION_ROOT_FILES.values():
            self.assertEqual(
                restored[file_name],
                expected[file_name],
                msg=f"round-trip mismatch: {file_name}",
            )

    def test_wire_toml_serialization_fidelity(self) -> None:
        """Wire dict → TOML 字符串 → 重读必须与原 Wire 同形。"""
        import tomllib

        corpus = build_desensitized_legacy_corpus()
        wire = legacy_production_roots_to_wire(corpus)

        for root_name in PRODUCTION_ROOT_NAMES:
            original = copy.deepcopy(dict(wire[root_name]))
            serialized = serialize_wire_toml(original)
            from_serialized_string = tomllib.loads(serialized)
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / f"{root_name}.toml"
                write_wire_toml(path, original)
                from_disk = read_wire_toml(path)
            self.assertEqual(
                from_disk,
                from_serialized_string,
                msg=f"TOML disk vs string mismatch: {root_name}",
            )
            self.assertEqual(
                from_disk,
                original,
                msg=f"TOML round-trip lost data: {root_name}",
            )

    def test_empty_root_migration(self) -> None:
        """空 legacy 根必须 round-trip 到规范化空集合形状。"""
        empty_roots = _empty_legacy_roots()
        wire = legacy_production_roots_to_wire(empty_roots)
        self.assertEqual(tuple(wire), PRODUCTION_ROOT_NAMES)

        restored = production_wire_roots_to_legacy(wire)
        self.assertEqual(set(restored), set(_empty_legacy_roots()))

        self.assertEqual(restored["EmulatorConfig.json"], {"instances": []})
        self.assertEqual(restored["PlanConfig.json"], {"instances": []})
        self.assertEqual(restored["ScriptConfig.json"], {"instances": []})
        self.assertEqual(restored["QueueConfig.json"], {"instances": []})
        self.assertEqual(
            restored["GameSignAccounts.json"], {"instances": []}
        )
        self.assertEqual(
            restored["Config.json"]["Function"]["HistoryRetentionTime"], 0
        )
        self.assertEqual(
            restored["ToolsConfig.json"]["ArknightsPC"]["Enabled"], False
        )
        self.assertEqual(
            restored["PluginConfig.json"]["Data"]["Version"], 1
        )

    def test_unknown_legacy_field_preservation(self) -> None:
        """未知 legacy 字段必须 fail-closed，不允许静默丢弃。"""

        corpus = build_desensitized_legacy_corpus()

        with self.assertRaises(ValueError) as raised_config:
            legacy_production_roots_to_wire(
                {
                    **corpus,
                    "Config.json": {
                        **corpus["Config.json"],
                        "UnknownGroup": {"Value": 1},
                    },
                }
            )
        self.assertIn("未知主配置路径", str(raised_config.exception))

        with self.assertRaises(ValueError) as raised_tools:
            legacy_production_roots_to_wire(
                {
                    **corpus,
                    "ToolsConfig.json": {
                        **corpus["ToolsConfig.json"],
                        "UnknownTool": {"Value": 1},
                    },
                }
            )
        self.assertIn("未知工具配置路径", str(raised_tools.exception))

        # EmulatorConfig 根级别未知字段触发 "$ 包含孤儿或未知字段"，
        # entry 内未知字段触发 "未知模拟器配置路径"。两者均 fail-closed。
        emulator_with_root_unknown = copy.deepcopy(
            corpus["EmulatorConfig.json"]
        )
        emulator_with_root_unknown["UnknownTop"] = "value"
        with self.assertRaises(ValueError) as raised_emulator_root:
            legacy_production_roots_to_wire(
                {
                    **corpus,
                    "EmulatorConfig.json": emulator_with_root_unknown,
                }
            )
        self.assertIn(
            "孤儿或未知字段", str(raised_emulator_root.exception)
        )

        emulator_with_entry_unknown = copy.deepcopy(
            corpus["EmulatorConfig.json"]
        )
        first_uid = emulator_with_entry_unknown["instances"][0]["uid"]
        emulator_with_entry_unknown[first_uid] = {
            **emulator_with_entry_unknown[first_uid],
            "UnknownGroup": {"Value": 1},
        }
        with self.assertRaises(ValueError) as raised_emulator_entry:
            legacy_production_roots_to_wire(
                {
                    **corpus,
                    "EmulatorConfig.json": emulator_with_entry_unknown,
                }
            )
        self.assertIn(
            "未知模拟器配置路径",
            str(raised_emulator_entry.exception),
        )


class ShadowWriteRoundTripTest(unittest.TestCase):
    """Shadow 写入路径必须生成与语料等价的 TOML 文件。"""

    def test_shadow_write_roundtrip_for_single_root(self) -> None:
        """注册 identity codec 后 shadow_write 必须写出可读回的 TOML。"""

        class _IdentityCodec:
            def encode(
                self, legacy_data: dict[str, Any]
            ) -> dict[str, Any]:
                return copy.deepcopy(legacy_data)

            def decode(self, wire_data: dict[str, Any]) -> dict[str, Any]:
                return copy.deepcopy(wire_data)

        adapter = LegacyWireAdapter()
        adapter.register_codec(
            "Config.json",
            _IdentityCodec(),
            secrets_protected=True,
        )

        corpus = build_desensitized_legacy_corpus()
        config_payload = copy.deepcopy(
            corpus["Config.json"]
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "app.configuration.compat.CONFIG_V2_MODE", "shadow"
            ),
        ):
            legacy_path = Path(temp_dir) / "Config.json"
            output_path = adapter.shadow_write(
                legacy_path, config_payload
            )

            self.assertIsNotNone(output_path)
            assert output_path is not None
            self.assertEqual(output_path.suffixes, [".v2", ".shadow", ".toml"])
            self.assertEqual(
                output_path.name, f"Config{SHADOW_SUFFIX}"
            )
            self.assertTrue(output_path.is_file())

            from_disk = read_wire_toml(output_path)
            self.assertEqual(from_disk, config_payload)
            # 语料已脱敏：占位密文是实际写入值，确认它存在而非真实明文。
            self.assertIn(
                "DPAPI:v1:REDACTED_BASE64_PLACEHOLDER",
                output_path.read_text(encoding="utf-8"),
            )

    def test_shadow_write_off_mode_writes_nothing(self) -> None:
        """off 模式下 shadow_write 必须返回 None 且不创建任何文件。"""

        class _IdentityCodec:
            def encode(
                self, legacy_data: dict[str, Any]
            ) -> dict[str, Any]:
                return copy.deepcopy(legacy_data)

            def decode(self, wire_data: dict[str, Any]) -> dict[str, Any]:
                return copy.deepcopy(wire_data)

        adapter = LegacyWireAdapter()
        adapter.register_codec(
            "Config.json",
            _IdentityCodec(),
            secrets_protected=True,
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "app.configuration.compat.CONFIG_V2_MODE", "off"
            ),
        ):
            legacy_path = Path(temp_dir) / "Config.json"
            result = adapter.shadow_write(
                legacy_path, {"Data": {"Value": "x"}}
            )

            self.assertIsNone(result)
            self.assertEqual(list(Path(temp_dir).glob("*.toml")), [])

    def test_shadow_write_no_codec_leaves_existing_files_intact(
        self,
    ) -> None:
        """没有注册 codec 时不能写入或删除已有 shadow 文件。"""
        adapter = LegacyWireAdapter()

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "app.configuration.compat.CONFIG_V2_MODE", "shadow"
            ),
        ):
            legacy_path = Path(temp_dir) / "ScriptConfig.json"
            shadow_path = legacy_path.with_suffix(SHADOW_SUFFIX)
            shadow_path.write_text("existing = true\n", encoding="utf-8")

            result = adapter.shadow_write(
                legacy_path,
                {"token": "plain-secret", "unknown": {"value": 1}},
            )

            self.assertIsNone(result)
            self.assertEqual(
                shadow_path.read_text(encoding="utf-8"),
                "existing = true\n",
            )
            self.assertEqual(
                list(Path(temp_dir).glob("*.toml")), [shadow_path]
            )


class ProductionRootSetIntegrityTest(unittest.TestCase):
    """生产根集合完整性：缺根、多根、非映射必须 fail-closed。"""

    def test_missing_root_fails_closed(self) -> None:
        corpus = build_desensitized_legacy_corpus()
        missing = dict(corpus)
        missing.pop("QueueConfig.json")
        with self.assertRaises(ProductionRootSetError):
            legacy_production_roots_to_wire(missing)

    def test_extra_root_fails_closed(self) -> None:
        corpus = build_desensitized_legacy_corpus()
        extra = dict(corpus)
        extra["Unknown.json"] = {}
        with self.assertRaises(ProductionRootSetError):
            legacy_production_roots_to_wire(extra)

    def test_none_payload_migrates_as_empty_root(self) -> None:
        """``None`` payload 表示文件缺失，必须按空根迁移。"""
        corpus = build_desensitized_legacy_corpus()
        none_roots = {name: None for name in corpus}
        wire = legacy_production_roots_to_wire(none_roots)
        self.assertEqual(tuple(wire), PRODUCTION_ROOT_NAMES)

        restored = production_wire_roots_to_legacy(wire)
        self.assertEqual(set(restored), set(corpus))
        self.assertEqual(
            restored["EmulatorConfig.json"], {"instances": []}
        )


if __name__ == "__main__":
    unittest.main()
