"""打开配置目录应跟随当前配置来源，不触碰配置内容。"""

from uuid import uuid4

import pytest

from app.core.config.manager import AppConfig
from app.models.config import GeneralUserConfig, MaaConfig, MaaUserConfig
from app.models.script_contracts import ScriptConfigHandler
from app.task.MAA.registration import build_config_handler


async def _host(
    tmp_path, entry_type=MaaConfig, *, base="shared", quick=True, install=None
):
    script = entry_type.build(
        payload={"Info": {"Path": str(install)}} if install is not None else None
    )
    await script.activate()
    user_type = MaaUserConfig if entry_type is MaaConfig else GeneralUserConfig
    uid = script.UserData.add(
        user_type, payload={"Info": {"Base": base, "IfQuickConfig": quick}}
    )
    await script.UserData.commit()
    host = AppConfig.__new__(AppConfig)
    host.data_path = tmp_path / "data"
    host.ScriptConfig = {script.uid: script}
    host._script_config_handlers = {}
    host.bind_script_config_handler(
        entry_type,
        build_config_handler() if entry_type is MaaConfig else ScriptConfigHandler(),
    )
    return host, str(script.uid), str(uid)


@pytest.mark.asyncio
@pytest.mark.parametrize("base", ["shared", "independent", "native"])
@pytest.mark.parametrize("quick", [True, False])
async def test_folder_follows_maa_source_without_changing_config(tmp_path, base, quick):
    install = tmp_path / "MAA"
    install.mkdir()
    host, sid, uid = await _host(tmp_path, base=base, quick=quick, install=install)
    expected = (
        install / "config"
        if base == "native"
        else host.data_path
        / sid
        / ("Default" if base == "shared" else uid)
        / "ConfigFile"
    )
    expected.mkdir(parents=True)
    config_file = expected / "gui.new.json"
    content = b'{"Update":{"VersionType":"Beta"}}'
    config_file.write_bytes(content)

    assert await host.get_user_config_dir(sid, uid) == expected
    assert config_file.read_bytes() == content
    if base != "independent":
        assert not (host.data_path / sid / uid).exists()


@pytest.mark.asyncio
async def test_missing_managed_folder_is_created_without_seeding_config(tmp_path):
    host, sid, uid = await _host(tmp_path)

    folder = await host.get_user_config_dir(sid, uid)

    assert folder == host.data_path / sid / "Default" / "ConfigFile"
    assert folder.is_dir()
    assert list(folder.iterdir()) == []


@pytest.mark.asyncio
async def test_native_source_requires_configured_installation(tmp_path):
    host, sid, uid = await _host(tmp_path, base="native")

    with pytest.raises(ValueError):
        await host.get_user_config_dir(sid, uid)
    assert not host.data_path.exists()


@pytest.mark.asyncio
async def test_unknown_user_does_not_create_directory(tmp_path):
    host, sid, _ = await _host(tmp_path)

    with pytest.raises(ValueError):
        await host.get_user_config_dir(sid, str(uuid4()))
    assert not host.data_path.exists()
