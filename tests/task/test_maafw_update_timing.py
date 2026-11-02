"""MaaFW、M9A、MSS 共享运行前更新时机，保留显式关闭。"""

from types import SimpleNamespace

import pytest

from app.models.config import M9AConfig, MaaFWConfig, MSSConfig
from app.task.MaaFW.tools.embedded.update_credentials import resolve_auto_update_mode


@pytest.mark.parametrize("config_type", [MaaFWConfig, M9AConfig, MSSConfig])
@pytest.mark.parametrize(
    ("stored", "expected"),
    [("Off", "Off"), ("BeforeRun", "BeforeRun"), ("AfterRun", "BeforeRun")],
)
def test_flavors_update_before_run(config_type, stored, expected):
    config = config_type(Update={"AutoUpdateMode": stored})
    assert resolve_auto_update_mode(config) == expected


def test_missing_update_mode_defaults_to_before_run():
    assert resolve_auto_update_mode(SimpleNamespace()) == "BeforeRun"
