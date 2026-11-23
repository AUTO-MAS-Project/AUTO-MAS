"""专项计划按字段覆写本次运行配置，不保存或下发整份账号副本。"""

import json
from datetime import datetime
from pathlib import Path

from app.models.schema import OkNtePlanKey
from app.task.OkNte.config_schema import (
    DAILY_ROUTINE_CONFIGS_FILE,
    DAILY_ROUTINE_TASK_FILE,
    DEFAULT_CONFIG_DATA,
    update_oknte_config_data,
)
from app.utils.common.constants import UTC3


def apply_plan(config_dir: Path, key: OkNtePlanKey) -> None:
    now = datetime.now().astimezone()
    for name, patch in key.Configs.items():
        if Path(name).name != name or not name.endswith(".json"):
            raise ValueError("计划配置文件名无效")
        target = config_dir / name
        if name == DAILY_ROUTINE_CONFIGS_FILE:
            weekly = patch.get("anomaly_pilgrimage", {})
            # 异环计划按北京时间凌晨五点切日，上游按本地零点判星期。
            # 周日计划跨到本地周一时，仅转换本次显式覆写，不改变继承值。
            if (
                now.astimezone(UTC3).weekday() == 6
                and now.weekday() == 0
                and weekly.get("每周开始运行日") is not None
            ):
                patch = {
                    **patch,
                    "anomaly_pilgrimage": {**weekly, "每周开始运行日": "周一"},
                }
        if name == DAILY_ROUTINE_TASK_FILE and "Routine Items" in patch:
            base = (
                json.loads(target.read_text(encoding="utf-8"))
                if target.is_file()
                else DEFAULT_CONFIG_DATA[name]
            )
            overrides = {item["id"]: item for item in patch["Routine Items"]}
            items = [
                dict(overrides.pop(item["id"], item)) for item in base["Routine Items"]
            ]
            patch = {**patch, "Routine Items": [*items, *overrides.values()]}
        update_oknte_config_data(target, patch)
