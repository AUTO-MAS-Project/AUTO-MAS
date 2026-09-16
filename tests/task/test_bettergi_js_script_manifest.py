"""BetterGI：一个 JS 脚本的 manifest.json 坏掉，不该让整个候选列表拿不到。"""

from pathlib import Path

from app.task.BetterGI.tools.one_dragon import list_js_scripts

_MANIFEST = "manifest.json"


def _make_script(root: Path, folder: str, manifest_text: str) -> Path:
    target = root / "User" / "JsScript" / folder
    target.mkdir(parents=True)
    (target / _MANIFEST).write_text(manifest_text, encoding="utf-8")
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


def test_directory_without_manifest_is_skipped(tmp_path):
    (tmp_path / "User" / "JsScript" / "NoManifest").mkdir(parents=True)
    _make_script(tmp_path, "DDD", '{"name": "D"}')

    assert list_js_scripts(tmp_path) == [("DDD", "D")]


def test_missing_js_dir_returns_empty(tmp_path):
    assert list_js_scripts(tmp_path) == []
