import json
from pathlib import Path

from app.task.MaaEnd.resource_loader import MaaEndResourceLoader


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_missing_unrelated_task_resource_does_not_block_options(tmp_path, monkeypatch):
    write_json(
        tmp_path / "interface.json",
        {
            "languages": {"zh-CN": "locales/zh-CN.json"},
            "controller": [{"name": "Desktop", "label": "$controller", "type": "Win32"}],
            "import": ["tasks/pretasks/GameSetting.json", "tasks/AutoEssence.json"],
        },
    )
    write_json(tmp_path / "locales/zh-CN.json", {"controller": "桌面端", "hub": "枢纽区"})
    write_json(tmp_path / "config/mxu-MaaEnd.json", {"settings": {"language": "zh-CN"}})
    write_json(
        tmp_path / "tasks/AutoEssence.json",
        {
            "task": [{"name": "AutoEssence", "label": "自动基质"}],
            "option": {
                "AutoEssenceChooseLocation": {
                    "cases": [{"name": "Hub", "label": "$hub"}]
                }
            },
        },
    )
    monkeypatch.setattr(MaaEndResourceLoader, "_save_disk_cache", lambda self: None)

    loader = MaaEndResourceLoader(tmp_path)

    assert loader.get_options() == {
        "controllers": [{"label": "桌面端", "value": "Desktop"}],
        "controllerTypes": {"Desktop": "Win32"},
        "essenceLocations": [{"label": "枢纽区", "value": "Hub"}],
    }
    assert loader.get_task_i18n("zh-CN") == {"AutoEssence": "自动基质"}
