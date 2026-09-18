"""内嵌副本之间按内容共用运行时文件：同样的字节只存一份，且谁也不能往共用文件里写。"""

import json
import os
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.task.MaaFW.tools.core.automas_maafw_project_update import blob_store as bs
from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    apply_package_transaction,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.blob_store import (
    LINK_MIN_BYTES,
    RuntimeBlobStore,
    sha256_file,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.projection import (
    build_projection_plan,
    materialize_projection,
)
from app.task.MaaFW.tools.embedded.embedded_project import (
    embedded_project_dir,
    import_embedded_project,
)

BIG = b"x" * (LINK_MIN_BYTES + 1)
SMALL = b"small"
SCRIPT_A = "3bc42771-7d59-49fb-99b4-8c86202907b0"
SCRIPT_B = "8d1c4f0e-2a6b-4c1d-9e3f-5a7b8c9d0e1f"


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _same_inode(a: Path, b: Path) -> bool:
    return os.stat(a).st_ino == os.stat(b).st_ino


class TestPlace:
    def test_same_content_shares_one_inode(self, tmp_path: Path) -> None:
        store = RuntimeBlobStore(tmp_path / "blobs")
        source = _write(tmp_path / "src/big.dll", BIG)

        first = store.place(source, tmp_path / "a/big.dll")
        second = store.place(source, tmp_path / "b/big.dll")

        assert (first.action, second.action) == ("linked", "linked")
        assert _same_inode(tmp_path / "a/big.dll", tmp_path / "b/big.dll")
        blob = store.blob_path(sha256_file(source))
        assert blob.is_file() and os.stat(blob).st_nlink == 3
        assert (tmp_path / "a/big.dll").read_bytes() == BIG

    def test_small_files_are_plain_copies(self, tmp_path: Path) -> None:
        store = RuntimeBlobStore(tmp_path / "blobs")
        source = _write(tmp_path / "src/x.lock", SMALL)

        result = store.place(source, tmp_path / "a/x.lock")

        assert result.action == "copied"
        assert not (tmp_path / "blobs").exists()

    def test_unchanged_destination_is_not_touched(self, tmp_path: Path) -> None:
        # 内容没变就别碰：那个文件可能正被别的项目映射着。
        store = RuntimeBlobStore(tmp_path / "blobs")
        source = _write(tmp_path / "src/big.dll", BIG)
        store.place(source, tmp_path / "a/big.dll")
        before = os.stat(tmp_path / "a/big.dll").st_ino

        with patch.object(bs.os, "link", side_effect=AssertionError("must not relink")):
            result = store.place(source, tmp_path / "a/big.dll")

        assert result.action == "unchanged"
        assert os.stat(tmp_path / "a/big.dll").st_ino == before

    def test_changed_content_never_writes_through_the_link(
        self, tmp_path: Path
    ) -> None:
        store = RuntimeBlobStore(tmp_path / "blobs")
        old = _write(tmp_path / "src/v1.dll", BIG)
        new = _write(tmp_path / "src/v2.dll", b"y" * (LINK_MIN_BYTES + 1))
        store.place(old, tmp_path / "a/big.dll")
        store.place(old, tmp_path / "b/big.dll")

        store.place(new, tmp_path / "a/big.dll")

        assert (tmp_path / "a/big.dll").read_bytes() == new.read_bytes()
        # B 仍是旧内容：A 换掉的是自己的目录项，不是共用的字节。
        assert (tmp_path / "b/big.dll").read_bytes() == BIG

    def test_link_failure_falls_back_to_copy(self, tmp_path: Path) -> None:
        store = RuntimeBlobStore(tmp_path / "blobs")
        source = _write(tmp_path / "src/big.dll", BIG)

        with patch.object(bs.os, "link", side_effect=OSError("no hard links here")):
            result = store.place(source, tmp_path / "a/big.dll")

        assert result.action == "copied"
        assert (tmp_path / "a/big.dll").read_bytes() == BIG

    def test_corrupted_blob_is_quarantined_not_reused(self, tmp_path: Path) -> None:
        store = RuntimeBlobStore(tmp_path / "blobs")
        source = _write(tmp_path / "src/big.dll", BIG)
        store.place(source, tmp_path / "a/big.dll")
        blob = store.blob_path(sha256_file(source))
        # 有人往共用文件里原地写了（A 也跟着变了——这就是不能原地写的原因）。
        with blob.open("r+b") as handle:
            handle.write(b"Z")

        result = store.place(source, tmp_path / "b/big.dll")

        assert result.action == "linked"
        assert (tmp_path / "b/big.dll").read_bytes() == BIG
        assert not _same_inode(tmp_path / "a/big.dll", tmp_path / "b/big.dll")
        assert any(".corrupt-" in p.name for p in blob.parent.iterdir())


class TestGarbage:
    def test_only_unreferenced_blobs_are_removed(self, tmp_path: Path) -> None:
        store = RuntimeBlobStore(tmp_path / "blobs")
        keep = _write(tmp_path / "src/keep.dll", BIG)
        drop = _write(tmp_path / "src/drop.dll", b"d" * (LINK_MIN_BYTES + 1))
        store.place(keep, tmp_path / "a/keep.dll")
        store.place(drop, tmp_path / "a/drop.dll")
        (tmp_path / "a/drop.dll").unlink()  # 副本删了，blob 就没人引用了
        _write(store.root / "zz" / "deadbeef.tmp-1234", b"half")

        report = store.collect_garbage()

        assert report.removed_blobs == 1
        assert report.removed_bytes == LINK_MIN_BYTES + 1
        assert report.removed_temps == 1
        assert store.blob_path(sha256_file(keep)).is_file()
        assert not store.blob_path(sha256_file(drop)).exists()


def _interface(agent: dict | None = None) -> str:
    payload = {
        "name": "Demo",
        "version": "v1.0.0",
        "resource": [{"name": "x", "path": "./resource/base"}],
        "agent": agent
        or {
            "child_exec": "./python/python.exe",
            "child_args": ["-u", "./agent/main.py"],
        },
    }
    return json.dumps(payload)


def _project(root: Path, *, dll: bytes = BIG, version: str = "v1.0.0") -> Path:
    _write(
        root / "interface.json", _interface().replace("v1.0.0", version).encode("utf-8")
    )
    _write(root / "resource/base/a.json", b"{}")
    _write(root / "agent/main.py", b"print('hi')")
    _write(root / "python/python.exe", b"exe")
    _write(root / "python/python313.dll", dll)
    _write(root / "python/Lib/site-packages/numpy/big.pyd", b"n" * (LINK_MIN_BYTES + 5))
    _write(root / "python/.marker", SMALL)
    _write(root / "maafw/MaaFramework.dll", b"m" * (LINK_MIN_BYTES + 9))
    _write(root / "resource/base/image.png", b"p" * (LINK_MIN_BYTES + 3))
    return root


class TestProjectionUsesTheStore:
    def test_two_copies_of_the_same_runtime_share_inodes(self, tmp_path: Path) -> None:
        source = _project(tmp_path / "src")
        a = import_embedded_project(SCRIPT_A, source, base=tmp_path)
        b = import_embedded_project(SCRIPT_B, source, base=tmp_path)
        copy_a = embedded_project_dir(SCRIPT_A, tmp_path)
        copy_b = embedded_project_dir(SCRIPT_B, tmp_path)

        for relative in (
            "python/python313.dll",
            "python/Lib/site-packages/numpy/big.pyd",
            "maafw/MaaFramework.dll",
        ):
            assert _same_inode(copy_a / relative, copy_b / relative), relative
        # 资源不共用（agent 会热更新它们），小文件也不共用。
        assert not _same_inode(
            copy_a / "resource/base/image.png", copy_b / "resource/base/image.png"
        )
        assert not _same_inode(copy_a / "python/.marker", copy_b / "python/.marker")
        assert a["report"]["sharedFiles"] == 3
        assert b["report"]["sharedBytes"] == a["report"]["sharedBytes"] > 0
        assert (tmp_path / "data" / "maafw_blobs").is_dir()

    def test_materialize_without_a_store_is_plain_copies(self, tmp_path: Path) -> None:
        source = _project(tmp_path / "src")
        stats = materialize_projection(build_projection_plan(source), tmp_path / "out")

        assert stats == {"sharedFiles": 0, "sharedBytes": 0}
        assert not (tmp_path / "data").exists()


class TestUpdateLandingUsesTheStore:
    def _package(self, tmp_path: Path, name: str, dll: bytes, version: str) -> Path:
        package = tmp_path / f"{name}.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("interface.json", _interface().replace("v1.0.0", version))
            archive.writestr("resource/base/a.json", '{"v": 2}')
            archive.writestr("agent/main.py", "print('hi')")
            archive.writestr("python/python.exe", "exe")
            archive.writestr("python/python313.dll", dll)
            archive.writestr("maafw/MaaFramework.dll", "m" * (LINK_MIN_BYTES + 9))
        return package

    def test_landing_shares_unchanged_runtime_and_replaces_changed_files_safely(
        self, tmp_path: Path
    ) -> None:
        source = _project(tmp_path / "src")
        import_embedded_project(SCRIPT_A, source, base=tmp_path)
        import_embedded_project(SCRIPT_B, source, base=tmp_path)
        copy_a = embedded_project_dir(SCRIPT_A, tmp_path)
        copy_b = embedded_project_dir(SCRIPT_B, tmp_path)
        new_dll = b"v2" * (LINK_MIN_BYTES // 2 + 4)
        package = self._package(tmp_path, "v1.1.0", new_dll, "v1.1.0")

        result = apply_package_transaction(
            copy_a,
            package,
            operation_root=tmp_path / "data" / "maafw_update_operations",
            projection=True,
        )

        assert result.get("applied") is not False
        assert (copy_a / "python/python313.dll").read_bytes() == new_dll
        # B 没更新：它的旧库原样，A 换的是自己的目录项。
        assert (copy_b / "python/python313.dll").read_bytes() == BIG
        # 没变的原生库仍是同一个 inode，也没有被重新链接。
        assert _same_inode(
            copy_a / "maafw/MaaFramework.dll", copy_b / "maafw/MaaFramework.dll"
        )
        # 新库进了共用库，第二个项目更新到同版本时会共用它。
        store = RuntimeBlobStore(tmp_path / "data" / "maafw_blobs")
        assert store.blob_path(sha256_file(copy_a / "python/python313.dll")).is_file()

    def test_rollback_restores_without_writing_through_shared_links(
        self, tmp_path: Path
    ) -> None:
        source = _project(tmp_path / "src")
        import_embedded_project(SCRIPT_A, source, base=tmp_path)
        import_embedded_project(SCRIPT_B, source, base=tmp_path)
        copy_a = embedded_project_dir(SCRIPT_A, tmp_path)
        copy_b = embedded_project_dir(SCRIPT_B, tmp_path)
        new_dll = b"v2" * (LINK_MIN_BYTES // 2 + 4)
        package = self._package(tmp_path, "v1.1.0", new_dll, "v1.1.0")

        def reject(_root: Path) -> bool:
            return False

        with pytest.raises(Exception):
            apply_package_transaction(
                copy_a,
                package,
                operation_root=tmp_path / "data" / "maafw_update_operations",
                projection=True,
                post_validate=reject,
            )

        # 回滚后 A 回到旧内容，B 全程不受影响；两边仍可以共用同一份旧库。
        assert (copy_a / "python/python313.dll").read_bytes() == BIG
        assert (copy_b / "python/python313.dll").read_bytes() == BIG
        assert (copy_a / "interface.json").read_text(encoding="utf-8") == _interface()
