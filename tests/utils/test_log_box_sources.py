"""日志文件身份的跨平台回归，不依赖宿主文件系统的 ctime 语义。"""

from types import SimpleNamespace

import pytest

from app.utils.common.log import sources as sources


@pytest.mark.parametrize("platform", ["posix", "nt"])
def test_append_rotation_and_truncation_keep_exact_offsets(
    tmp_path, monkeypatch, platform
):
    path = tmp_path / "run.log"
    path.write_text("历史内容\n", encoding="utf-8", newline="\n")
    original_stat = type(path).stat
    state = {"ctime_delta": 0}

    def stat(current, *args, **kwargs):
        result = original_stat(current, *args, **kwargs)
        if current != path:
            return result
        return SimpleNamespace(
            st_ino=result.st_ino,
            st_dev=result.st_dev,
            st_mode=result.st_mode,
            st_size=result.st_size,
            st_ctime_ns=100 + state["ctime_delta"],
        )

    monkeypatch.setattr(type(path), "stat", stat)
    monkeypatch.setattr(sources, "os", SimpleNamespace(name=platform))
    source = sources.LogSource(path)
    source.open()
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("新节点\n")
    if platform == "posix":
        state["ctime_delta"] = 1000000000  # POSIX 追加会更新 ctime。
    assert source.read_new() == ["新节点"]
    assert source.read_new() == []

    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("轮转前尾部\n")
    path.rename(tmp_path / "run.log.bak")
    path.write_text("新文件节点\n", encoding="utf-8", newline="\n")
    assert source.read_new() == ["轮转前尾部", "新文件节点"]
    assert source.read_new() == []

    path.write_text("短\n", encoding="utf-8", newline="\n")
    assert source.read_new() == ["短"]
    assert source.read_new() == []


def test_windows_creation_time_still_detects_replacement_without_inode(monkeypatch):
    monkeypatch.setattr(sources, "os", SimpleNamespace(name="nt"))
    old = SimpleNamespace(st_ino=0, st_ctime_ns=10, st_dev=0)
    new = SimpleNamespace(st_ino=0, st_ctime_ns=20, st_dev=0)
    assert sources._file_identity(old) != sources._file_identity(new)
