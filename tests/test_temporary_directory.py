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


@pytest.fixture
def startup_entry(tmp_path):
    source_root = tmp_path / "repo"
    source_root.mkdir()
    entry = source_root / "main.py"
    entry.write_bytes(Path(main.__file__).read_bytes())
    return entry


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


def test_startup_failure_logs_exception_and_exits_nonzero(tmp_path, startup_entry):
    (tmp_path / "temp").write_text("blocks temporary directory creation", "utf-8")

    result = subprocess.run(
        [sys.executable, str(startup_entry)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(main.__file__).parent),
            "PYTHONIOENCODING": "utf-8",
            "AUTO_MAS_ENV": "development",
            "AUTO_MAS_SUPERVISED": "1",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )

    assert "FileExistsError" in (tmp_path / "debug/app.log").read_text("utf-8")
    assert result.returncode != 0, result.stderr


@pytest.mark.parametrize("supervised", [False, True])
def test_startup_sets_temp_before_business_imports(tmp_path, startup_entry, supervised):
    expected_root = tmp_path if supervised else startup_entry.parent
    code = """
import builtins
import os
import runpy
import sys
import tempfile
from pathlib import Path
entry, expected, source = sys.argv[1:]
sys.path.insert(0, source)
original_import = builtins.__import__
def stop_at_business_import(name, *args, **kwargs):
    if name == "app.core":
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
        [
            sys.executable,
            "-c",
            code,
            str(startup_entry),
            str(expected_root),
            str(Path(main.__file__).parent),
        ],
        cwd=tmp_path,
        check=True,
        timeout=15,
        env={
            **os.environ,
            "AUTO_MAS_SUPERVISED": "1" if supervised else "0",
            "AUTO_MAS_ENV": "development",
        },
    )


def test_startup_requests_elevation_before_creating_temp(tmp_path, startup_entry):
    code = """
import ctypes
import runpy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
entry, source = sys.argv[1:]
sys.path.insert(0, source)
import app.utils
app.utils.IS_WINDOWS = True
app.utils.is_admin = lambda: False
temp_root = Path(entry).parent / "temp"
previous_temp = tempfile.gettempdir()
original_mkdir = Path.mkdir
def deny_temp_creation(path, *args, **kwargs):
    if path == temp_root:
        raise PermissionError("temporary directory requires elevation")
    return original_mkdir(path, *args, **kwargs)
Path.mkdir = deny_temp_creation
def request_elevation(*args):
    assert not temp_root.exists()
    assert tempfile.gettempdir() == previous_temp
    raise SystemExit(0)
if not hasattr(ctypes, "windll"):
    ctypes.windll = SimpleNamespace(shell32=SimpleNamespace())
ctypes.windll.shell32.ShellExecuteW = request_elevation
runpy.run_path(entry, run_name="__main__")
raise AssertionError("startup did not request elevation")
"""
    subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(startup_entry),
            str(Path(main.__file__).parent),
        ],
        cwd=tmp_path,
        check=True,
        timeout=15,
        env={
            **os.environ,
            "AUTO_MAS_ENV": "production",
            "AUTO_MAS_SUPERVISED": "0",
            "AUTO_MAS_DEV": "0",
        },
    )
