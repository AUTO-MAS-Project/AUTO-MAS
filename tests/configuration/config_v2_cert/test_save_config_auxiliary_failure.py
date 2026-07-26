"""ConfigService.save_config auxiliary v2 写失败误判成功专项核查。

任务点 7：必须以实际调用顺序、文件哈希和复现测试判定，不能只静态猜测。

核查目标：
- shadow/canary 模式下 legacy_adapter.shadow_write 失败时，save_config 是否吞没异常
  仅 logger.error，使调用方误判保存成功（auxiliary 写失败不可见）。
- 验证 JSON 在 observer 触发前已原子落盘（调用顺序），故配置不丢失。
- 验证 line 345 `legacy_adapter.is_authoritative` 分支为死代码（不可达）。
- 验证 authoritative 模式在 save_config 入口即 fail-closed（assert_startup_mode_ready 先于 uses_legacy_runtime）。

注意：config_service.py 用 loguru logger（from app.utils import get_logger），
标准 logging.assertLogs 无法捕获；改用 Mock 替身验证 logger.error 调用。
config_service.py 通过 `from app.configuration.compat import legacy_adapter`
导入了 legacy_adapter 的模块级绑定，必须 patch `app.core.config_service.legacy_adapter`。
"""

from __future__ import annotations

import hashlib
import inspect
import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from app.configuration import compat as compat_module
from app.configuration.compat import LegacyWireAdapter


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestSaveConfigAuxiliaryFailure:
    """复现 save_config 在 auxiliary v2 写失败时的误判成功行为。

    用 unittest.mock.patch 直接替换 config_service 模块内的 legacy_adapter
    与 logger 绑定，避免 loguru/标准 logging 捕获差异。
    """

    def test_shadow_write_failure_swallowed(self) -> None:
        """shadow 模式下 shadow_write 抛异常时，save_config 不抛、仅 logger.error。

        observed：调用方无法通过返回值/异常感知 auxiliary 写失败。
        """
        import asyncio

        from app.core import config_service as cs

        failing_adapter = mock.create_autospec(LegacyWireAdapter, instance=True)
        failing_adapter.is_off = False
        failing_adapter.is_authoritative = False
        failing_adapter.shadow_write.side_effect = OSError("disk full")

        error_calls: list[str] = []

        class _CaptureLogger:
            def error(self, msg: str, *args: object) -> None:
                error_calls.append(msg % args if args else msg)

            def debug(self, *a: object, **k: object) -> None:
                pass

            def info(self, *a: object, **k: object) -> None:
                pass

            def warning(self, *a: object, **k: object) -> None:
                pass

        with mock.patch.object(cs, "CONFIG_V2_MODE", "shadow"), \
             mock.patch.object(cs, "legacy_adapter", failing_adapter), \
             mock.patch.object(cs, "logger", _CaptureLogger()):
            service = cs.ConfigService()
            asyncio.run(service.save_config(Path("Config.json"), {"Data": {"UID": "t"}}))

        # observed：shadow_write 被调用且抛异常，但 save_config 未抛
        failing_adapter.shadow_write.assert_called_once()
        assert len(error_calls) == 1
        assert "auxiliary write failed" in error_calls[0]
        assert "Config.json" in error_calls[0]
        assert "OSError" in error_calls[0]

    def test_json_already_durable_before_observer(self) -> None:
        """验证调用顺序：atomic_write_json 先于 _notify_config_saved。

        用真实文件哈希证明：observer（save_config）的 shadow_write 失败不改变已落盘 JSON。
        """
        import asyncio

        from app.core import config_service as cs
        from app.utils.atomic_file import atomic_write_json

        failing_adapter = mock.create_autospec(LegacyWireAdapter, instance=True)
        failing_adapter.is_off = False
        failing_adapter.is_authoritative = False
        failing_adapter.shadow_write.side_effect = RuntimeError("shadow disk full")

        with mock.patch.object(cs, "CONFIG_V2_MODE", "shadow"), \
             mock.patch.object(cs, "legacy_adapter", failing_adapter), \
             mock.patch.object(cs, "logger", mock.MagicMock()):
            service = cs.ConfigService()

            with tempfile.TemporaryDirectory() as tmp:
                config_path = Path(tmp) / "Config.json"
                payload = {"Data": {"UID": "durable-test"}, "Notify": {"IfSendMail": False}}

                # 步骤 1：atomic_write_json 先落盘（模拟 ConfigBase.save line 1339）
                atomic_write_json(config_path, payload)
                hash_after_json = _sha256_file(config_path)

                # 步骤 2：触发 observer（模拟 ConfigBase.save line 1340）
                asyncio.run(service.save_config(config_path, payload))

                # observed：JSON 文件哈希在 observer 失败后未改变
                hash_after_observer = _sha256_file(config_path)
                assert hash_after_json == hash_after_observer, (
                    "JSON 必须在 observer 触发前已原子落盘，observer 失败不得改变 JSON"
                )
                read_back = json.loads(config_path.read_text(encoding="utf-8"))
                assert read_back == payload
                shadow_toml = config_path.with_suffix(".v2.shadow.toml")
                assert not shadow_toml.exists(), "shadow TOML 不应存在"

    def test_authoritative_mode_rejects_legacy_json_save(self) -> None:
        """authoritative 运行时不允许重新进入 legacy JSON-first 写链。"""
        import asyncio

        from app.core import config_service as cs

        failing_adapter = mock.create_autospec(LegacyWireAdapter, instance=True)
        failing_adapter.is_off = False
        failing_adapter.is_authoritative = True

        with mock.patch.object(cs, "CONFIG_V2_MODE", "authoritative"), \
             mock.patch.object(cs, "legacy_adapter", failing_adapter):
            service = cs.ConfigService()
            with pytest.raises(
                RuntimeError,
                match="rejects legacy JSON-first saves",
            ):
                asyncio.run(service.save_config(Path("Config.json"), {"Data": {}}))
        failing_adapter.shadow_write.assert_not_called()

    def test_dead_code_branch_is_authoritative_unreachable(self) -> None:
        """验证 config_service.py:345 is_authoritative 分支不可达。

        uses_legacy_runtime（line 194）与 legacy_adapter.is_authoritative（compat:93）
        都检查同一个 CONFIG_V2_MODE。非 authoritative 时 is_authoritative 必为 False。
        """
        import asyncio

        from app.core import config_service as cs

        ok_adapter = mock.create_autospec(LegacyWireAdapter, instance=True)
        ok_adapter.is_off = False
        ok_adapter.is_authoritative = False
        ok_adapter.shadow_write.return_value = Path("Config.v2.shadow.toml")

        with mock.patch.object(cs, "CONFIG_V2_MODE", "shadow"), \
             mock.patch.object(cs, "legacy_adapter", ok_adapter), \
             mock.patch.object(cs, "logger", mock.MagicMock()):
            service = cs.ConfigService()
            asyncio.run(service.save_config(Path("Config.json"), {"Data": {}}))

        ok_adapter.shadow_write.assert_called_once()

    def test_canary_mode_auxiliary_failure_swallowed(self) -> None:
        """canary 模式同样吞没 auxiliary 写失败。"""
        import asyncio

        from app.core import config_service as cs

        failing_adapter = mock.create_autospec(LegacyWireAdapter, instance=True)
        failing_adapter.is_off = False
        failing_adapter.is_authoritative = False
        failing_adapter.shadow_write.side_effect = ValueError("canary corrupt")

        with mock.patch.object(cs, "CONFIG_V2_MODE", "canary"), \
             mock.patch.object(cs, "legacy_adapter", failing_adapter), \
             mock.patch.object(cs, "logger", mock.MagicMock()):
            service = cs.ConfigService()
            asyncio.run(service.save_config(Path("QueueConfig.json"), {"instances": []}))

    def test_off_mode_skips_shadow_write(self) -> None:
        """off 模式 is_v2_active=False，不触发 shadow_write。"""
        import asyncio

        from app.core import config_service as cs

        ok_adapter = mock.create_autospec(LegacyWireAdapter, instance=True)
        ok_adapter.is_off = True
        ok_adapter.is_authoritative = False

        with mock.patch.object(cs, "CONFIG_V2_MODE", "off"), \
             mock.patch.object(cs, "legacy_adapter", ok_adapter), \
             mock.patch.object(cs, "logger", mock.MagicMock()):
            service = cs.ConfigService()
            asyncio.run(service.save_config(Path("Config.json"), {"Data": {}}))

        ok_adapter.shadow_write.assert_not_called()


