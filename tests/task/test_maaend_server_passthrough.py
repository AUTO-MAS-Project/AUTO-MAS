"""上游服务器选项加载与原生启动参数透传。"""

import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.task.MaaEnd.resource_loader import MaaEndResourceLoader


@pytest.fixture
def maaend_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(MaaEndResourceLoader, "_loader_cache", {})
    (tmp_path / "tasks/pretasks").mkdir(parents=True)
    (tmp_path / "resource").mkdir()
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent/go-service").touch()
    (tmp_path / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "MaaEnd",
                "languages": {"zh_cn": "zh.json"},
                "controller": [{"name": "Win32-Front", "type": "Win32", "win32": {}}],
                "resource": [{"name": "Default", "path": ["resource"]}],
                "import": ["tasks/pretasks/LaunchGamePC.json"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "zh.json").write_text(
        json.dumps({"region.steam": "Steam"}), encoding="utf-8"
    )
    (tmp_path / "tasks/pretasks/LaunchGamePC.json").write_text(
        json.dumps(
            {
                "pretask": {
                    "name": "LaunchGamePC",
                    "exec": "agent/go-service",
                    "args": ["--pretask", "LaunchGamePC"],
                    "option": ["LaunchGamePCRegion"],
                },
                "option": {
                    "LaunchGamePCRegion": {
                        "type": "select",
                        "default_case": "CN",
                        "cases": [
                            {"name": "CN", "label": "国服"},
                            {"name": "Steam", "label": "$region.steam"},
                            {"name": "FutureChannel", "label": "Future"},
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_upstream_servers_are_loaded_without_fixed_channel_list(maaend_root):
    assert MaaEndResourceLoader(maaend_root).get_options()["servers"] == [
        {"value": "CN", "label": "国服"},
        {"value": "Steam", "label": "Steam"},
        {"value": "FutureChannel", "label": "Future"},
    ]


@pytest.mark.parametrize(
    "server,expected",
    [("Steam", "Steam"), ("FutureChannel", "FutureChannel"), ("官服", "CN")],
)
def test_selected_server_reaches_upstream_process(
    maaend_root, monkeypatch, server, expected
):
    import asyncio

    module = importlib.import_module("app.task.MaaEnd.AutoProxy")
    process = AsyncMock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(module.ProcessRunner, "run_process", process)
    monkeypatch.setattr(module, "push_dispatch_log", AsyncMock())
    task = SimpleNamespace(
        maaend_root_path=maaend_root,
        script_config=SimpleNamespace(
            Game=MaaEndConfig.GameFields(
                ControllerType="Win32-Front", LaunchMode="MaaEnd"
            )
        ),
        cur_user_config=SimpleNamespace(
            Info=MaaEndUserConfig.InfoFields(Resource=server)
        ),
        launcher_game_setting_options={},
        _game_setting_pretask=lambda: "__MXU_PRETASK__LaunchGamePC",
        mode="Routine",
        first_run_mode="Routine",
        script_info=None,
        _launch_mode=lambda: "MaaEnd",
    )
    asyncio.run(module.AutoProxyTask._apply_launcher_game_settings(task))
    args = process.call_args.args
    assert json.loads(args[-1])["LaunchGamePCRegion"] == expected
    assert task.launcher_game_setting_options == {}


def test_standard_json_resources_use_fast_parser(maaend_root, monkeypatch):
    module = importlib.import_module("app.task.MaaEnd.resource_loader")
    slow_parser = module.json5.loads
    calls = []

    def track_json5(text):
        calls.append(text)
        return slow_parser(text)

    monkeypatch.setattr(module.json5, "loads", track_json5)
    options = module.MaaEndResourceLoader(maaend_root).get_options()
    assert options["servers"][1] == {"value": "Steam", "label": "Steam"}
    assert calls == []


def test_json5_resources_and_changed_files_are_reloaded(maaend_root):
    module = importlib.import_module("app.task.MaaEnd.resource_loader")
    locale = maaend_root / "zh.json"
    locale.write_text(
        "{ // JSON5 注释\n 'region.steam': 'Steam JSON5',\n}", encoding="utf-8"
    )
    loader = module.MaaEndResourceLoader.get_cached(maaend_root)
    assert loader.get_options()["servers"][1]["label"] == "Steam JSON5"

    locale.write_text('{"region.steam": "Updated Steam label"}', encoding="utf-8")
    refreshed = module.MaaEndResourceLoader.get_cached(maaend_root)
    assert refreshed.get_options()["servers"][1]["label"] == "Updated Steam label"
    assert loader.get_options()["servers"][1]["label"] == "Steam JSON5"


def test_cached_resources_are_reused_after_restart(maaend_root, monkeypatch):
    module = importlib.import_module("app.task.MaaEnd.resource_loader")
    before = module.MaaEndResourceLoader.get_cached(maaend_root).get_options()
    source_files = {
        maaend_root / "interface.json",
        maaend_root / "zh.json",
        maaend_root / "tasks/pretasks/LaunchGamePC.json",
    }
    read_text = type(maaend_root).read_text

    def read_cached_files_only(path, *args, **kwargs):
        assert path not in source_files, (
            "Unchanged resource was read instead of cached data"
        )
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(type(maaend_root), "read_text", read_cached_files_only)
    module.MaaEndResourceLoader._loader_cache.pop(maaend_root.resolve())
    restored = module.MaaEndResourceLoader.get_cached(maaend_root)
    assert restored.get_options() == before
