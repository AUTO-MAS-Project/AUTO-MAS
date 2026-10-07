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

import re

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


__all__ = ["OTHER_PROJECT", "telemetry_project_name"]
