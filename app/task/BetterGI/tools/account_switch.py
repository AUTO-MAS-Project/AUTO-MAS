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

通过 BetterGI 的脚本仓库（ScriptRepoUpdater）管理「切换账号多模式」脚本，不再随
MAS 内置冻结副本：MAS 只写订阅清单，由 BetterGI 把脚本更新到
``User/JsScript/SwitchAccountMultipleMode``。切号/一条龙的「运行前先同步更新、更新完成
再执行」特性当前已冻结（见 ``_UPDATE_REPO_BEFORE_RUN``，仅保留后台自动更新与误删恢复）。
MAS 按当前用户配置生成一个独立的配置组 ``MAS切换账号``，供
``BetterGI.exe --startGroups MAS切换账号`` 单独执行。

- 订阅清单: ``{RootPath}/User/Subscriptions/bettergi-scripts-list.json`` = 路径数组
- 自动更新: ``{RootPath}/User/config.json`` 的 ``ScriptConfig`` 三个开关（两个自动更新开关 +
  ``selectedChannelName = "CNB"`` 固定仓库渠道为 BetterGI 官方 cnb.cool 镜像，无需境外源）
- 检出目标: ``{RootPath}/User/JsScript/SwitchAccountMultipleMode``
- 误删恢复/初次使用: 脚本本地缺失时删除中央仓库副本
  ``{RootPath}/Repos/bettergi-scripts-list``，BGI 下次启动完整重建并重新检出已订阅脚本。
  因为 ``OnDeleteScript`` 只删脚本目录、不取消订阅，BGI 每次更新都会对已订阅脚本无条件
  重检出，即便仓库「已是最新」也会把误删后的目录补回来。

