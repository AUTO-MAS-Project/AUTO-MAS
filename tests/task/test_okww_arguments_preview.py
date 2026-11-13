"""启动参数预览复用真实任务参数构造规则。"""

import uuid
from types import SimpleNamespace

import pytest

from app.models.config.script import OkwwConfig
from app.task.Okww import api_service
from app.task.Okww.tools.arguments import build_custom_arguments


@pytest.mark.parametrize("mode", ["MAS", "OKWW", "OKWW_SINGLE"])
def test_preview_respects_native_switch_mode(monkeypatch, mode):
    sid = uuid.uuid4()
    config = OkwwConfig.model_validate({"Game": {"AccountSwitchMethod": mode}})
    monkeypatch.setattr(
        api_service, "Config", SimpleNamespace(ScriptConfig={sid: config})
    )
    arguments = '-t "Other Task" -h'
    actual, native = api_service.resolve_startup_arguments(
        str(sid), custom=True, arguments=arguments
    )
    assert actual == build_custom_arguments(arguments)
    assert native == (mode != "MAS")
