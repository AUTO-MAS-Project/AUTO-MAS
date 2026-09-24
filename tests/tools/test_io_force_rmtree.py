"""通用目录删除原语 `force_rmtree` 的纯逻辑回归测试

脚本配置目录里可能带脚本自己的版本库，git 在 Windows 上会把 `.git/objects/pack/*`
标记为只读；`shutil.rmtree(..., ignore_errors=True)` 删不掉这类文件且静默跳过，
残留文件随后会让 `copytree(..., dirs_exist_ok=True)` 覆盖时抛 `PermissionError`，
配置既没复原、任务也被记成异常。
"""

import os
import stat
from pathlib import Path

from app.utils.io import force_rmtree, replace_dir


def _write_readonly(path: Path) -> None:
    """按 git 的做法把文件标成只读（Windows 上即 FILE_ATTRIBUTE_READONLY）。"""

    path.write_bytes(b"PACK")
    os.chmod(path, stat.S_IREAD)


def test_removes_tree_containing_readonly_files(tmp_path: Path) -> None:
    """目录树里有只读文件时也能整体删掉，不留下残留。"""

    pack_dir = tmp_path / "configs" / ".git" / "objects" / "pack"
    pack_dir.mkdir(parents=True)
    for suffix in ("idx", "pack", "rev"):
        _write_readonly(pack_dir / f"pack-aabb.{suffix}")
    (tmp_path / "configs" / "Basic Options.json").write_text("{}", encoding="utf-8")

    force_rmtree(tmp_path / "configs")

    assert not (tmp_path / "configs").exists()


def test_missing_path_is_a_noop(tmp_path: Path) -> None:
    """路径不存在时不抛异常，重复调用幂等。"""

    force_rmtree(tmp_path / "not-exists")
    force_rmtree(tmp_path / "not-exists")

    assert not (tmp_path / "not-exists").exists()


def test_replace_dir_overwrites_readonly_target(tmp_path: Path) -> None:
    """目标目录带只读文件时也能整体换成源内容，不留 `.tmp` 残留。"""

    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "configs"
    (dst / ".git" / "objects" / "pack").mkdir(parents=True)
    _write_readonly(dst / ".git" / "objects" / "pack" / "pack-aabb.pack")
    (dst / "user.json").write_text('{"a": 999}', encoding="utf-8")
    (src / "user.json").write_text('{"a": 1}', encoding="utf-8")

    replace_dir(src, dst)

    assert (dst / "user.json").read_text(encoding="utf-8") == '{"a": 1}'
    assert not (tmp_path / "configs.tmp").exists()


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
        replace_dir(src, dst)

        # 关键断言：不是「删了一半、备份一个没拷回」
        assert (dst / "user.json").exists()
        assert (dst / "user.json").read_text(encoding="utf-8") == '{"a": 1}'


def test_replace_dir_creates_missing_target(tmp_path: Path) -> None:
    """目标不存在时直接建出来，与源内容一致。"""

    src = tmp_path / "src"
    src.mkdir()
    (src / "user.json").write_text("{}", encoding="utf-8")

    replace_dir(src, tmp_path / "brand-new")

    assert (tmp_path / "brand-new" / "user.json").exists()
