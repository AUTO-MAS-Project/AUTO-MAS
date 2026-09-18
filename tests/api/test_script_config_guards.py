import uuid
from unittest.mock import patch

import pytest

from app.api import scripts
from app.models.config import (
    BetterGIConfig,
    HSRConfig,
    MaaConfig,
    MaaFWConfig,
    OkNteConfig,
)


def _with_script(script_config) -> tuple[str, object]:
    script_id = uuid.uuid4()
    return str(script_id), patch.object(
        scripts.Config, "ScriptConfig", {script_id: script_config}
    )


def test_script_config_guards_return_matched_config() -> None:
    for guard, config in [
        (scripts._hsr_script_config, HSRConfig()),
        (scripts._bettergi_script_config, BetterGIConfig()),
        (scripts._maafw_script_config, MaaFWConfig()),
    ]:
        script_id, patched = _with_script(config)
        with patched:
            assert guard(script_id) is config


def test_oknte_guard_returns_uid_and_config() -> None:
    config = OkNteConfig()
    script_id, patched = _with_script(config)
    with patched:
        script_uid, resolved = scripts._oknte_script_config(script_id)

    assert script_uid == uuid.UUID(script_id)
    assert resolved is config


def test_script_config_guards_reject_cross_type_ids() -> None:
    """错误类型与消息逐字保留：HSR/BetterGI/MFW=TypeError，OK-NTE=ValueError。"""

    script_id, patched = _with_script(MaaConfig())
    with patched:
        with pytest.raises(TypeError, match=r"脚本配置类型错误, 不是 HSR 类型"):
            scripts._hsr_script_config(script_id)
        with pytest.raises(TypeError, match=r"脚本配置类型错误, 不是 BetterGI 类型"):
            scripts._bettergi_script_config(script_id)
        with pytest.raises(TypeError, match=r"脚本配置类型错误, 不是 MFW 类型"):
            scripts._maafw_script_config(script_id)
        with pytest.raises(ValueError, match=r"脚本配置类型错误, 不是 OK-NTE 类型"):
            scripts._oknte_script_config(script_id)
