"""MaaEnd v2.28：动态资源与理智任务字段注入的回归用例。"""

import json
from pathlib import Path
from unittest.mock import patch

from app.task.MaaEnd.AutoProxy import AutoProxyTask
from app.task.MaaEnd.resource_loader import MaaEndResourceLoader

TARGET_GROUPS = [
    {
        "value": "Sword",
        "label": "单手剑",
        "options": [
            {"label": "长剑一", "value": "wpn_sword_1"},
            {"label": "长剑二", "value": "wpn_sword_2"},
        ],
    },
    {
        "value": "Bow",
        "label": "弓",
        "options": [{"label": "弓一", "value": "wpn_bow_1"}],
    },
]


class _FakeConfig:
    def __init__(self, values: dict[str, object]):
        self._values = values

    def get(self, section: str, key: str):
        return self._values.get(key)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _build_root(tmp_path: Path, *, legacy: bool = False) -> Path:
    """搭一个最小 MaaEnd 资源根：接口、本地化与拆分后的任务资源。"""

    imports = (
        ["tasks/AutoEssence/AutoEssence.json", "tasks/AutoUseSpMedication.json"]
        if legacy
        else [
            "tasks/ProtocolSpace.json",
            "tasks/AutoEssence/AutoEssence.json",
            "tasks/AutoEssence/Location/SelectLocation.json",
            "tasks/AutoEssence/Target/Target.json",
        ]
    )
    _write_json(
        tmp_path / "interface.json",
        {
            "languages": {"zh_cn": "locales/zh_cn.json"},
            "import": imports,
            "controller": [{"name": "Win32-Front", "type": "Win32"}],
        },
    )
    _write_json(tmp_path / "locales/zh_cn.json", {})

    essence_options: dict[str, dict] = {
        "AutoEssenceChooseLocation": {
            "type": "checkbox",
            "cases": [{"name": "VFTheHub", "label": "枢纽区"}],
        }
    }
    if not legacy:
        essence_options["AutoEssenceMenu"] = {
            "type": "select",
            "cases": [
                {"name": "Random", "label": "随机模式"},
                {"name": "Location", "label": "地区模式"},
                {"name": "Target", "label": "目标选择"},
            ],
        }
        essence_options["AutoUseSpMedication"] = {
            "type": "select",
            "cases": [{"name": "EndTask"}, {"name": "UseMedication"}],
        }
    _write_json(
        tmp_path / "tasks/AutoEssence/AutoEssence.json",
        {
            "task": [{"name": "AutoEssence", "label": "基质刷取"}],
            "option": essence_options,
        },
    )

    if legacy:
        _write_json(
            tmp_path / "tasks/AutoUseSpMedication.json",
            {"task": [{"name": "AutoUseSpMedication", "label": "应急理智加强剂"}]},
        )
        return tmp_path

    _write_json(
        tmp_path / "tasks/ProtocolSpace.json",
        {
            "task": [{"name": "ProtocolSpace", "label": "协议空间"}],
            "option": {
                "ProtocolSpaceObtainMode": {
                    "type": "select",
                    "cases": [{"name": "ObtainScaling2"}, {"name": "Discard"}],
                }
            },
        },
    )
    _write_json(
        tmp_path / "tasks/AutoEssence/Location/SelectLocation.json",
        {
            "option": {
                "AutoEssenceSelectLocation": {
                    "type": "select",
                    "cases": [{"name": "VFTheHub", "label": "枢纽区"}],
                }
            }
        },
    )
    _write_json(
        tmp_path / "tasks/AutoEssence/Target/Target.json",
        {
            "option": {
                "AutoEssenceWeaponsSword": {
                    "type": "checkbox",
                    "cases": [
                        {"name": "wpn_sword_1", "label": "长剑一"},
                        {"name": "wpn_sword_2", "label": "长剑二"},
                    ],
                },
                "AutoEssenceWeaponTypeSword": {
                    "type": "switch",
                    "label": "单手剑",
                    "cases": [{"name": "Yes"}, {"name": "No"}],
                },
                "AutoEssenceWeaponsBow": {
                    "type": "checkbox",
                    "cases": [{"name": "wpn_bow_1", "label": "弓一"}],
                },
                "AutoEssenceWeaponTypeBow": {
                    "type": "switch",
                    "label": "弓",
                    "cases": [{"name": "Yes"}, {"name": "No"}],
                },
            }
        },
    )
    return tmp_path


