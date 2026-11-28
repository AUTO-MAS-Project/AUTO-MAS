"""全局设置的桌面分身两份清单：经设置接口读写，内部迁移标记不进接口。"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.utils import io as config_io
from tests.config_support import activate_config

pytestmark = pytest.mark.asyncio


async def test_targets_round_trip_through_setting_api(monkeypatch, tmp_path):
    from app.api.setting import SettingUpdateIn, get_scripts, update_script
    from app.core import Config
    from app.models.config import GlobalConfig

    path = tmp_path / "setting.yaml"
    setting = await activate_config(GlobalConfig.build(), path)
    monkeypatch.setattr(Config, "setting", setting)
    queue, script = str(uuid4()), str(uuid4())

    result = await update_script(
        SettingUpdateIn.model_validate(
            {
                "data": {
                    "DesktopSession": {
                        "Targets": [script.upper(), script],
                        "StartOnOpen": [queue.upper(), script, queue],
                        # 迁移标记只由后端写，接口传进来也不生效。
                        "LegacyMigrated": True,
                    }
                }
            }
        )
    )
    assert result.code == 200, result.message
    await activate_config(setting, path)
    assert config_io.read_dict_file(path)["DesktopSession"] == {
        "Targets": [script],
        "StartOnOpen": [queue, script],
        "LegacyMigrated": False,
    }

    got = await get_scripts()
    assert got.data.model_dump(exclude_unset=True)["DesktopSession"] == {
        "Targets": [script],
        "StartOnOpen": [queue, script],
    }


@pytest.mark.parametrize("field", ["Targets", "StartOnOpen"])
@pytest.mark.parametrize(
    "targets",
    [[str(uuid4()) for _ in range(101)], ["not-a-uuid"]],
    ids=["over-limit", "not-uuid"],
)
async def test_invalid_targets_are_rejected(field, targets):
    from app.api.setting import SettingUpdateIn

    with pytest.raises(ValidationError):
        SettingUpdateIn.model_validate({"data": {"DesktopSession": {field: targets}}})
