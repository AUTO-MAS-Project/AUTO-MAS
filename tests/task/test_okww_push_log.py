"""app/task/Okww/push_log.py 补充翻译 .po 路径的源码相对解析回归测试。

补充 .po 是随源码分发的内置资源（res/i18n/），受监督布局下工作目录与源码
目录分离，路径必须仍按源码位置解析。
"""

from pathlib import Path

import pytest

from app.task.Okww.push_log import _okww_supplement_po


def test_supplement_po_survives_cwd_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    po_path = _okww_supplement_po()

    assert po_path.name == "okww.po"
    assert po_path.is_file()
