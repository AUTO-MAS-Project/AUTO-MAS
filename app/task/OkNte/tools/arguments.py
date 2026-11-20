"""Resolve the saved MAS task selection to the OK-NTE CLI argument."""

from pathlib import Path

from packaging.version import InvalidVersion, Version

from app.utils.common.io import read_dict_file

from .runtime import runtime_dir

# The keys are MAS account selections, which also identify the task in history.
_NAMED_TASKS = {
    3: "FishingTask",
    4: "AnomalyTask",
    5: "AnomalyHunter",
    6: "RhythmTask",
    7: "OwnerSelectionTask",
    8: "AutoHeistTask",
    9: "BagelAITools",
    10: "WhirlwindTask",
    11: "DSDFarmTask",
    12: "CombatDetectionTestTask",
    13: "DiagnosisTask",
    14: "DailyClaimTask",
    15: "GiftTask",
    16: "CoffeeTask",
    17: "FountainTask",
    18: "FurnitureTask",
    19: "CinemaDateTask",
}

# Legacy numeric CLI arguments for MAS selections 12–19. Earlier selections
# already match the CLI. OK-NTE v1.4.7 switched to ok-script 2.0.8.
_NAMED_CLI_SINCE = Version("1.4.7")
_LEGACY_TAILS = (
    (Version("1.4.2"), (15, 17, 18, 19, 20, 21, 22, 23)),
    (Version("1.3.8"), (14, 16, 17, 18, 19, 20, 21, 22)),
    (Version("1.3.3"), (14, 15, 16, 17, 18, 19, 20, 21)),
    (Version("1.3.0"), (12, 13, 14, 15, 16, 17, 18, 19)),
)


def task_argument(script_root: Path, task_index: int) -> str:
    """Keep MAS task selection stable across supported OK-NTE releases."""
    if task_index in (1, 2):
        return str(task_index)

    task_name = _NAMED_TASKS[task_index]
    # Official standalone body packages were introduced after the named CLI.
    if runtime_dir(script_root) == script_root:
        return task_name

    app_path = script_root / "data/apps/ok-nte/app.json"
    try:
        app_manifest = read_dict_file(app_path)
        version = Version(str(app_manifest.get("current_version")))
    except (OSError, InvalidVersion) as exc:
        raise ValueError(
            "无法确认 OK-NTE 已安装版本，请先在 OK-NTE 启动器完成安装或更新"
        ) from exc

    if version >= _NAMED_CLI_SINCE:
        return task_name

    if not version.is_prerelease:
        for first_version, arguments in _LEGACY_TAILS:
            if version >= first_version:
                cli_index = (
                    task_index if task_index < 12 else arguments[task_index - 12]
                )
                return str(cli_index)

    raise ValueError(f"OK-NTE {version} 的固定任务编号无法确认，请更新 OK-NTE")
