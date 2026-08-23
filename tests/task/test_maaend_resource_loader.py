import json
from pathlib import Path
from unittest.mock import Mock

import json5

from app.task.MaaEnd.resource_loader import MaaEndResourceLoader


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_startup_only_reparses_changed_source_files(tmp_path, monkeypatch):
    root_path = tmp_path / "MaaEnd"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(MaaEndResourceLoader, "_loader_cache", {})
    write_json(
        root_path / "interface.json",
        {
            "languages": {"zh-CN": "locales/zh-CN.json"},
            "controller": [{"name": "Desktop", "label": "$controller", "type": "Win32"}],
            "import": ["tasks/pretasks/GameSetting.json", "tasks/AutoEssence.json"],
        },
    )
    write_json(
        root_path / "locales/zh-CN.json",
        {"controller": "桌面端", "hub": "枢纽区"},
    )
    write_json(
        root_path / "tasks/AutoEssence.json",
        {
            "task": [{"name": "AutoEssence", "label": "自动基质"}],
            "option": {
                "AutoEssenceChooseLocation": {
                    "cases": [{"name": "Hub", "label": "$hub"}]
                }
            },
        },
    )

    loader = MaaEndResourceLoader.get_cached(root_path, force_reload=True)
    assert loader.get_options()["essenceLocations"] == [
        {"label": "枢纽区", "value": "Hub"}
    ]
    assert loader.get_task_i18n("zh-CN") == {"AutoEssence": "自动基质"}

    write_json(
        root_path / "locales/zh-CN.json",
        {"controller": "桌面控制器", "hub": "枢纽区域"},
    )
    write_json(
        root_path / "tasks/pretasks/GameSetting.json",
        {"task": [{"name": "GameSetting", "label": "游戏设置"}]},
    )
    MaaEndResourceLoader._loader_cache.clear()
    loads = Mock(wraps=json5.loads)
    monkeypatch.setattr(json5, "loads", loads)
    loader = MaaEndResourceLoader.get_cached(root_path)

    assert loader.get_options()["controllers"] == [
        {"label": "桌面控制器", "value": "Desktop"}
    ]
    assert loader.get_task_i18n("zh-CN") == {
        "GameSetting": "游戏设置",
        "AutoEssence": "自动基质",
    }
    assert loads.call_count == 2
