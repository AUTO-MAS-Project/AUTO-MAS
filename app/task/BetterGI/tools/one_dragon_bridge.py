#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BetterGI 一条龙：路径 B「MAS 自编排执行层」配置组与脚本资产渲染。

复用切号通道（``account_switch``）的成熟做法：把 Plan 写进配置组 ``MAS一条龙``
的 ``projects[0].jsScriptSettingsObject``，脚本本体（``MASOneDragon``）经
``User/JsScript/MASOneDragon`` 运行，由 ``BetterGI.exe --startGroups MAS一条龙``
单独执行。战斗 4 项在此直连执行层；日常 4 项由随后的一条龙（已过滤掉战斗 4 项）
承接，避免重复执行。
"""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from shutil import copy2
from typing import Any

from app.utils import get_logger, resource_path
from app.utils.io import read_file, write_file

logger = get_logger("BetterGI 一条龙执行层")

GROUP_NAME = "MAS一条龙"
SCRIPT_FOLDER_NAME = "MASOneDragon"

_GROUP_REL_DIR = Path("User") / "ScriptGroup"
_JS_SCRIPT_REL_DIR = Path("User") / "JsScript"
_RES_TEMPLATE_DIR = resource_path("templates", "BetterGI")
_SCRIPT_ASSET_DIR = _RES_TEMPLATE_DIR / "MASOneDragon"


def ensure_script_assets(root_path: Path) -> None:
    """把 MASOneDragon 脚本资产（main.js / manifest.json）复制到 BGI 的
    ``User/JsScript/MASOneDragon``。

    验证1 已坐实：本地脚本经配置组 ``folderName`` 引用即可运行，无需订阅；
    这里负责把自建脚本本体落到该目录。内容不变则不重写，避免无谓 IO。
    settings.json 必须部署：manifest 声明 ``settings_ui`` 后 BGI 才会把配置组的
    ``jsScriptSettingsObject``（Plan）注入为脚本 settings 全局，缺失则 main.js
    读到空 Plan 秒退（2026-09 实机排障结论）。
    """
    dst_dir = root_path / _JS_SCRIPT_REL_DIR / SCRIPT_FOLDER_NAME
    dst_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("main.js", "manifest.json", "settings.json"):
        src = _SCRIPT_ASSET_DIR / fname
        if not src.is_file():
            logger.warning(f"一条龙执行层脚本资产缺失，跳过复制: {src}")
            continue
        dst = dst_dir / fname
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            copy2(src, dst)
            logger.info(f"已部署一条龙执行层脚本资产: {dst}")


def write_one_dragon_group(root_path: Path, plan_steps: list[dict[str, Any]]) -> Path:
    """生成（覆盖）BetterGI 一条龙执行层配置组 ``MAS一条龙``。

    ``folderName`` 固定指向 ``MASOneDragon``，``jsScriptSettingsObject`` 注入 Plan
    （仅战斗 4 项 steps；日常 4 项不在此，由随后的一条龙承接）。
    Returns:
        写入的配置组 JSON 文件路径。
    """
    ensure_script_assets(root_path)
    template_path = _RES_TEMPLATE_DIR / f"{GROUP_NAME}.json"
    template = read_file(template_path)
    if not isinstance(template, dict) or not isinstance(template.get("projects"), list):
        raise RuntimeError(f"一条龙执行层配置组模板无效: {template_path}")
    project = template["projects"][0]
    if not isinstance(project, dict):
        raise RuntimeError(f"一条龙执行层配置组模板缺 projects[0]: {template_path}")
    project["folderName"] = SCRIPT_FOLDER_NAME
    # plan 必须以 JSON 字符串注入：BGI 的 settings 注入是 .NET 对象包装（实测
    # MAS_SETTINGS_KEYS 打出 GetType/ToString 等），JS 侧对嵌套值（steps/weeklyLeyLine）
    # 做属性访问会拿到 undefined，序列化成字符串后由 main.js safeParsePlan 解析。
    project["jsScriptSettingsObject"] = {
        "plan": json.dumps({"version": 1, "steps": plan_steps}, ensure_ascii=False)
    }
    out_path = root_path / _GROUP_REL_DIR / f"{GROUP_NAME}.json"
    write_file(out_path, template)
    logger.info(f"已生成一条龙执行层配置组: {out_path}（{len(plan_steps)} 步）")
    return out_path


def remove_one_dragon_group(root_path: Path) -> None:
    """运行结束后删除一条龙执行层配置组文件 ``User/ScriptGroup/MAS一条龙.json``。

    该配置组由 MAS 每次运行前重新生成，不属于用户资产；留着会常驻在 BGI 的配置组
    列表里干扰用户。脚本本体（``User/JsScript/MASOneDragon``）保留，不随配置组删除。
    """
    out_path = root_path / _GROUP_REL_DIR / f"{GROUP_NAME}.json"
    with suppress(OSError):
        out_path.unlink(missing_ok=True)
