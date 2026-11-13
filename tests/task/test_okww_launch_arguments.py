"""OK-WW 普通日常启动参数回归。"""

import importlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config.script import OkwwUserConfig
from app.models.task import UserItem
from app.task.Okww.AutoProxy import AutoProxyTask
from tests.runtime_support import RuntimeStub


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version", "argument"),
    [
        ("v3.6.6", "1"),
        ("v3.6.7-beta.2", "DailyTask"),
        ("v3.6.7", "DailyTask"),
        ("v3.8.0-beta.1", "DailyTask"),
        ("unknown", None),
    ],
)
async def test_daily_task_uses_version_supported_argument(
    tmp_path, version, argument, monkeypatch
):
    task = make_task(tmp_path, version)
    # 关闭开关后，保留的自定义草稿不参与启动或校验。
    task.cur_user_config.Task.CustomArguments = '"unfinished'

    if argument is None:
        with pytest.raises(ValueError, match="无法识别 OK-WW 当前版本"):
            await task.prepare()
        return
    await task.prepare()

    assert task.okww_args == ["-t", argument, "-e"]

    app_json = tmp_path / "data/apps/ok-ww/app.json"
    module = importlib.import_module("app.task.Okww.AutoProxy")
    launches = []

    async def launch(*args, **kwargs):
        launches.append(list(kwargs["args"]))
        app_json.write_text('{"current_version": "v3.8.0-beta.1"}', encoding="utf-8")

    monkeypatch.setattr(module, "start_okww", launch)
    monkeypatch.setattr(task, "_push_dispatch_log", AsyncMock())
    monkeypatch.setattr(task.okww_process_manager, "kill", AsyncMock())
    monkeypatch.setattr(module.process, "kill_process", AsyncMock())
    await task._start_okww_with_current_arguments()
    expected = [["-t", "DailyTask", "-e"]]
    if argument == "1":
        expected.insert(0, ["-t", "1", "-e"])
    assert launches == expected
    assert task.okww_process_manager.kill.await_count == (argument == "1")


def make_task(tmp_path, version):
    app_json = tmp_path / "data/apps/ok-ww/app.json"
    app_json.parent.mkdir(parents=True)
    app_json.write_text(json.dumps({"current_version": version}), encoding="utf-8")
    uid = uuid.uuid4()
    user = UserItem(user_id=str(uid), name="用户", status="等待")
    script_info = RuntimeStub(
        task_info=RuntimeStub(),
        script_id=str(uuid.uuid4()),
        user_list=[user],
        current_index=0,
    )
    return AutoProxyTask(
        script_info,
        SimpleNamespace(Info=SimpleNamespace(RootPath=tmp_path)),
        {uid: OkwwUserConfig.model_validate({"Notify": {"PushLogMode": "关闭"}})},
        None,
    )


@pytest.mark.asyncio
async def test_custom_arguments_override_unknown_version(tmp_path):
    task = make_task(tmp_path, "unknown")
    task.cur_user_config.Task.IfCustomArguments = True
    task.cur_user_config.Task.CustomArguments = (
        r'-t "Other Task" -h --path "C:\Game Files\config.json"'
    )
    await task.prepare()
    assert task.okww_args == [
        "-t",
        "Other Task",
        "-h",
        "--path",
        r"C:\Game Files\config.json",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("custom", [True, False])
async def test_native_switch_passes_custom_arguments_through(tmp_path, custom):
    from app.task.Okww.BatchProxy import BatchProxyTask

    proxy = make_task(tmp_path, "unknown")
    proxy.cur_user_config.Task.IfCustomArguments = custom
    proxy.cur_user_config.Task.CustomArguments = '-t "Other Task" --'
    proxy.cur_user_config.Info.Id = "13012345678"
    task = BatchProxyTask(
        proxy.script_info,
        proxy.script_config,
        proxy.user_config,
        None,
        participants=[proxy.cur_user_item],
    )
    await task.prepare()
    assert task.okww_args == (
        ["-t", "Other Task", "--"] if custom else ["-t", "MultiAccountConfigTask", "-e"]
    )


@pytest.mark.parametrize("arguments", ['"unfinished'])
def test_invalid_custom_arguments_are_rejected(arguments):
    from app.task.Okww.tools.arguments import build_custom_arguments

    with pytest.raises(ValueError):
        build_custom_arguments(arguments)


def test_custom_arguments_survive_account_backup_overlay():
    from app.task.Okww.tools.backup_archive import group_overlay, read_overlay_values

    config = OkwwUserConfig.model_validate(
        {"Task": {"IfCustomArguments": True, "CustomArguments": '-t "Other Task" -h'}}
    )
    restored = OkwwUserConfig.model_validate(group_overlay(read_overlay_values(config)))
    assert restored.Task.IfCustomArguments is True
    assert restored.Task.CustomArguments == '-t "Other Task" -h'


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ("", []),
        ("-t DailyTask --", ["-t", "DailyTask", "--"]),
        ("-t DailyTask -e", ["-t", "DailyTask", "-e"]),
    ],
)
def test_custom_arguments_are_not_rewritten(arguments, expected):
    from app.task.Okww.tools.arguments import build_custom_arguments

    assert build_custom_arguments(arguments) == expected
