"""通用计划的所属关系与配置副本定位，不解释原生配置内容。"""

import shutil
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import UUID

from app.models.config import UniversalPlanConfig


def plan_directory(
    *,
    data_path: Path,
    plan: UniversalPlanConfig,
    script_id: str,
    user_id: str | None = None,
    runtime: bool = False,
    day: str | None = None,
    now: datetime | None = None,
) -> Path:
    if not isinstance(plan, UniversalPlanConfig):
        raise ValueError("所选配置不是通用脚本计划表")
    if plan.Info.ScriptId != UUID(script_id):
        raise ValueError("通用脚本计划表不属于当前脚本")
    group = day or plan.current_group(now or datetime.now().astimezone())
    if group != "ALL" and plan.day_group_of(group) != group:
        if not (group.startswith("Day") and plan.day_group_of(group[3:]) == group):
            raise ValueError("无效的计划日期")
    root = data_path / script_id / "Plans" / str(plan.uid) / group
    if runtime:
        root = root / "Users" / str(UUID(user_id or ""))
    return root / "ConfigFile"


def save_plan_config(
    *, source: Path, destination: Path, mode: Literal["File", "Folder"]
) -> None:
    """完整复制后再原子换入，失败时保留此前已保存的日期配置。"""
    from app.utils import io as config_io
    from app.utils.common.config.archive import archive_dir

    if mode == "Folder" and not source.is_dir():
        raise ValueError("脚本配置目录不存在，未保存计划配置")
    if mode == "File" and not source.is_file():
        raise ValueError("脚本配置文件不存在，未保存计划配置")
    if destination.is_dir():
        archive_dir(destination, destination.parent / "Backups")
    with TemporaryDirectory() as temporary:
        staging = Path(temporary) / "ConfigFile"
        if mode == "Folder":
            shutil.copytree(source, staging)
        else:
            staging.mkdir()
            shutil.copy(source, staging / source.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        config_io.swap_in_dir(staging, destination)
    archive_dir(destination, destination.parent / "Backups")
