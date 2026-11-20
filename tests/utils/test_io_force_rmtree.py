"""Windows 配置恢复遇到占用文件时必须报告失败。"""

import sys
from pathlib import Path

import pytest

from app.utils import io as _utils_io


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 文件占用语义")
def test_replace_dir_rejects_target_still_held(tmp_path: Path) -> None:
    """目标未清空时不能复制新配置并假装替换成功。"""

    src = tmp_path / "src"
    dst = tmp_path / "configs"
    src.mkdir()
    (src / "user.json").write_text('{"a": 1}', encoding="utf-8")
    dst.mkdir()
    (dst / "user.json").write_text('{"a": 999}', encoding="utf-8")
    (dst / "held.bin").write_bytes(b"x" * 64)

    with (dst / "held.bin").open("rb"):
        with pytest.raises(OSError, match="目标目录未能清空"):
            _utils_io.replace_dir(src, dst)

    assert (dst / "held.bin").exists()
    assert not (dst / "user.json").exists()
