"""正式版的切号开关只迁移一次，不能覆盖公测版保存的切号方式。"""

import pytest

from app.config import config_manager
from app.models.config import OkwwConfig
from app.utils import io
from tests.config_support import activate_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("old_game", "expected"),
    [
        ({"AccountSwitch": False}, "NONE"),
        ({"AccountSwitch": True}, "MAS"),
        ({"AccountSwitch": False, "AccountSwitchMethod": "OKWW_SINGLE"}, "OKWW_SINGLE"),
    ],
)
async def test_account_switch_survives_upgrade_and_restart(
    tmp_path, old_game, expected
):
    path = tmp_path / "okww.yaml"
    io.write_file(path, {"Game": old_game})
    config = await activate_config(OkwwConfig.build(file=path))
    assert config.Game.AccountSwitchMethod == expected

    config.Game.AccountSwitchMethod = "OKWW"
    await config.commit()
    await config_manager.flush()
    saved = io.read_dict_file(path)["Game"]
    assert saved["AccountSwitchMethod"] == "OKWW" and "AccountSwitch" not in saved
    config_manager.unregister_root(config)
    reloaded = await activate_config(OkwwConfig.build(file=path))
    assert reloaded.Game.AccountSwitchMethod == "OKWW"
