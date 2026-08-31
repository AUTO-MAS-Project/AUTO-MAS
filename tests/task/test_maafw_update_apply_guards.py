import unittest

import app.core  # noqa: F401

from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    UpdateApplyError,
    _is_bytecode_artifact,
    _verify_owned_files,
)


class BytecodeArtifactTest(unittest.TestCase):
    """字节码产物判定：决定哪些文件不纳入受管文件校验与 manifest 登记。"""

    def test_recognises_bytecode(self) -> None:
        for relative in (
            "agent/main.pyc",
            "agent/__pycache__/main.cpython-312.pyc",
            "__pycache__/x.pyc",
            "a\\b\\__pycache__\\c.pyc",
        ):
            with self.subTest(relative=relative):
                self.assertTrue(_is_bytecode_artifact(relative))

    def test_leaves_normal_files_alone(self) -> None:
        for relative in (
            "interface.json",
            "agent/main.py",
            "resource/base/pipeline/x.json",
            "docs/pycharm.md",
            "tools/mypycache.txt",
        ):
            with self.subTest(relative=relative):
                self.assertFalse(_is_bytecode_artifact(relative))


class VerifyOwnedFilesTest(unittest.TestCase):
    """受管文件校验对字节码必须免疫。

    全量包自带的 .pyc 解压后首次 import 即被解释器重写，若纳入校验，装过一次并
    跑过一次之后就会被判「受管文件被本地改写」而**永久拒绝后续所有更新**。
    """

    def setUp(self) -> None:
        self._temp = self.enterContext(_temp_dir())

    def test_modified_bytecode_does_not_block_update(self) -> None:
        root = self._temp
        (root / "__pycache__").mkdir(parents=True)
        target = root / "__pycache__" / "main.cpython-312.pyc"
        target.write_bytes(b"rewritten by interpreter")
        manifest = {"files": {"__pycache__/main.cpython-312.pyc": "0" * 64}}
        # 不抛异常即为通过。
        _verify_owned_files(root, manifest)

    def test_modified_source_still_blocks_update(self) -> None:
        root = self._temp
        target = root / "interface.json"
        target.write_text("locally edited", encoding="utf-8")
        manifest = {"files": {"interface.json": "0" * 64}}
        with self.assertRaises(UpdateApplyError):
            _verify_owned_files(root, manifest)


def _temp_dir():
    import tempfile
    from contextlib import contextmanager
    from pathlib import Path

    @contextmanager
    def _ctx():
        with tempfile.TemporaryDirectory() as name:
            yield Path(name)

    return _ctx()


if __name__ == "__main__":
    unittest.main()
