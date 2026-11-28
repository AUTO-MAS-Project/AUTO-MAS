"""推荐配置创建保留原生格式、隔离设备信息且不覆盖已有配置。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.config import BAAHConfig
from app.task.BAAH.api_service import BAAHConfigService
from app.utils.common.update_files import directory_lock

TEMPLATE = Path(__file__).resolve().parents[2] / "res/templates/BAAH/recommended.json"


@pytest.fixture
def installed_baah(tmp_path):
    exe = tmp_path / "BAAH.exe"
    exe.touch()
    script = BAAHConfig(Script={"BAAHPath": exe})
    return BAAHConfigService(get_script=lambda _: script, template_path=TEMPLATE)


@pytest.mark.asyncio
async def test_generated_native_config_is_portable_and_does_not_overwrite(
    tmp_path, installed_baah
):
    config_dir = tmp_path / "BAAH_CONFIGS"
    config_dir.mkdir()
    original = config_dir / "推荐配置.json"
    original.write_bytes(b"existing user config, even if invalid JSON")
    script_id = str(uuid4())

    name = await installed_baah.create_recommended_config(script_id)
    second = await installed_baah.create_recommended_config(script_id)
    assert name == "推荐配置_2"
    assert second == "推荐配置_3"
    assert original.read_bytes() == b"existing user config, even if invalid JSON"
    data = json.loads((config_dir / f"{name}.json").read_text(encoding="utf-8"))
    assert data == json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert data["TARGET_PORT"] == 0
    assert data["TARGET_EMULATOR_PATH"] == ""
    assert data["ADB_SEIAL_NUMBER"] == ""
    assert data["ADB_DIRECT_USE_SERIAL_NUMBER"] is False
    for key in (
        "MAIL_USER",
        "MAIL_PASS",
        "SENDER_EMAIL",
        "RECEIVER_EMAIL",
        "MAIL_HOST",
        "TARGET_HTTP_URL",
        "TARGET_HTTP_TOKEN",
        "PRE_COMMAND",
        "POST_COMMAND",
        "USER_DEF_TASKS",
    ):
        assert data[key] == ""
    for key in ("ENABLE_MAIL_NOTI", "ENABLE_HTTP_NOTI", "USE_OBJ_FLOW_WHEN_LOGIN"):
        assert data[key] is False
    assert "SCREENSHOT_NAME" not in data
    assert "USER_STORAGE_FILE_NAME" not in data
    assert data["OBJ_FLOW_WHEN_LOGIN"] == {}
    pipelines = data["TASK_ORDER_GROUP"]["ALL_PIPELINES"]
    active = pipelines[data["TASK_ORDER_GROUP"]["ACTIVATE_IND"]]
    assert active["TASK_PIPELINE"].count("活动关卡") == 2
    assert active["TASK_PIPELINE"].index("每日任务") < max(
        i for i, task in enumerate(active["TASK_PIPELINE"]) if task == "活动关卡"
    )
    assert name in installed_baah.get_config_names(script_id)


@pytest.mark.asyncio
async def test_busy_installation_refuses_creation(tmp_path, installed_baah):
    async with directory_lock(tmp_path.resolve()):
        with pytest.raises(RuntimeError):
            await installed_baah.create_recommended_config(str(uuid4()))
    assert not (tmp_path / "BAAH_CONFIGS").exists()


@pytest.mark.asyncio
async def test_missing_template_does_not_create_empty_config(tmp_path):
    exe = tmp_path / "BAAH.exe"
    exe.touch()
    script = BAAHConfig(Script={"BAAHPath": exe})
    service = BAAHConfigService(
        get_script=lambda _: script, template_path=tmp_path / "missing.json"
    )
    with pytest.raises(RuntimeError):
        await service.create_recommended_config(str(uuid4()))
    assert not (tmp_path / "BAAH_CONFIGS").exists()


@pytest.mark.asyncio
async def test_unconfigured_installation_does_not_write(tmp_path):
    service = BAAHConfigService(
        get_script=lambda _: BAAHConfig(), template_path=TEMPLATE
    )
    with pytest.raises(ValueError):
        await service.create_recommended_config(str(uuid4()))
    assert list(tmp_path.iterdir()) == []
