#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""遥测里 MFW 项目的上报名：只认公开项目，其余一律 ``other``。

interface.json 的 ``name`` / ``label`` 是自由文本，用户自建的私有项目也会写，
不能原样上报。这里按 ``github`` 字段对白名单，命中就报仓库的 ``owner/repo``。

白名单取自 MaaFramework README「社区项目 → 应用程序」（2026-10-05），
新项目没进名单只会被记成 ``other``，补一行即可。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

OTHER_PROJECT = "other"

_KNOWN_PROJECT_REPOS = (
    "MaaXYZ/M9A",
    "overflow65537/MAA_SnowBreak",
    "TanyaShue/MaaYYs",
    "overflow65537/MAA_Punish",
    "Saratoga-Official/MRA",
    "syoius/MaaYuan",
    "KarylDAZE/Maa-HBR",
    "DarkLingYun/MaaGF2Exilium",
    "ravizhan/MaaXuexi",
    "gitlihang/Maa_MHXY_MG",
    "Coxwtwo/MaaTOT",
    "KhazixW2/MaaGumballs",
    "fictionalflaw/MMleo",
    "miaojiuqing/SLIMEIM_Maa",
    "miaojiuqing/Maa_bbb",
    "duorua/narutomobile",
    "SuperWaterGod/MaaGakumasu",
    "233Official/MaaStarResonance",
    "Kazaorus/MAG",
    "NewWYoming/MAAAE",
    "quietlysnow/MBCCtools",
    "Tigerisu/MaaEOV",
    "26F-Studio/maa-star-resonance",
    "SodaCodeSave/StellaSora-Auto-Helper",
    "kqcoxn/MaaDuDuL",
    "Witty36/MaaLYSK",
    "MaaEnd/MaaEnd",
    "PinkMMF/MaaGFNeuralCloud",
    "xlxyvergil/MaaFgo",
    "1bananachicken/MaaNTE",
    "lisadnsess/MALostWord",
    "originalsage/MR3A",
    "miaojiuqing/Maa_Kes",
    "Hollow-YK/MaaAssistantKedrgame",
    "Quartewe/MAH",
    "NotZoruak/MATR",
    "Azureetude/MaaADr",
    "sunyink/MFABD2",
    "huzesama/MaaWoA",
    "Guili-Ad/MAES",
)

# 迁过仓库的项目：interface.json 里还写着旧地址
_REPO_ALIASES = {
    "maa1999/m9a": "MaaXYZ/M9A",
}

_PROJECT_BY_REPO = {
    **{repo.lower(): repo for repo in _KNOWN_PROJECT_REPOS},
    **_REPO_ALIASES,
}

_GITHUB_REPO_RE = re.compile(
    r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", re.IGNORECASE
)


def telemetry_project_name(github: object) -> str:
    """把 interface.json 的 ``github`` 地址映射成上报用的项目名。"""

    if not isinstance(github, str):
        return OTHER_PROJECT
    match = _GITHUB_REPO_RE.search(github.strip())
    if match is None:
        return OTHER_PROJECT
    repo = f"{match.group(1)}/{match.group(2)}".lower()
    return _PROJECT_BY_REPO.get(repo, OTHER_PROJECT)


async def record_project_run(project_path: Path | None, *, script_type: str) -> None:
    """记一次项目运行（``auto_mas.maafw.project.runs``）：项目名按 interface 的 ``github`` 对白名单，
    读不出（``project_path`` 为 None、interface 读失败）记 ``other``。遥测失败不影响任务。

    ``project_path`` 是这次运行的有效根（调用方解析好，解析出错传 None）；``script_type`` 是专项的
    上报名（通用 MFW ``MaaFW``、``M9A``、``MSS``）。interface 在工作线程里读（走核心包缓存）。
    """

    from app.services import telemetry as _service_telemetry

    try:
        if project_path is None:
            raise ValueError("没有项目路径")
        from app.task.MaaFW.blocks.maafw_interface.interface import (
            load_interface_model_cached,
        )

        interface = await asyncio.to_thread(load_interface_model_cached, project_path)
        project = telemetry_project_name(getattr(interface, "github", None))
    except Exception:  # noqa: BLE001 - 遥测失败不影响任务
        project = OTHER_PROJECT
    _service_telemetry.record_count(
        "auto_mas.maafw.project.runs",
        attributes={"project": project, "script_type": script_type},
    )


__all__ = ["OTHER_PROJECT", "record_project_run", "telemetry_project_name"]
