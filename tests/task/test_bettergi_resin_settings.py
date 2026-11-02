"""BetterGI 新旧树脂配置的面板读写与任务结束还原。"""

from copy import deepcopy

import pytest

from app.task.BetterGI.tools import one_dragon


@pytest.fixture(params=["domain", "stygian"])
def settings_io(request, tmp_path):
    kind = request.param
    segment = "autoDomainConfig" if kind == "domain" else "autoStygianOnslaughtConfig"
    read = getattr(one_dragon, f"read_global_{kind}_settings")
    write = getattr(one_dragon, f"write_global_{kind}_settings")
    path = tmp_path / "User" / "config.json"
    path.parent.mkdir()
    return tmp_path, segment, path, read, write


def usage(mode="PerType"):
    return {
        "mode": mode,
        "runCount": 7,
        "allowed": {
            "condensed": True,
            "original": True,
            "transient": True,
            "fragile": False,
        },
        "counts": {"condensed": 7, "original": 4, "transient": 2, "fragile": 0},
        "originalTier": "Only20",
        "futureOption": {"opaque": True},
    }


def seed(settings_io, native_usage):
    root, segment, path, read, write = settings_io
    config = {
        segment: {
            "resinUsage": native_usage,
            "specifyResinUse": False,
            "condensedResinUseCount": 1,
            "originalResinUseCount": 0,
            "transientResinUseCount": 0,
            "fragileResinUseCount": 0,
        },
        "otherConfig": {"untouched": True},
    }
    one_dragon.write_file(path, config)
    return config


@pytest.mark.parametrize("mode", ["PerType", 2])
def test_new_resin_settings_take_priority_over_stale_legacy_fields(settings_io, mode):
    root, segment, path, read, write = settings_io
    seed(settings_io, usage(mode))

    result = read(root)

    assert result["specifyResinUse"] is True
    assert result["condensedResinUseCount"] == 7
    assert result["originalResinUseCount"] == 4
    assert result["transientResinUseCount"] == 2


def test_partial_write_updates_new_usage_and_preserves_other_choices(settings_io):
    root, segment, path, read, write = settings_io
    original = seed(settings_io, usage())

    write(root, {"condensedResinUseCount": 3})

    saved = one_dragon.read_file(path)
    expected = deepcopy(original)
    expected[segment]["condensedResinUseCount"] = 3
    expected[segment]["resinUsage"]["counts"]["condensed"] = 3
    assert saved == expected
    assert read(root)["condensedResinUseCount"] == 3


def test_write_repairs_new_usage_when_the_legacy_value_already_matches(settings_io):
    root, segment, path, read, write = settings_io
    config = seed(settings_io, usage())
    config[segment]["condensedResinUseCount"] = 3
    one_dragon.write_file(path, config)

    write(root, {"condensedResinUseCount": 3})

    assert one_dragon.read_file(path)[segment]["resinUsage"]["counts"]["condensed"] == 3


@pytest.mark.parametrize("specified", [False, True])
def test_mode_change_updates_the_active_resin_usage(settings_io, specified):
    root, segment, path, read, write = settings_io
    seed(settings_io, usage("Exhaust" if specified else "PerType"))

    write(root, {"specifyResinUse": specified})

    saved = one_dragon.read_file(path)[segment]["resinUsage"]
    assert saved["mode"] == ("PerType" if specified else "Exhaust")
    assert saved["counts"] == usage()["counts"]
    assert saved["allowed"] == usage()["allowed"]


@pytest.mark.parametrize("mode", ["Exhaust", "RunCount", "PerType"])
def test_full_panel_save_preserves_unedited_native_usage(settings_io, mode):
    root, segment, path, read, write = settings_io
    original = seed(settings_io, usage(mode))
    panel = read(root)
    panel["autoArtifactSalvage"] = True

    write(root, panel)

    saved = one_dragon.read_file(path)[segment]
    assert saved["autoArtifactSalvage"] is True
    assert saved["resinUsage"] == original[segment]["resinUsage"]


@pytest.mark.parametrize("native_usage", [None, usage()])
def test_runtime_resin_overlay_is_fully_restored(settings_io, native_usage):
    root, segment, path, read, write = settings_io
    original = seed(settings_io, native_usage)
    snapshot = one_dragon.snapshot_global_battle_config(root)

    write(root, {"specifyResinUse": True, "condensedResinUseCount": 3})
    one_dragon.restore_global_battle_config(root, snapshot)

    assert one_dragon.read_file(path) == original


def test_restore_preserves_unrelated_native_resin_changes(settings_io):
    root, segment, path, read, write = settings_io
    original = seed(settings_io, usage())
    snapshot = one_dragon.snapshot_global_battle_config(root)
    write(root, {"specifyResinUse": False, "condensedResinUseCount": 3})
    changed = one_dragon.read_file(path)
    changed[segment]["resinUsage"]["originalTier"] = "Prefer40"
    changed[segment]["resinUsage"]["futureOption"] = {"external": True}
    one_dragon.write_file(path, changed)

    one_dragon.restore_global_battle_config(root, snapshot)

    restored = one_dragon.read_file(path)
    expected = deepcopy(original)
    expected[segment]["resinUsage"]["originalTier"] = "Prefer40"
    expected[segment]["resinUsage"]["futureOption"] = {"external": True}
    assert restored == expected


@pytest.mark.parametrize("initial_usage", [None, {}, "missing"])
def test_restore_removes_usage_created_by_bgi_runtime_migration(
    settings_io, initial_usage
):
    root, segment, path, read, write = settings_io
    original = seed(settings_io, initial_usage)
    if initial_usage == "missing":
        del original[segment]["resinUsage"]
        one_dragon.write_file(path, original)
    snapshot = one_dragon.snapshot_global_battle_config(root)
    write(root, {"specifyResinUse": True, "condensedResinUseCount": 3})
    migrated = one_dragon.read_file(path)
    migrated[segment]["resinUsage"] = usage()
    migrated[segment]["resinUsage"]["counts"]["condensed"] = 3
    one_dragon.write_file(path, migrated)

    one_dragon.restore_global_battle_config(root, snapshot)

    assert one_dragon.read_file(path) == original


def test_legacy_config_keeps_working_without_adding_new_fields(settings_io):
    root, segment, path, read, write = settings_io
    original = seed(settings_io, None)
    del original[segment]["resinUsage"]
    one_dragon.write_file(path, original)

    write(root, {"specifyResinUse": True, "condensedResinUseCount": 3})

    assert "resinUsage" not in one_dragon.read_file(path)[segment]
    assert read(root)["specifyResinUse"] is True
    assert read(root)["condensedResinUseCount"] == 3
