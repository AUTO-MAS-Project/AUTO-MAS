"""Windows 配置恢复遇到占用文件时，不能留下半删的用户目录。"""

import sys
from pathlib import Path

import pytest

from app.utils import io as _utils_io


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 文件占用语义")
def test_replace_dir_restores_when_target_still_held(tmp_path: Path) -> None:
    """目标有文件被占用时不再停在半删状态：删掉的部分会被就地补回。"""

    src = tmp_path / "src"
    dst = tmp_path / "configs"
    src.mkdir()
    (src / "user.json").write_text('{"a": 1}', encoding="utf-8")
    dst.mkdir()
    (dst / "user.json").write_text('{"a": 999}', encoding="utf-8")
    (dst / "held.bin").write_bytes(b"x" * 64)

    with (dst / "held.bin").open("rb"):
        _utils_io.replace_dir(src, dst)

        # 关键断言：不是「删了一半、备份一个没拷回」
        assert (dst / "user.json").exists()
        assert (dst / "user.json").read_text(encoding="utf-8") == '{"a": 1}'
