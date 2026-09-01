"""automas_maafw_runner/run_plan.py 客户端版本号读取的源码相对解析回归测试。

version.json 是随源码分发的内置资源（res/version.json），受监督布局下工作
目录与源码目录分离，路径必须仍按源码位置解析；否则会静默命中 except 分支
返回空字符串，而不是报错，回归很容易被忽略。
"""

import json
from pathlib import Path

import pytest

from app.task.MaaFW.tools.core.automas_maafw_runner.run_plan import (
    _load_client_version,
)
from app.utils.paths import SOURCE_ROOT


def test_load_client_version_survives_cwd_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    expected = json.loads(
        (SOURCE_ROOT / "res" / "version.json").read_text(encoding="utf-8")
    )["version"]

    version = _load_client_version()

    assert version, "应读到真实版本号，而不是落入 except 分支返回空字符串"
    assert version == expected
