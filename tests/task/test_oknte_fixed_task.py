"""Keep fixed-task selections compatible with both OK-NTE CLI versions."""

import json
import uuid

import pytest

from app.models.config.script import OkNteConfig, OkNteUserConfig
from app.models.task import TaskItem, TaskScriptItem, TaskUserItem
from app.task.OkNte.AutoProxy import AutoProxyTask
from app.task.OkNte.tools.arguments import task_argument
from tests.config_support import activate_config


@pytest.mark.parametrize(
    ("version", "task_index", "expected"),
    [
        ("v1.3.0", 19, "19"),
        ("v1.3.7", 19, "21"),
        ("v1.4.1", 19, "22"),
        ("v1.4.6", 19, "23"),
        ("v1.4.7", 19, "CinemaDateTask"),
        ("v1.5.3", 6, "RhythmTask"),
        ("v1.5.4", 6, "RhythmTask"),
        ("v1.5.4", 19, "CinemaDateTask"),
    ],
)
def test_fixed_task_uses_the_selected_task_for_installed_version(
    tmp_path, version, task_index, expected
):
    manifest = tmp_path / "data/apps/ok-nte/app.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"current_version": version}), encoding="utf-8")

    assert task_argument(tmp_path, task_index) == expected


def test_standalone_body_uses_named_cli_without_launcher_manifest(tmp_path):
    (tmp_path / "ok-nte.exe").touch()
    (tmp_path / "_internal").mkdir()

    assert task_argument(tmp_path, 19) == "CinemaDateTask"


def test_missing_launcher_manifest_cannot_dispatch_an_ambiguous_task(tmp_path):
    assert task_argument(tmp_path, 1) == "1"
    assert task_argument(tmp_path, 2) == "2"
    with pytest.raises(ValueError, match="OK-NTE"):
        task_argument(tmp_path, 19)


@pytest.mark.asyncio
async def test_corrupt_launcher_manifest_fails_account_preflight(tmp_path):
    program = tmp_path / "ok-nte.exe"
    program.touch()
    script_log = tmp_path / "ok-script.log"
    script_log.touch()
    manifest = tmp_path / "data/apps/ok-nte/app.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("[]", encoding="utf-8")
    config = OkNteConfig(
        Info={"RootPath": tmp_path},
        Script={"ScriptPath": program, "LogPath": script_log, "ConfigPath": tmp_path},
        Game={"Enabled": False},
    )
    account = OkNteUserConfig(Task={"TaskIndex": 19})
    await activate_config(config)
    await activate_config(account)

    uid = uuid.uuid4()
    task = TaskItem()
    await task.activate()
    sid = task.scripts.add(TaskScriptItem, payload={"info": {"script_id": "oknte"}})
    await task.scripts.commit()
    script = task.scripts[sid]
    script.users.add(TaskUserItem, payload={"info": {"user_id": str(uid)}})
    await script.users.commit()
    await script.set_current_index(0)

    proxy = AutoProxyTask(script, config, {uid: account}, None)
    assert str(manifest) in await proxy.check()