def test_option_only_resources_merge_into_the_task(tmp_path: Path) -> None:
    loader = MaaEndResourceLoader(_build_root(tmp_path))

    assert loader.has_task("AutoEssence") is True
    assert loader.has_task("ProtocolSpace") is True
    assert loader.has_task("AutoUseSpMedication") is False
    assert loader.has_task_option("AutoEssence", "AutoEssenceSelectLocation") is True
    assert loader.has_task_option("ProtocolSpace", "ProtocolSpaceObtainMode") is True


def test_target_weapon_groups_come_from_the_resource(tmp_path: Path) -> None:
    options = MaaEndResourceLoader(_build_root(tmp_path)).get_options()

    assert [menu["value"] for menu in options["essenceMenus"]] == [
        "Random",
        "Location",
        "Target",
    ]
    groups = options["essenceTargetWeaponGroups"]
    # 组名与顺序完全来自资源声明：没有写死名单，新武器类型会自动出现。
    assert [(group["value"], group["label"]) for group in groups] == [
        ("Sword", "单手剑"),
        ("Bow", "弓"),
    ]
    assert groups[0]["options"] == [
        {"label": "长剑一", "value": "wpn_sword_1"},
        {"label": "长剑二", "value": "wpn_sword_2"},
    ]


def test_legacy_layout_has_no_dynamic_essence_options(tmp_path: Path) -> None:
    loader = MaaEndResourceLoader(_build_root(tmp_path, legacy=True))

    assert loader.has_task("AutoUseSpMedication") is True
    assert loader.has_task_option("AutoEssence", "AutoEssenceMenu") is False
    assert loader.has_task_option("AutoEssence", "AutoEssenceChooseLocation") is True
    options = loader.get_options()
    assert options["essenceMenus"] == []
    assert options["essenceTargetWeaponGroups"] == []


def _essence_proxy(
    supported: set[tuple[str, str]],
    *,
    medication: bool = True,
) -> AutoProxyTask:
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.maaend_root_path = Path("X:/maaend")
    proxy.cur_user_config = _FakeConfig({"IfAutoUseSpMedication": medication})
    proxy._maaend_task_option_supported = (  # type: ignore[method-assign]
        lambda task_name, option_name: (task_name, option_name) in supported
    )
    return proxy


def _write_essence(proxy: AutoProxyTask, key: dict[str, object]) -> dict:
    task: dict[str, object] = {
        "taskName": "AutoEssence",
        "enabled": True,
        "optionValues": {
            "AutoEssenceChooseLocation": {
                "type": "checkbox",
                "caseNames": ["VFTheHub"],
            },
            "AutoEssenceSpecifiedLocation": "legacy",
            "AutoEssenceWeaponsBow": {"type": "checkbox", "caseNames": ["wpn_bow_1"]},
            "AutoEssenceWeaponTypeBow": {"type": "switch", "value": True},
            "AutoEssenceObtainModeClaimOnlyForcedFilter": {
                "type": "select",
                "caseName": "ObtainScaling1",
            },
        },
    }
    with patch(
        "app.task.MaaEnd.AutoProxy.get_loaded_maaend_options",
        return_value={"essenceTargetWeaponGroups": TARGET_GROUPS},
    ):
        proxy._write_auto_essence_options(task, key)
    return task["optionValues"]


def test_target_mode_scopes_weapons_to_the_selected_groups() -> None:
    proxy = _essence_proxy(
        {
            ("AutoEssence", "AutoEssenceMenu"),
            ("AutoEssence", "AutoEssenceWeaponsSword"),
            ("AutoEssence", "AutoEssenceWeaponTypeSword"),
            ("AutoEssence", "AutoEssenceWeaponsBow"),
            ("AutoEssence", "AutoEssenceWeaponTypeBow"),
            ("AutoEssence", "AutoEssenceObtainModeClaimOnlyForcedFilter"),
            ("AutoEssence", "AutoUseSpMedication"),
        }
    )

    option_values = _write_essence(
        proxy,
        {
            "SanityTaskType": "Essence",
            "AutoEssenceSpecifiedLocation": "VFTheHub",
            "AutoEssenceMenu": "Target",
            "AutoEssenceTargetWeapons": ["wpn_sword_2"],
        },
    )

    assert option_values["AutoEssenceMenu"] == {"type": "select", "caseName": "Target"}
    assert option_values["AutoEssenceWeaponsSword"] == {
        "type": "checkbox",
        "caseNames": ["wpn_sword_2"],
    }
    assert option_values["AutoEssenceWeaponTypeSword"] == {
        "type": "switch",
        "value": True,
    }
    # 未选中的武器类型必须显式关掉，否则 MaaEnd 仍按“全选”处理
    assert option_values["AutoEssenceWeaponsBow"] == {
        "type": "checkbox",
        "caseNames": [],
    }
    assert option_values["AutoEssenceWeaponTypeBow"] == {
        "type": "switch",
        "value": False,
    }
    assert "AutoEssenceChooseLocation" not in option_values
    assert "AutoEssenceSelectLocation" not in option_values
    assert "AutoEssenceSpecifiedLocation" not in option_values
    assert option_values["AutoEssenceObtainModeClaimOnlyForcedFilter"] == {
        "type": "select",
        "caseName": "ObtainScaling2",
    }
    assert option_values["AutoUseSpMedication"] == {
        "type": "select",
        "caseName": "UseMedication",
    }


