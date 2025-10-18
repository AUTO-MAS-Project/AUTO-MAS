#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import json
from pathlib import Path
from app.core import Config


async def agree_bilibili(maa_tasks_path: Path, if_agree: bool):
    """向MAA写入Bilibili协议相关任务"""

    data: dict = json.loads(maa_tasks_path.read_text(encoding="utf-8"))
    if if_agree and Config.get("Function", "IfAgreeBilibili"):
        data["BilibiliAgreement_AUTO"] = {
            "algorithm": "OcrDetect",
            "action": "ClickSelf",
            "text": ["同意"],
            "maxTimes": 5,
            "Doc": "关闭B服用户协议",
            "next": ["StartUpThemes#next"],
        }
        if "BilibiliAgreement_AUTO" not in data["StartUpThemes"]["next"]:
            data["StartUpThemes"]["next"].insert(0, "BilibiliAgreement_AUTO")
    else:
        if "BilibiliAgreement_AUTO" in data:
            data.pop("BilibiliAgreement_AUTO")
        if "BilibiliAgreement_AUTO" in data["StartUpThemes"]["next"]:
            data["StartUpThemes"]["next"].remove("BilibiliAgreement_AUTO")
    maa_tasks_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
    )
