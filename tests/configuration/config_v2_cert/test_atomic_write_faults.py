"""故障注入：atomic_write_text / write_wire_toml 各阶段失败行为认证。

验证在写入管道的不同阶段注入异常时，原文件完整性、备份副本残留
和错误传播语义均符合设计契约。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from app.configuration.v2.wire import write_wire_toml
from app.utils.atomic_file import atomic_write_text


class _FailingStream:
    """模拟 ``os.fdopen`` 返回的流：``write`` 抛出指定异常。"""

    def __init__(self, fd: int, *, fail_on: str = "write") -> None:
        self._fd = fd
        self._fail_on = fail_on

    def write(self, _content: str) -> None:
        raise IOError("injected write failure")

    def flush(self) -> None:
        if self._fail_on == "flush":
            raise IOError("injected flush failure")

    def fileno(self) -> int:
        return self._fd

    def __enter__(self) -> "_FailingStream":
        return self

    def __exit__(self, *_exc: object) -> None:
        pass


class TestAtomicWriteTextFaults(TestCase):
    """``atomic_write_text`` 各阶段故障注入。"""

    # ── 1. 写前 mkdir 失败 ──

    def test_pre_write_mkdir_failure(self) -> None:
        """patch ``Path.mkdir`` 抛 PermissionError，原文件不变。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cfg.toml"
            path.write_text("original", encoding="utf-8")

            with patch(
                "pathlib.Path.mkdir",
                side_effect=PermissionError("denied"),
            ):
                with self.assertRaises(PermissionError):
                    atomic_write_text(path, "new content")

            # 原文件未被修改
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            # 无 .bak 残留（mkdir 在 backup 创建之前）
            self.assertFalse(path.with_name("cfg.toml.bak").exists())

    # ── 2. 临时文件创建失败 ──

    def test_temp_file_creation_failure(self) -> None:
        """patch ``tempfile.mkstemp`` 抛 OSError，原文件不变，.bak 残留。

        backup 在 mkstemp 之前创建（atomic_file.py:26-28），因此 owns_backup=True。
        恢复成功后 re-raise 原异常但不删 .bak（line 60-74 的 else 分支才删）。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cfg.toml"
            path.write_text("original", encoding="utf-8")
            backup_path = path.with_name("cfg.toml.bak")

            with patch(
                "app.utils.atomic_file.tempfile.mkstemp",
                side_effect=OSError("mkstemp failed"),
            ):
                with self.assertRaises(OSError):
                    atomic_write_text(path, "new content")

            # 原文件从 .bak 恢复
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            # .bak 残留（恢复后不删）
            self.assertTrue(backup_path.exists())

    # ── 3. 写内容失败 ──

    def test_write_content_failure(self) -> None:
        """patch ``os.fdopen`` 返回的 stream.write 抛 IOError，temp 清理，原文件恢复。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cfg.toml"
            path.write_text("original", encoding="utf-8")
            backup_path = path.with_name("cfg.toml.bak")

            with patch(
                "app.utils.atomic_file.os.fdopen",
                side_effect=lambda fd, *a, **kw: _FailingStream(fd),
            ):
                with self.assertRaises(IOError):
                    atomic_write_text(path, "new content")

            # 原文件从 .bak 恢复
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            # .bak 残留
            self.assertTrue(backup_path.exists())
            # 无 .tmp 残留
            tmp_files = list(Path(temp_dir).glob("cfg.toml.*.tmp"))
            self.assertEqual(tmp_files, [])

    # ── 4. fsync 失败 ──

    def test_fsync_failure(self) -> None:
        """patch ``os.fsync`` 抛 OSError，原文件从 .bak 恢复。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cfg.toml"
            path.write_text("original", encoding="utf-8")
            backup_path = path.with_name("cfg.toml.bak")

            with patch(
                "app.utils.atomic_file.os.fsync",
                side_effect=OSError("fsync failed"),
            ):
                with self.assertRaises(OSError):
                    atomic_write_text(path, "new content")

            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            self.assertTrue(backup_path.exists())

    # ── 5. replace 失败 → 从 backup 恢复 ──

    def test_replace_failure_restores_from_backup(self) -> None:
        """patch ``os.replace`` 抛 OSError，原文件仍为 original，.bak 存在。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cfg.toml"
            path.write_text("original", encoding="utf-8")
            backup_path = path.with_name("cfg.toml.bak")

            with patch(
                "app.utils.atomic_file.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaises(OSError):
                    atomic_write_text(path, "new")

            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            # 恢复后不删 .bak
            self.assertTrue(backup_path.exists())

    # ── 6. replace 失败且 backup 恢复也失败 ──

    def test_replace_failure_backup_restore_also_fails(self) -> None:
        """``os.replace`` 与恢复 ``shutil.copy2`` 均失败 → RuntimeError，.bak 存在。

        ``shutil.copy2`` 第一次调用（创建 backup）必须执行真实复制以创建
        .bak 文件，第二次调用（恢复）抛异常。若用 ``side_effect=[None, ...]``
        则 mock 不创建文件，``backup_path.exists()`` 为 False，恢复分支不执行。
        """
        real_copy2 = shutil.copy2
        call_count = {"n": 0}

        def copy2_side_effect(src, dst, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return real_copy2(src, dst, *args, **kwargs)
            raise Exception("restore failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cfg.toml"
            path.write_text("original", encoding="utf-8")
            backup_path = path.with_name("cfg.toml.bak")

            with (
                patch(
                    "app.utils.atomic_file.os.replace",
                    side_effect=OSError("replace failed"),
                ),
                patch(
                    "app.utils.atomic_file.shutil.copy2",
                    side_effect=copy2_side_effect,
                ),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    atomic_write_text(path, "new")

            self.assertIn(
                "backup restoration failed",
                str(ctx.exception),
            )
            # .bak 保留（唯一的恢复副本）
            self.assertTrue(backup_path.exists())

    # ── 7. 成功写入后删除 backup ──

    def test_successful_write_removes_backup(self) -> None:
        """正常写入后 .bak 不存在。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cfg.toml"
            path.write_text("original", encoding="utf-8")
            backup_path = path.with_name("cfg.toml.bak")

            atomic_write_text(path, "new content")

            self.assertEqual(path.read_text(encoding="utf-8"), "new content")
            self.assertFalse(backup_path.exists())


class TestWriteWireTomlFaults(TestCase):
    """``write_wire_toml`` 序列化丢失检测。"""

    # ── 8. 序列化丢失抛 ValueError ──

    def test_write_wire_toml_serialization_loss_raises(self) -> None:
        """wire dict 含 tuple 值 → TOML round-trip 后变 list → 抛 ValueError。

        ``_tomlable`` 不转换 tuple，``tomli_w`` 将 tuple 写为 TOML array，
        ``tomllib.loads`` 读回 list，``_first_wire_mismatch`` 检测到
        ``type(tuple) is not type(list)`` → mismatch。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "wire.toml"
            # tuple 通过 _tomlable 原样返回，tomli_w 接受为 array，
            # 但 tomllib.loads 返回 list → 类型不匹配
            payload = {"settings": {"items": (1, 2, 3)}}

            with self.assertRaises(ValueError) as ctx:
                write_wire_toml(path, payload)

            self.assertIn(
                "TOML serialization would lose",
                str(ctx.exception),
            )
            # 文件未被创建（序列化校验在写盘之前）
            self.assertFalse(path.exists())
