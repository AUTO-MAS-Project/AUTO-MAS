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
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BetterGI 切换账号专项适配。

将上游脚本「切换账号多模式」(SwitchAccountMultipleMode) 内置为 MAS 资源，
运行时把脚本部署到 BetterGI 的 JsScript 目录，并按当前用户配置生成一个独立的
配置组 ``MAS切换账号``，供 ``BetterGI.exe --startGroups MAS切换账号`` 单独执行。

账号密码来源：MAS 用户配置 ``Info.Id`` / ``Info.Password``（密码已加密存储），
下拉列表模式下由 MAS 负责把完整手机号/邮箱转换为游戏下拉列表显示的打码形式。
"""

import shutil
from pathlib import Path
from typing import Any

from app.utils import get_logger
from app.utils.io import read_file, write_file

logger = get_logger("BetterGI 切换账号")

# 与 BetterGI 项目结构固定的相对路径（从 RootPath 派生）
_JS_SCRIPT_REL_DIR = Path("User") / "JsScript"
_SCRIPT_GROUP_REL_DIR = Path("User") / "ScriptGroup"

# 内置资源目录（随 MAS 版本同步）
_RES_TEMPLATE_DIR = Path.cwd() / "res" / "templates" / "BetterGI"

# 脚本文件夹名（BetterGI JsScript 下），须与配置组 template 的 folderName 一致。
# 追加 _MAS 后缀与上游订阅脚本 SwitchAccountMultipleMode 隔离，避免 BetterGI
# ScriptRepoUpdater 自动同步时删除 MAS 部署的副本。
_SCRIPT_FOLDER_NAME = "SwitchAccountMultipleMode_MAS"

# 生成的配置组名称（同时作为文件名与 --startGroups 的组名）
_GROUP_NAME = "MAS切换账号"

# 下拉列表模式下手机号/邮箱的打码规则（与游戏登录界面显示一致）
_PHONE_MASK_PREFIX = 3
_PHONE_MASK_SUFFIX = 2
_PHONE_DIGITS = 11


def mask_account(account: str) -> str:
    """把完整账号转换为游戏下拉列表显示的打码形式。

    手机号 ``13812345678`` → ``138******78``（前3 + 6个* + 后2）
    邮箱 ``11abc1@919.com`` → ``11****1@919.com``（@前 前2 + **** + 最后1位）
    第三方登录（如 ``apple``）→ 原样返回。
    """
    account = (account or "").strip()
    if not account:
        return ""

    if "@" in account:
        local, _, domain = account.partition("@")
        if len(local) <= 2:
            # 本地部分过短，无法打码，原样返回
            return account
        return f"{local[:2]}****{local[-1]}@{domain}"

    if account.isdigit() and len(account) == _PHONE_DIGITS:
        return f"{account[:_PHONE_MASK_PREFIX]}******{account[-_PHONE_MASK_SUFFIX:]}"

    return account


# 游戏服务器 → (是否国际服, 国际服服务器, 强制切换模式)
# 官服/B服 走国服登录（非国际服）；B服 强制走「B服切换另一个账号匹配+键鼠」模式
# （B服 无下拉列表/OCR 切换方式），其余服务器不强制（切换模式由密码是否填写决定）。
_RESOURCE_MAP: dict[str, tuple[bool, str, str | None]] = {
    "官服": (False, "不切换服务器", None),
    "B服": (False, "不切换服务器", "B服切换另一个账号匹配+键鼠"),
    "亚服": (True, "Asia", None),
    "欧服": (True, "Europe", None),
    "美服": (True, "America", None),
    "港澳台服": (True, "TW,HK,MO", None),
}


def resolve_switch_settings(resource: str, mode: str) -> tuple[bool, str, str]:
    """把「游戏服务器」翻译为切换账号脚本所需的三元组 (是否国际服, 服务器, 切换模式)。

    B服 强制走「B服切换另一个账号匹配+键鼠」模式；未知资源兜底为「官服」。
    """
    resource = (resource or "官服").strip()
    global_account, servers, forced_mode = _RESOURCE_MAP.get(
        resource, _RESOURCE_MAP["官服"]
    )
    if forced_mode is not None:
        mode = forced_mode
    return global_account, servers, mode


def _build_js_settings(
    account: str,
    password: str,
    mode: str,
    global_account: bool,
    servers: str,
    uid: str,
) -> dict[str, Any]:
    """组装配置组中 ``jsScriptSettingsObject``（即脚本 settings 注入对象）。"""
    # 下拉列表模式写打码账号；账号+密码模式写完整账号，由脚本 OCR 输入
    username = mask_account(account) if mode == "下拉列表" else account.strip()
    return {
        "Modes": mode,
        "username": username,
        "password": password,
        "GlobalAccount": global_account,
        "Servers": servers,
        "uid": uid,
    }


def deploy_switch_script(root_path: Path) -> Path:
    """把内置的切换账号脚本部署到 BetterGI 的 JsScript 目录（覆盖式，保证版本一致）。

    Returns:
        部署后的脚本目录路径。
    """
    src = _RES_TEMPLATE_DIR / _SCRIPT_FOLDER_NAME
    if not src.is_dir():
        raise FileNotFoundError(f"BetterGI 切换账号脚本资源缺失: {src}")

    dst = root_path / _JS_SCRIPT_REL_DIR / _SCRIPT_FOLDER_NAME
    # 目标已存在时直接合并覆盖，避免 BetterGI 运行中占用目录导致 rmtree 静默失败、
    # 进而 copytree 抛 FileExistsError（WinError 183）。
    shutil.copytree(src, dst, dirs_exist_ok=True)
    logger.info(f"已部署切换账号脚本: {dst}")
    return dst


def write_switch_group(
    root_path: Path,
    account: str,
    password: str,
    mode: str,
    global_account: bool,
    servers: str,
    uid: str,
) -> Path:
    """生成（覆盖）BetterGI 切换账号配置组 ``MAS切换账号``。

    Returns:
        写入的配置组 JSON 文件路径。
    """
    template_path = _RES_TEMPLATE_DIR / f"{_GROUP_NAME}.json"
    template = read_file(template_path)
    if not isinstance(template, dict) or not isinstance(template.get("projects"), list):
        raise RuntimeError(f"切换账号配置组模板无效: {template_path}")

    template["name"] = _GROUP_NAME
    template["index"] = 999
    template["projects"][0]["jsScriptSettingsObject"] = _build_js_settings(
        account, password, mode, global_account, servers, uid
    )

    out_path = root_path / _SCRIPT_GROUP_REL_DIR / f"{_GROUP_NAME}.json"
    write_file(out_path, template)
    logger.info(f"已生成切换账号配置组: {out_path} (账号 {mask_account(account)})")
    return out_path


def scrub_switch_group(root_path: Path) -> None:
    """运行结束后脱敏切换账号配置组，清空密码并把账号置为打码形式。

    切号脚本执行时必须写入明文账号/密码供 OCR/键鼠登录，但完成后不应让明文
    凭据残留磁盘。本函数把 ``jsScriptSettingsObject`` 的 ``password`` 清空、
    ``username`` 还原为打码（下拉列表模式本已是打码，OCR 模式的完整账号被抹掉）。
    """
    out_path = root_path / _SCRIPT_GROUP_REL_DIR / f"{_GROUP_NAME}.json"
    data = read_file(out_path)
    if not isinstance(data, dict):
        return
    for proj in data.get("projects") or []:
        if not isinstance(proj, dict):
            continue
        settings = proj.get("jsScriptSettingsObject")
        if not isinstance(settings, dict):
            continue
        settings["password"] = ""
        settings["username"] = mask_account(str(settings.get("username") or ""))
    write_file(out_path, data)
    logger.info(f"已脱敏切换账号配置组: {out_path}")
