"""OK-WW 普通模式启动参数。"""

import json
from pathlib import Path

from packaging.version import InvalidVersion, Version

from app.task.proxy_helpers import split_args


def build_custom_arguments(arguments: str) -> list[str]:
    """按原样拆分用户参数，不补充或替换选项。"""
    return split_args(arguments)


def daily_task_argument(script_root: Path) -> str:
    """按已安装版本选择上游支持的日常任务参数。"""
    app_config = json.loads(
        (script_root / "data/apps/ok-ww/app.json").read_text(encoding="utf-8-sig")
    )
    if not isinstance(app_config, dict):
        raise ValueError("OK-WW 启动器配置格式错误，请先在脚本启动器中完成安装或更新")
    raw_version = app_config.get("current_version")
    try:
        version = Version(str(raw_version))
    except InvalidVersion as exc:
        raise ValueError(
            "无法识别 OK-WW 当前版本，请先在脚本启动器中完成安装或更新"
        ) from exc
    # 上游 f09ac771（ok-script 2.0.7b1）；首个含此变更的预发布 tag。
    return "DailyTask" if version >= Version("3.6.7b2") else "1"
