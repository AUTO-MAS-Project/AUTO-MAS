"""候选列表 / 报告里给人看的项目名：label → name，i18n 键翻不出来时不能把「$project.label」当名字。"""

import json
from pathlib import Path

from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    load_interface_model_cached,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.preview import (
    interface_display_name,
)


def _interface(root: Path, **extra: object) -> Path:
    payload = {
        "interface_version": 2,
        "name": "FOS",
        "version": "v3.10.36",
        "resource": [{"name": "x", "path": ["./resource/base"]}],
        **extra,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "interface.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return root


def test_label_wins_and_the_synthesized_title_is_not_used(tmp_path: Path) -> None:
    root = _interface(tmp_path / "a", label="法奥斯之梦")
    interface = load_interface_model_cached(root, force_reload=True)
    # 模型把 title 拼成「label 版本」，显示名不能带版本，版本另给。
    assert interface.title == "法奥斯之梦 v3.10.36"
    assert interface_display_name(root, interface) == "法奥斯之梦"


def test_untranslatable_i18n_key_falls_back_to_name(tmp_path: Path) -> None:
    root = _interface(tmp_path / "b", label="$project.label")
    interface = load_interface_model_cached(root, force_reload=True)
    assert interface_display_name(root, interface) == "FOS"


def test_i18n_key_is_translated_through_the_project_language_file(
    tmp_path: Path,
) -> None:
    root = _interface(
        tmp_path / "c",
        label="$project.label",
        languages={"zh_cn": "./i18n/zh_cn.json"},
    )
    (root / "i18n").mkdir()
    (root / "i18n" / "zh_cn.json").write_text(
        json.dumps({"project": {"label": "法奥斯之梦"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    interface = load_interface_model_cached(root, force_reload=True)
    assert interface_display_name(root, interface) == "法奥斯之梦"
