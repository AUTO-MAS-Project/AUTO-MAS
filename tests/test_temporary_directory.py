"""应用启动后的临时目录、子进程继承及导入隔离契约。"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import main


@pytest.fixture
def configured_temp(tmp_path, monkeypatch):
    # 先缓存原默认值，确认初始化也能覆盖已经使用过 tempfile 的启动环境。
    monkeypatch.setattr(tempfile, "tempdir", tempfile.gettempdir())
    for name in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.setenv(name, os.environ.get(name, ""))
    main.configure_temporary_directory(tmp_path)
    return tmp_path / "temp"


def test_default_temporary_files_use_app_root_and_keep_cleanup(configured_temp):
    assert Path(tempfile.gettempdir()) == configured_temp
    with tempfile.TemporaryDirectory() as directory:
        temporary_directory = Path(directory)
        assert temporary_directory.parent == configured_temp
        with tempfile.NamedTemporaryFile() as temporary:
            assert Path(temporary.name).parent == configured_temp
    assert not temporary_directory.exists()
    assert not Path(temporary.name).exists()

    # 原子写入仍可显式指定目标文件所在目录。
    explicit_root = configured_temp.parent / "config"
    explicit_root.mkdir()
    with tempfile.TemporaryDirectory(dir=explicit_root) as directory:
        assert Path(directory).parent == explicit_root


def test_child_python_inherits_app_temporary_directory(configured_temp):
    code = """
import os
import tempfile
from pathlib import Path
root = Path(os.environ["TEMP"])
assert root == Path(os.environ["TMP"]) == Path(os.environ["TMPDIR"])
assert Path(tempfile.gettempdir()) == root
with tempfile.TemporaryDirectory() as directory:
    assert Path(directory).parent == root
"""
    subprocess.run([sys.executable, "-I", "-c", code], check=True, timeout=15)


def test_importing_main_preserves_caller_temporary_directory(tmp_path):
    code = """
import os
import tempfile
before_environment = {name: os.environ.get(name) for name in ("TEMP", "TMP", "TMPDIR")}
before_directory = tempfile.gettempdir()
import main
assert tempfile.gettempdir() == before_directory
assert {name: os.environ.get(name) for name in before_environment} == before_environment
"""
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        timeout=15,
        env={
            **os.environ,
            "TEMP": str(tmp_path),
            "TMP": str(tmp_path),
            "TMPDIR": str(tmp_path),
        },
    )


@pytest.mark.parametrize("supervised", [False, True])
def test_startup_sets_temp_before_business_imports(tmp_path, supervised):
    source_root = tmp_path / "repo"
    source_root.mkdir()
    entry = source_root / "main.py"
    entry.write_bytes(Path(main.__file__).read_bytes())
    expected_root = tmp_path if supervised else source_root
    code = """
import builtins
import os
import runpy
import sys
import tempfile
from pathlib import Path
entry, expected = sys.argv[1:]
original_import = builtins.__import__
def stop_at_business_import(name, *args, **kwargs):
    if name == "app.utils":
        root = Path(expected)
        assert Path.cwd() == root
        assert Path(tempfile.gettempdir()) == root / "temp"
        assert all(os.environ[key] == str(root / "temp") for key in ("TEMP", "TMP", "TMPDIR"))
        with tempfile.TemporaryDirectory() as directory:
            assert Path(directory).parent == root / "temp"
        raise SystemExit(0)
    return original_import(name, *args, **kwargs)
builtins.__import__ = stop_at_business_import
runpy.run_path(entry, run_name="__main__")
raise AssertionError("startup did not reach the business import")
"""
    subprocess.run(
        [sys.executable, "-c", code, str(entry), str(expected_root)],
        cwd=tmp_path,
        check=True,
        timeout=15,
        env={**os.environ, "AUTO_MAS_SUPERVISED": "1" if supervised else "0"},
    )
