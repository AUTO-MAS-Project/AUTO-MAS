import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.core.config import Config


def test_history_log_path_prefixes_script_name() -> None:
    log_time = datetime(2026, 8, 5, 12, 34, 56)

    log_path = Config.build_history_log_path(
        script_name="每日/任务",
        user_name="用户 1",
        log_time=log_time,
    )

    assert log_path.name == "每日_任务-12-34-56.log"
    assert log_path.parent == Config.history_path / "2026-08-05" / "用户 1"


def test_merge_statistic_info_accepts_prefixed_and_legacy_names(
    tmp_path: Path,
) -> None:
    user_history_path = tmp_path / "2026-08-05" / "用户 1"
    user_history_path.mkdir(parents=True)

    prefixed_path = user_history_path / "每日-任务-12-34-56.json"
    legacy_path = user_history_path / "13-34-56.json"
    for path in (prefixed_path, legacy_path):
        path.write_text(
            json.dumps({"general_result": "Success!"}), encoding="utf-8"
        )

    statistics = asyncio.run(
        Config.merge_statistic_info([prefixed_path, legacy_path])
    )

    assert len(statistics["index"]) == 2
    assert {Path(item["jsonFile"]).name for item in statistics["index"]} == {
        prefixed_path.name,
        legacy_path.name,
    }
