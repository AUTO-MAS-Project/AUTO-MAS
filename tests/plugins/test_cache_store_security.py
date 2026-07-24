#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""cache_store.py 的明文限制回归测试。

覆盖：
- register() 时 logger 发出明文落盘警告
- JsonPluginCache 明确声明警告不等于安全机制
- set/get/exists/delete 基础 CRUD 不被警告逻辑破坏
- 磁盘仍为明文，不能将该限制误报为安全闭环
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CACHE_STORE_PATH = _REPO_ROOT / "app" / "plugins" / "cache_store.py"


def _load_cache_store_module():
    """直接按文件路径加载 cache_store 模块，避免触发 app.plugins.__init__ 副作用。"""
    spec = importlib.util.spec_from_file_location("_cache_store_under_test_security", _CACHE_STORE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_cache_store = _load_cache_store_module()
PluginCacheManager = _cache_store.PluginCacheManager
JsonPluginCache = _cache_store.JsonPluginCache


class _CapturingLogger:
    """简易 logger 替身，收集 warning/info 调用。"""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.warnings.append(message)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.infos.append(message)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass


class CacheStoreSecurityWarningTest(unittest.TestCase):
    def test_register_emits_plaintext_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = _CapturingLogger()
            manager = PluginCacheManager(
                plugin_name="test_plugin",
                instance_id="test_instance",
                data_root=Path(temp_dir),
                logger=logger,
            )
            manager.register(cache_name="default", limit=10, limit_mode="count")

            self.assertTrue(
                any("明文" in msg and "敏感数据" in msg for msg in logger.warnings),
                f"expected plaintext warning, got: {logger.warnings}",
            )

    def test_register_warning_contains_instance_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = _CapturingLogger()
            manager = PluginCacheManager(
                plugin_name="my_plugin",
                instance_id="my_instance_001",
                data_root=Path(temp_dir),
                logger=logger,
            )
            manager.register(cache_name="runtime_cache", limit=5, limit_mode="count")

            self.assertTrue(
                any("my_instance_001" in msg and "runtime_cache" in msg for msg in logger.warnings),
                f"warning should contain instance_id and cache name: {logger.warnings}",
            )

    def test_reregister_does_not_emit_duplicate_warning(self) -> None:
        """重复 register 同一 cache 应直接返回已有实例，不再触发 warning。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = _CapturingLogger()
            manager = PluginCacheManager(
                plugin_name="test_plugin",
                instance_id="test_instance",
                data_root=Path(temp_dir),
                logger=logger,
            )
            manager.register(cache_name="default", limit=10, limit_mode="count")
            warning_count_after_first = len(logger.warnings)
            manager.register(cache_name="default", limit=10, limit_mode="count")
            self.assertEqual(len(logger.warnings), warning_count_after_first)

    def test_json_plugin_cache_docstring_contains_security_notice(self) -> None:
        docstring = JsonPluginCache.__doc__ or ""
        self.assertIn("明文", docstring)
        self.assertIn("敏感数据", docstring)
        self.assertIn("不是安全", docstring)


class CacheStoreCrudStillWorksTest(unittest.TestCase):
    """确认安全提示不破坏 CRUD 基础行为。"""

    def test_set_get_exists_delete_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = _CapturingLogger()
            manager = PluginCacheManager(
                plugin_name="test_plugin",
                instance_id="test_instance",
                data_root=Path(temp_dir),
                logger=logger,
            )
            cache = manager.register(cache_name="default", limit=10, limit_mode="count")
            cache.set("key1", {"public": "data"})
            self.assertTrue(cache.exists("key1"))
            self.assertEqual(cache.get("key1"), {"public": "data"})
            self.assertTrue(cache.delete("key1"))
            self.assertFalse(cache.exists("key1"))
            self.assertIsNone(cache.get("key1"))

    def test_plaintext_value_is_written_to_disk(self) -> None:
        """确认缓存值确实以明文写入磁盘（这是当前已知行为，安全提示文档化此限制）。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = _CapturingLogger()
            manager = PluginCacheManager(
                plugin_name="test_plugin",
                instance_id="test_instance",
                data_root=Path(temp_dir),
                logger=logger,
            )
            cache = manager.register(cache_name="default", limit=10, limit_mode="count")
            cache.set("plaintext_key", "plaintext_value")

            cache_file = manager.instance_cache_dir / "default.json"
            raw_text = cache_file.read_text(encoding="utf-8")
            self.assertIn("plaintext_value", raw_text)


if __name__ == "__main__":
    unittest.main()