def test_target_mode_drops_groups_the_resource_no_longer_declares() -> None:
    proxy = _essence_proxy(
        {
            ("AutoEssence", "AutoEssenceMenu"),
            ("AutoEssence", "AutoEssenceWeaponsSword"),
        }
    )

    option_values = _write_essence(
        proxy,
        {
            "SanityTaskType": "Essence",
            "AutoEssenceMenu": "Target",
            "AutoEssenceTargetWeapons": ["wpn_sword_2"],
        },
    )

    assert "AutoEssenceWeaponsBow" not in option_values
    assert "AutoEssenceWeaponTypeBow" not in option_values


def test_location_mode_uses_the_split_location_option() -> None:
    proxy = _essence_proxy(
        {
            ("AutoEssence", "AutoEssenceMenu"),
            ("AutoEssence", "AutoEssenceSelectLocation"),
        }
    )

    option_values = _write_essence(
        proxy,
        {
            "SanityTaskType": "Essence",
            "AutoEssenceSpecifiedLocation": "VFTheHub",
            "AutoEssenceMenu": "Location",
        },
    )

    assert option_values["AutoEssenceMenu"] == {
        "type": "select",
        "caseName": "Location",
    }
    assert option_values["AutoEssenceSelectLocation"] == {
        "type": "select",
        "caseName": "VFTheHub",
    }
    assert "AutoEssenceWeaponsSword" not in option_values
    assert "AutoEssenceObtainModeClaimOnlyForcedFilter" not in option_values


def test_legacy_essence_keeps_the_checkbox_location() -> None:
    proxy = _essence_proxy({("AutoEssence", "AutoEssenceChooseLocation")})

    option_values = _write_essence(
        proxy,
        {
            "SanityTaskType": "Essence",
            "AutoEssenceSpecifiedLocation": "VFTheHub",
            "AutoEssenceMenu": "Target",
            "AutoEssenceTargetWeapons": ["wpn_sword_1"],
        },
    )

    assert "AutoEssenceMenu" not in option_values
    assert option_values["AutoEssenceChooseLocation"] == {
        "type": "checkbox",
        "caseNames": ["VFTheHub"],
    }
    assert "AutoEssenceWeaponsSword" not in option_values


def test_medication_switch_can_turn_the_option_off() -> None:
    proxy = _essence_proxy({("AutoEssence", "AutoUseSpMedication")}, medication=False)

    option_values = _write_essence(proxy, {"SanityTaskType": "Essence"})

    assert option_values["AutoUseSpMedication"] == {
        "type": "select",
        "caseName": "EndTask",
    }


def test_removed_medication_task_is_dropped_only_when_upstream_lacks_it() -> None:
    proxy = AutoProxyTask.__new__(AutoProxyTask)

    for support in (False, True, None):
        proxy._maaend_task_supported = (  # type: ignore[method-assign]
            lambda task_name, support=support: support  # type: ignore[misc]
        )
        tasks = [
            {"taskName": "AutoUseSpMedication", "enabled": True},
            {"taskName": "AutoEssence", "enabled": True},
        ]
        proxy._drop_removed_medication_task(tasks)
        names = [task["taskName"] for task in tasks]
        if support is False:
            assert names == ["AutoEssence"]
        else:
            # 上游仍声明该任务、或资源不可读（未知）时都不做移除
            assert names == ["AutoUseSpMedication", "AutoEssence"]


def test_ensure_sanity_task_mirrors_the_saved_entry_shape() -> None:
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.script_config = _FakeConfig({"ControllerType": "Win32-Front"})

    tasks: list[dict[str, object]] = []
    task = proxy._ensure_sanity_task(tasks, "AutoEssence")

    assert task is not None
    assert tasks == [task]
    assert task["taskName"] == "AutoEssence"
    assert task["enabledByController"] == {"Win32-Front": True}
    assert set(task) == {
        "id",
        "taskName",
        "enabled",
        "enabledByController",
        "expanded",
        "optionValues",
    }
    # 任务已存在时不重复补齐
    assert proxy._ensure_sanity_task(tasks, "AutoEssence") is task
    assert len(tasks) == 1
