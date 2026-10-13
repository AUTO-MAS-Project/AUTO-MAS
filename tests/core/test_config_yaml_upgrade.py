from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import ConfigCollection
from app.core.config_upgrade import convert_collection, convert_entry, upgrade_json_configs
from app.models.config import GameSignAccount, QueueEntry, Setting, Tools
from app.utils.constants import UTC8
from app.utils.io import read_dict_file, write_file
from app.utils.security import dpapi_decrypt, dpapi_encrypt


def test_upgrade_once_preserves_changes_and_archives_source(tmp_path):
    write_file(tmp_path / "Config.json", {"Function": {"IfSilence": True}, "Data": {"UID": "old-install"}})
    write_file(tmp_path / "setting.yaml", {"function": {"if_allow_sleep": True}, "data": {"uid": "generated"}})
    upgrade_json_configs(tmp_path)
    result = read_dict_file(tmp_path / "setting.yaml")
    assert result["function"] == {"if_allow_sleep": True, "if_silence": True}
    assert result["data"]["uid"] == "old-install"
    assert not (tmp_path / "Config.json").exists()
    assert (tmp_path / "legacy-json/Config.json").is_file()
    write_file(tmp_path / "setting.yaml", {"function": {"if_silence": False}})
    upgrade_json_configs(tmp_path)
    assert read_dict_file(tmp_path / "setting.yaml")["function"]["if_silence"] is False


def test_invalid_payload_keeps_original_and_existing_yaml(tmp_path):
    write_file(tmp_path / "Config.json", {"Voice": {"Type": "invalid"}})
    write_file(tmp_path / "setting.yaml", {"voice": {"enabled": True}})
    with pytest.raises(ValueError):
        upgrade_json_configs(tmp_path)
    assert (tmp_path / "Config.json").is_file()
    assert read_dict_file(tmp_path / "setting.yaml") == {"voice": {"enabled": True}}


def test_old_dpapi_cipher_is_not_encrypted_twice():
    cipher = dpapi_encrypt("migration-secret")
    result = convert_entry({"Notify": {"AuthorizationCode": cipher}}, Setting.build())
    assert result["notify"]["authorization_code"] == "DPAPI:" + cipher
    assert dpapi_decrypt(result["notify"]["authorization_code"][6:]) == "migration-secret"


def test_account_credentials_and_device_identity_are_preserved():
    cipher = dpapi_encrypt("account-secret")
    result = convert_entry({"GameSignAccount": {"Name": "account", "TaygedoToken": cipher, "MiyousheDeviceId": "device", "Enabled": False}}, GameSignAccount.build())
    assert result["info"]["name"] == "account"
    assert result["info"]["enabled"] is False
    assert result["info"]["taygedo_token"] == "DPAPI:" + cipher
    assert result["info"]["miyoushe_device_id"] == "device"


def test_queue_nested_ids_schedule_and_time_are_preserved():
    queue_id, item_id, script_id = (str(uuid4()) for _ in range(3))
    source = {"instances": [{"uid": queue_id, "type": "QueueConfig"}], queue_id: {
        "Info": {"CycleEnabled": True, "StartUpMode": "DailyFirst"},
        "SubConfigsInfo": {"QueueItem": {"instances": [{"uid": item_id, "type": "QueueItem"}], item_id: {
            "Info": {"ScriptId": script_id},
            "Schedule": {"Mode": "interval", "IntervalMinutes": 30, "NextRunAt": "2000-01-01 00:00:00", "Time": "08:30"}
        }}}
    }}
    result = convert_collection(source, ConfigCollection.build([QueueEntry]))
    assert result["order"] == [{"uid": queue_id, "type": "QueueEntry"}]
    entry = result["data"][queue_id]
    assert entry["info"]["schedule_mode"] == "cycle"
    assert entry["info"]["start_up_mode"] == "DailyFirst"
    item = entry["items"]["data"][item_id]
    assert item["info"]["script_id"] == script_id
    assert item["schedule"]["next_run_at"] is None
    assert datetime.fromisoformat(item["schedule"]["time"]).hour == 8


def test_unsupported_type_is_not_silently_discarded():
    uid = str(uuid4())
    with pytest.raises(ValueError, match="MaaConfig"):
        convert_collection({"instances": [{"uid": uid, "type": "MaaConfig"}], uid: {}}, ConfigCollection.build([QueueEntry]))


def test_real_sources_convert_without_writing():
    root = Path("config")
    for filename, node in (("Config.json", Setting.build()), ("ToolsConfig.json", Tools.build()), ("QueueConfig.json", ConfigCollection.build([QueueEntry]))):
        source = root / filename
        if not source.is_file():
            continue
        if isinstance(node, ConfigCollection):
            convert_collection(read_dict_file(source), node)
        else:
            convert_entry(read_dict_file(source), node)
