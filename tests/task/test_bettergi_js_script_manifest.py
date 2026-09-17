"""BetterGI：一个 JS 脚本的 manifest.json 坏掉，不该让整个候选列表拿不到。"""

from pathlib import Path

import pytest

from app.task.BetterGI.tools import one_dragon
from app.task.BetterGI.tools.one_dragon import list_js_scripts

_MANIFEST = "manifest.json"


def _make_script(root: Path, folder: str, manifest_text: str) -> Path:
    target = root / "User" / "JsScript" / folder
    target.mkdir(parents=True)
    (target / _MANIFEST).write_text(manifest_text, encoding="utf-8")
    return target


def _make_script_bytes(root: Path, folder: str, manifest_raw: bytes) -> Path:
    target = root / "User" / "JsScript" / folder
    target.mkdir(parents=True)
    (target / _MANIFEST).write_bytes(manifest_raw)
    return target


def test_broken_manifest_falls_back_to_folder_name(tmp_path):
    """尾逗号之类的非严格 JSON 只影响自己：显示名退回目录名，其余脚本照常列出。"""

    _make_script(tmp_path, "AAA-Good", '{"name": "AAA狗粮批发"}')
    # 第 9 行第 5 列的尾逗号正是线上那条事件里的形态
    _make_script(tmp_path, "BBB-Broken", '{\n  "name": "坏脚本",\n}')

    assert list_js_scripts(tmp_path) == [
        ("AAA-Good", "AAA狗粮批发"),
        ("BBB-Broken", "BBB-Broken"),
    ]


def test_manifest_without_name_falls_back_to_folder_name(tmp_path):
    _make_script(tmp_path, "CCC", '{"version": "1.0"}')

    assert list_js_scripts(tmp_path) == [("CCC", "CCC")]


@pytest.mark.parametrize(
    "manifest_raw",
    [
        pytest.param(
            b"\xff\xfe" + '{"name": "BBB坏脚本"}'.encode("utf-8"), id="invalid-bytes"
        ),
        pytest.param(
            '{"name": "BBB坏脚本"}'.encode("utf-16-le"), id="utf16-without-bom"
        ),
    ],
)
def test_manifest_with_invalid_bytes_falls_back_to_folder_name(tmp_path, manifest_raw):
    """manifest 含无效字节（编码不对/被截断）时同样只影响自己。"""

    _make_script(tmp_path, "AAA-Good", '{"name": "AAA狗粮批发"}')
    _make_script_bytes(tmp_path, "BBB-BadBytes", manifest_raw)

    assert list_js_scripts(tmp_path) == [
        ("AAA-Good", "AAA狗粮批发"),
        ("BBB-BadBytes", "BBB-BadBytes"),
    ]


def test_manifest_decode_error_is_swallowed(tmp_path, monkeypatch):
    """``read_file`` 按字节解码失败抛 ``UnicodeDecodeError`` 时不得让候选列表 500。

    当前 ``read_file`` 的解码器带 latin1 兜底，磁盘上的无效字节通常走到
    ``JSONDecodeError``；这里固定住另一条路径，避免上游收紧解码后整列表拿不到。
    """

    _make_script(tmp_path, "AAA-Good", '{"name": "AAA狗粮批发"}')
    _make_script(tmp_path, "BBB-BadBytes", "{}")

    real_read_file = one_dragon.read_file

    def _read_file(path):
        if path.parent.name == "BBB-BadBytes":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        return real_read_file(path)

    monkeypatch.setattr(one_dragon, "read_file", _read_file)

    assert list_js_scripts(tmp_path) == [
        ("AAA-Good", "AAA狗粮批发"),
        ("BBB-BadBytes", "BBB-BadBytes"),
    ]


def test_directory_without_manifest_is_skipped(tmp_path):
    (tmp_path / "User" / "JsScript" / "NoManifest").mkdir(parents=True)
    _make_script(tmp_path, "DDD", '{"name": "D"}')

    assert list_js_scripts(tmp_path) == [("DDD", "D")]


def test_missing_js_dir_returns_empty(tmp_path):
    assert list_js_scripts(tmp_path) == []