账号密码来源：MAS 用户配置 ``Info.Id`` / ``Info.Password``（密码已加密存储），
下拉列表模式下由 MAS 负责把完整手机号/邮箱转换为游戏下拉列表显示的打码形式。
"""

import shutil
from pathlib import Path
from typing import Any

from app.utils import get_logger
from app.utils.io import read_file, write_file

from .one_dragon import GLOBAL_CONFIG_LOCK

logger = get_logger("BetterGI 切换账号")

# 生成并执行的配置组名称（同时作为文件名与 --startGroups 的组名）
GROUP_NAME = "MAS切换账号"

# 与 BetterGI 项目结构固定的相对路径（从 RootPath 派生）
_JS_SCRIPT_REL_DIR = Path("User") / "JsScript"
_SCRIPT_GROUP_REL_DIR = Path("User") / "ScriptGroup"

# 内置资源目录（随 MAS 版本同步；含配置组模板，脚本本体不再内置）
_RES_TEMPLATE_DIR = Path.cwd() / "res" / "templates" / "BetterGI"

# 切换账号脚本在 BetterGI 脚本仓库中的相对路径（repo 下），"js" 前缀映射到 User/JsScript
_SCRIPT_REPO_PATH = "js/SwitchAccountMultipleMode"
# 仓库检出到 User/JsScript 下的文件夹名，须与配置组 template 的 folderName 一致
_SCRIPT_FOLDER_NAME = "SwitchAccountMultipleMode"

# BetterGI 脚本仓库（ScriptRepoUpdater）控制相对路径
#   仓库目录: {RootPath}/Repos/bettergi-scripts-list（真实 git 克隆）
#   订阅清单: {RootPath}/User/Subscriptions/bettergi-scripts-list.json = ["js/..."]
_REPO_FOLDER_NAME = "bettergi-scripts-list"

# BetterGI 中央脚本仓库本地副本: {RootPath}/Repos/bettergi-scripts-list（桌面元数据缓存）。
# 用户误删脚本 / 初次使用脚本缺失时，删掉它可在 BGI 下次启动触发完整重建，从而把
# 检出的脚本连同缺失的切换账号脚本一起拉回来。
_REPO_REL_DIR = Path("Repos") / _REPO_FOLDER_NAME
_SUBSCRIPTION_REL_DIR = Path("User") / "Subscriptions"
# BetterGI 主配置: {RootPath}/User/config.json，ScriptConfig 段开启自动更新
_BGI_CONFIG_REL_PATH = Path("User") / "config.json"

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


def switch_script_dir(root_path: Path) -> Path:
    """切换账号脚本经 BetterGI 仓库检出后的本地部署目录。"""
    return root_path / _JS_SCRIPT_REL_DIR / _SCRIPT_FOLDER_NAME


def _ensure_script_subscription(root_path: Path) -> Path:
    """合并订阅清单，返回订阅文件路径。

    把 ``_SCRIPT_REPO_PATH`` 追加进 ``User/Subscriptions/{仓库名}.json``（路径数组），
    保留用户已订阅的其他脚本；由 BetterGI ScriptRepoUpdater 据此拉取/更新。
    """
    sub_path = root_path / _SUBSCRIPTION_REL_DIR / f"{_REPO_FOLDER_NAME}.json"
    data = read_file(sub_path)
    subscribed = [str(x) for x in data] if isinstance(data, list) else []
    if _SCRIPT_REPO_PATH not in subscribed:
        subscribed.append(_SCRIPT_REPO_PATH)
    write_file(sub_path, subscribed)
    logger.info(f"已订阅切换账号脚本: {_SCRIPT_REPO_PATH} -> {sub_path}")
    return sub_path


# 「命令行运行前先同步更新脚本仓库、更新完成后再执行任务」特性开关。
# 暂时冻结：当前发现该特性已无必要——每次 CLI 启动前的同步更新会拖慢启动，
# 且切号脚本已能通过后台自动更新（autoUpdateSubscribedScripts）与误删恢复补位。
# 若日后出现脚本缺失却未被后台拉回等真实 bug，再把本常量置 True 重新启用。
_UPDATE_REPO_BEFORE_RUN = False


def _ensure_auto_update_on_cli(root_path: Path) -> Path:
    """配置 BetterGI 脚本仓库自动更新并把渠道固定为 CNB，返回主配置文件路径。

    ``{RootPath}/User/config.json`` 的 ``ScriptConfig`` 置：
    - ``autoUpdateBeforeCommandLineRun = _UPDATE_REPO_BEFORE_RUN``：命令行启动
      （切号/一条龙）是否先同步更新仓库脚本再执行。当前冻结停用（False），
      届时若重新启用改回 True。
    - ``autoUpdateSubscribedScripts = true``：普通启动时也后台更新已订阅脚本（兜底）
    - ``selectedChannelName = "CNB"``：脚本仓库固定从 BetterGI 官方 cnb.cool 镜像
      ``https://cnb.cool/bettergi/bettergi-scripts-list`` 拉取/更新。CNB 本就是
      ScriptRepoUpdater 的默认渠道，但用户若在 BGI GUI 里选了 GitHub 会盖过默认回境外源，
      这里显式钉死，避免切号脚本又从 GitHub 下载。
    """
    config_path = root_path / _BGI_CONFIG_REL_PATH
    with GLOBAL_CONFIG_LOCK:
        config = read_file(config_path)
        if not isinstance(config, dict):
            config = {}
        # 统一写到 camelCase 键（BetterGI JsonOptions 以 CamelCase 读写，PascalCase 键读取时会被忽略）
        script_cfg = config.get("scriptConfig")
        if not isinstance(script_cfg, dict):
            legacy = config.get("ScriptConfig")  # 兼容历史 PascalCase 键，合并后弃用
            script_cfg = legacy if isinstance(legacy, dict) else {}
        script_cfg["autoUpdateBeforeCommandLineRun"] = _UPDATE_REPO_BEFORE_RUN
        script_cfg["autoUpdateSubscribedScripts"] = True
        script_cfg["selectedChannelName"] = "CNB"
        config.pop("ScriptConfig", None)
        config["scriptConfig"] = script_cfg
        write_file(config_path, config)
    logger.info(
        f"已配置 BetterGI 脚本仓库自动更新(运行时预更新={'启用' if _UPDATE_REPO_BEFORE_RUN else '已冻结'})"
        f"，渠道 CNB: {config_path}"
    )
    return config_path


def ensure_switch_subscription(root_path: Path) -> bool:
    """确保切换账号脚本被订阅，缺失时强制重建，返回脚本本地是否已就绪。

    BGI 负责按订阅更新仓库脚本（运行前同步更新已冻结，改走后台
    ``autoUpdateSubscribedScripts``），故这里只需保证订阅就绪即可，
    删除/初次使用两种情况都会被 BGI 自动重新检出：

    - 覆盖式写入订阅清单（``js/SwitchAccountMultipleMode``）并开启自动更新，
      保留用户已有订阅项与其余配置。BGI 更新逻辑对每个已订阅路径无条件重检出，
      即使仓库「已是最新」也会补回被误删的脚本目录。
    - 若切换账号脚本当前本地缺失（用户误删、或初次使用从未检出），删除本地中央
      仓库副本 ``Repos/bettergi-scripts-list``，强制 BGI 下次启动完整重建仓库并
      重检出全部已订阅脚本，确定性地把缺失的切号脚本拉回来，避免依赖 BGI 磁盘
      缓存快捷路径导致一直不补位。

    Returns:
        切换账号脚本当前是否已存在于本地（帮助日志判断是已就绪还是将现拉取）。
    """
    try:
        _ensure_script_subscription(root_path)
        _ensure_auto_update_on_cli(root_path)
        if not switch_script_dir(root_path).is_dir():
            # 脚本缺失（用户误删/初次使用）：清掉本地仓库，逼 BGI 下次启动整体重建
            repo_dir = root_path / _REPO_REL_DIR
            if repo_dir.is_dir():
                shutil.rmtree(repo_dir, ignore_errors=True)
                logger.info(f"切换账号脚本缺失，已清理本地脚本仓库强制重建: {repo_dir}")
    except Exception as e:
        logger.opt(exception=True).warning(f"切换账号脚本仓库订阅设置失败: {e}")
        raise
    return switch_script_dir(root_path).is_dir()


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

    ``folderName`` 固定指向脚本仓库检出目录 ``SwitchAccountMultipleMode``，与
    ``ensure_switch_subscription`` 对齐；``jsScriptSettingsObject`` 按用户注入。
    Returns:
        写入的配置组 JSON 文件路径。
    """
    template_path = _RES_TEMPLATE_DIR / f"{GROUP_NAME}.json"
    template = read_file(template_path)
    if not isinstance(template, dict) or not isinstance(template.get("projects"), list):
        raise RuntimeError(f"切换账号配置组模板无效: {template_path}")

    project = template["projects"][0]
    if not isinstance(project, dict):
        raise RuntimeError(f"切换账号配置组模板缺 projects[0]: {template_path}")
    project["folderName"] = _SCRIPT_FOLDER_NAME
    project["jsScriptSettingsObject"] = _build_js_settings(
        account, password, mode, global_account, servers, uid
    )

    out_path = root_path / _SCRIPT_GROUP_REL_DIR / f"{GROUP_NAME}.json"
    write_file(out_path, template)
    logger.info(f"已生成切换账号配置组: {out_path} (账号 {mask_account(account)})")
    return out_path


def scrub_switch_group(root_path: Path) -> None:
    """运行结束后脱敏切换账号配置组，清空密码并把账号置为打码形式。

    切号脚本执行时必须写入明文账号/密码供 OCR/键鼠登录，但完成后不应让明文
    凭据残留磁盘。本函数把 ``jsScriptSettingsObject`` 的 ``password`` 清空、
    ``username`` 还原为打码（下拉列表模式本已是打码，OCR 模式的完整账号被抹掉）。
    """
    out_path = root_path / _SCRIPT_GROUP_REL_DIR / f"{GROUP_NAME}.json"
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