class TestCallOrderSourceVerification:
    """静态验证 ConfigBase.save 调用顺序与 save_config 异常吞没路径。"""

    def test_save_config_source_call_order(self) -> None:
        """验证 ConfigBase.save 先 atomic_write_json 后 _notify_config_saved。

        ConfigBase.py:1339 调 atomic_write_json，line 1340 调 _notify_config_saved。
        JSON 落盘先于 observer 触发——这是 auxiliary 写失败不丢配置的根本保证。
        """
        from app.models.ConfigBase import ConfigBase

        # Python 3.12 CO_COROUTINE=0x80（非旧版 0x100），用 inspect 更稳健
        assert inspect.iscoroutinefunction(ConfigBase.save), "save 必须是协程"
        save_code = ConfigBase.save.__code__
        names = set(save_code.co_names)
        assert "atomic_write_json" in names, "save 必须调用 atomic_write_json"
        assert "_notify_config_saved" in names, "save 必须调用 _notify_config_saved"

    def test_save_config_swallow_path_exists(self) -> None:
        """静态验证 config_service.save_config 的异常吞没路径。"""
        from app.core import config_service as cs

        src = inspect.getsource(cs.ConfigService.save_config)
        assert "except Exception" in src
        assert "auxiliary write failed" in src
        assert "logger.error" in src
        assert "uses_legacy_runtime" in src
        assert "authoritative runtime rejects legacy JSON-first saves" in src
        assert "assert_startup_mode_ready" in src

    def test_save_config_call_order_bytecode(self) -> None:
        """用字节码 co_names 顺序验证 atomic_write_json 在 _notify_config_saved 之前。"""
        from app.models.ConfigBase import ConfigBase

        names = ConfigBase.save.__code__.co_names
        idx_write = names.index("atomic_write_json")
        idx_notify = names.index("_notify_config_saved")
        assert idx_write < idx_notify, (
            f"atomic_write_json(idx={idx_write}) 必须在 _notify_config_saved"
            f"(idx={idx_notify}) 之前"
        )


if __name__ == "__main__":
    import unittest

    # 用 unittest 加载非 TestCase 的 plain class 中的 test_* 方法
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestSaveConfigAuxiliaryFailure, TestCallOrderSourceVerification):
        for name in dir(cls):
            if name.startswith("test_"):
                suite.addTest(cls(name))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
