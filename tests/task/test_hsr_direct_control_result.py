import asyncio
import json
from pathlib import Path

from app.core.config import Config


def test_direct_control_completion_is_success(tmp_path: Path) -> None:
    history_path = tmp_path / "2026-08-19" / "用户" / "HSR-05-13-10.json"
    history_path.parent.mkdir(parents=True)
    history_path.write_text(
        json.dumps({"hsr_result": "HSR 脚本直控完成"}), encoding="utf-8"
    )

    statistics = asyncio.run(Config.merge_statistic_info([history_path]))

    assert statistics["index"][0]["status"] == "DONE"
    assert "error_info" not in statistics
