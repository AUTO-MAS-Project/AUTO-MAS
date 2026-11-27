"""MaaEnd 外部更新恢复必须逐文件匹配当前版本官方包。"""

import threading
import zipfile
from pathlib import Path

from app.task.MaaEnd.tools.script_update import verify_package_tree


def make_install(root: Path, names: set[str]) -> None:
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"content:{name}".encode())


def make_package(archive: Path, names: set[str]) -> None:
    with zipfile.ZipFile(archive, "w") as package:
        for name in names:
            package.writestr(name, f"content:{name}".encode())


def test_package_tree_requires_every_official_file(tmp_path):
    root = tmp_path / "MaaEnd"
    root.mkdir()
    expected = {
        "interface.json",
        "MaaEnd.exe",
        "agent/go-service.exe",
        "resource/pipeline/nodes.json",
        "resource/image/required.png",
    }
    archive = tmp_path / "official.zip"
    make_package(archive, expected)
    make_install(root, expected)
    assert verify_package_tree(root, archive, threading.Event())

    (root / "resource/image/required.png").unlink()
    assert not verify_package_tree(root, archive, threading.Event())


def test_package_tree_rejects_changed_official_file(tmp_path):
    root = tmp_path / "MaaEnd"
    root.mkdir()
    archive = tmp_path / "official.zip"
    make_package(archive, {"interface.json", "resource/image/required.png"})
    make_install(root, {"interface.json", "resource/image/required.png"})
    (root / "resource/image/required.png").write_bytes(b"partial")

    assert not verify_package_tree(root, archive, threading.Event())
