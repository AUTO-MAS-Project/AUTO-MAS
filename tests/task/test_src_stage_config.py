"""SRC 已有关卡选择经升级、保存和重新加载后保持原值。"""

import pytest

from app.config import config_manager
from app.config.wire import ConfigInput, ConfigPayload
from app.core.config.upgrade import convert_legacy
from app.models.config import SrcUserConfig
from app.utils import io as _utils_io
from tests.config_support import activate_config

SECRET_ACTOR = "Cavern_of_Corrosion_Path_of_the_Secret_Actor"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True], ids=["saved-yaml", "upgraded-json"])
async def test_existing_secret_actor_survives_save_and_reload(tmp_path, legacy):
    payload = {
        "Info": {"Base": "native", "IfQuickConfig": False},
        "Stage": {"Channel": "Relic", "Relic": SECRET_ACTOR, "FuelReserve": 7},
    }
    if legacy:
        payload["Info"] = {"Mode": "直控", "IfQuickConfig": False}
        payload = convert_legacy(payload, SrcUserConfig.build())

    path = tmp_path / "src-user.yaml"
    _utils_io.write_file(path, payload)
    user = SrcUserConfig.build(file=path)
    try:
        await user.activate(fast_init=True)
        assert user.Stage.Relic == SECRET_ACTOR
        response = ConfigPayload[SrcUserConfig].model_validate(user.model_dump())
        assert response.Stage.Relic == SECRET_ACTOR

        # 完整回传及只改其他字段的部分保存都不能清掉已有的关卡选择。
        for patch in (
            response.model_dump(exclude_unset=True),
            {"Info": {"Notes": "保留关卡"}},
        ):
            request = ConfigInput[SrcUserConfig].model_validate(patch)
            await user.update(
                SrcUserConfig.model_validate(request.model_dump(exclude_unset=True))
            )
            await config_manager.flush()
            assert _utils_io.read_dict_file(path)["Stage"]["Relic"] == SECRET_ACTOR
    finally:
        config_manager.unregister_root(user)

    reloaded = await activate_config(SrcUserConfig.build(), path)
    assert reloaded.Stage.Relic == SECRET_ACTOR
    assert reloaded.Stage.FuelReserve == 7
    assert reloaded.Info.Notes == "保留关卡"
    assert reloaded.Info.Base == "native"
    assert reloaded.Info.IfQuickConfig is False
