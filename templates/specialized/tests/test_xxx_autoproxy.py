"""Xxx AutoProxy 最小回归测试。

复制到 ``tests/task/test_xxx_autoproxy.py`` 后，将 import 路径和夹具替换为真实
专项配置。测试不启动外部脚本，只固定参数解析、日志文件名前缀和配置恢复边界。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from app.task.Xxx.AutoProxy import (
        AutoProxyTask,
        _format_to_prefix_regex,
        _split_script_arguments,
    )
except ImportError:
    # 模板尚未复制进 app/task 时允许仓库全量 pytest 收集并跳过本文件。
    AutoProxyTask = None


class _ScriptConfigStub:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def get(self, section: str, key: str):
        if (section, key) == ("Script", "ConfigPathMode"):
            return self.mode
        raise AssertionError(f"unexpected config lookup: {section}.{key}")


def _build_task(root: Path, mode: str) -> AutoProxyTask:
    task = object.__new__(AutoProxyTask)
    task.script_config = _ScriptConfigStub(mode)
    task.script_config_path = root / "script-config"
    task.temp_path = root / "temp"
    task.external_config_exists = False
    task.external_config_snapshot_ready = False
    return task


@unittest.skipUnless(AutoProxyTask is not None, "请先将模板复制并注册为 Xxx 专项")
class XxxAutoProxyTest(unittest.TestCase):
    def test_split_script_arguments_keeps_executable_and_arguments(self) -> None:
        paths, arguments = _split_script_arguments(
            "runner.exe%--headless --task 1|config.exe%--settings",
            Path("C:/Xxx"),
        )
        self.assertEqual(paths[0], Path("C:/Xxx/runner.exe").resolve())
        self.assertEqual(arguments[0], ["--headless", "--task", "1"])
        self.assertEqual(arguments[1], ["--settings"])

    def test_log_prefix_pattern_supports_strptime_directives(self) -> None:
        pattern = _format_to_prefix_regex("%Y-%m-%d")
        self.assertIsNotNone(pattern.match("2026-08-21-1.log"))
        self.assertIsNone(pattern.match("not-a-date.log"))

    def test_folder_snapshot_restores_original_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task = _build_task(root, "Folder")
            task.script_config_path.mkdir()
            (task.script_config_path / "keep.json").write_text("direct", encoding="utf-8")

            task._snapshot_external_config()
            (task.script_config_path / "keep.json").unlink()
            (task.script_config_path / "managed.json").write_text("managed", encoding="utf-8")
            task._restore_external_config()

            self.assertEqual(
                (task.script_config_path / "keep.json").read_text(encoding="utf-8"),
                "direct",
            )
            self.assertFalse((task.script_config_path / "managed.json").exists())

    def test_file_snapshot_restores_original_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task = _build_task(root, "File")
            task.script_config_path.write_text("direct", encoding="utf-8")

            task._snapshot_external_config()
            task.script_config_path.write_text("managed", encoding="utf-8")
            task._restore_external_config()

            self.assertEqual(task.script_config_path.read_text(encoding="utf-8"), "direct")

    def test_missing_config_remains_missing_after_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task = _build_task(root, "Folder")
            task._snapshot_external_config()
            task.script_config_path.mkdir()
            (task.script_config_path / "managed.json").write_text("managed", encoding="utf-8")

            task._restore_external_config()

            self.assertFalse(task.script_config_path.exists())


if __name__ == "__main__":
    unittest.main()
