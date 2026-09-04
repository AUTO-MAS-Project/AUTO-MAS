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
再执行」特性当前已冻结停用（仅保留后台自动更新与误删恢复）。
MAS 按当前用户配置生成一个独立的配置组 ``MAS切换账号``，供
``BetterGI.exe --startGroups MAS切换账号`` 单独执行。

- 订阅清单: ``{RootPath}/User/Subscriptions/bettergi-scripts-list.json`` = 路径数组
- 自动更新: ``{RootPath}/User/config.json`` 的 ``ScriptConfig`` 三个开关（两个自动更新开关 +
  ``selectedChannelName = "CNB"`` 固定仓库渠道为 BetterGI 官方 cnb.cool 镜像，无需境外源）
- 检出目标: ``{RootPath}/User/JsScript/SwitchAccountMultipleMode``
- 误删恢复/初次使用: 脚本本地缺失时只保证订阅就绪，交给 BGI 启动后的后台自动更新补位
  （``OnDeleteScript`` 只删脚本目录、不取消订阅，BGI 对已订阅脚本无条件重检出）。
  仅当上一轮 BGI 运行结束后脚本仍缺失（MAS 侧记录的检出失败标记，见
  ``record_switch_checkout_result``），下一轮才删除中央仓库副本
  ``{RootPath}/Repos/bettergi-scripts-list`` 强制完整重建；首次启用不会删用户已有仓库。

账号密码来源：MAS 用户配置 ``Info.Id`` / ``Info.Password``（密码已加密存储），
下拉列表模式下由 MAS 负责把完整手机号/邮箱转换为游戏下拉列表显示的打码形式。
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils import get_logger, resource_path
from app.utils.io import read_file, write_file

from .one_dragon import GLOBAL_CONFIG_LOCK

logger = get_logger("BetterGI 切换账号")

# 生成并执行的配置组名称（同时作为文件名与 --startGroups 的组名）
GROUP_NAME = "MAS切换账号"

# 与 BetterGI 项目结构固定的相对路径（从 RootPath 派生）
_JS_SCRIPT_REL_DIR = Path("User") / "JsScript"
_SCRIPT_GROUP_REL_DIR = Path("User") / "ScriptGroup"

# 内置资源目录（随 MAS 版本同步；含配置组模板，脚本本体不再内置）
_RES_TEMPLATE_DIR = resource_path("templates", "BetterGI")

# 切换账号脚本在 BetterGI 脚本仓库中的相对路径（repo 下），"js" 前缀映射到 User/JsScript
_SCRIPT_REPO_PATH = "js/SwitchAccountMultipleMode"
# 仓库检出到 User/JsScript 下的文件夹名，须与配置组 template 的 folderName 一致
_SCRIPT_FOLDER_NAME = "SwitchAccountMultipleMode"

# BetterGI 脚本仓库（ScriptRepoUpdater）控制相对路径
#   仓库目录: {RootPath}/Repos/bettergi-scripts-list（真实 git 克隆）
#   订阅清单: {RootPath}/User/Subscriptions/bettergi-scripts-list.json = ["js/..."]
_REPO_FOLDER_NAME = "bettergi-scripts-list"

# BetterGI 中央脚本仓库本地副本: {RootPath}/Repos/bettergi-scripts-list（真实 git 克隆）。
# 只在「上一轮 BGI 运行后切换账号脚本仍缺失」时删掉它，逼 BGI 下次启动完整重建；
# 里面还有用户其他已订阅脚本，不能在首次使用的正常路径上删除。
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


def _checkout_failed_marker(script_id: str) -> Path:
    """「上一轮 BGI 运行后切换账号脚本仍缺失」标记文件路径。

    放在 MAS 自有数据目录 ``data/{script_id}/``（与 ``per_user_one_dragon_path`` 同根），
    不进 BGI 目录树：BGI 会枚举 ``User/JsScript`` 找脚本，且 BGI 重装不应丢失该状态。
    """
    return Path.cwd() / "data" / script_id / ".bettergi_switch_checkout_failed"


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


def _ensure_auto_update_on_cli(root_path: Path) -> Path:
    """配置 BetterGI 脚本仓库自动更新并把渠道固定为 CNB，返回主配置文件路径。

    ``{RootPath}/User/config.json`` 的 ``ScriptConfig`` 置：
    - ``autoUpdateBeforeCommandLineRun = false``：命令行启动
      （切号/一条龙）是否先同步更新仓库脚本再执行，当前冻结停用。
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
        script_cfg["autoUpdateBeforeCommandLineRun"] = False
        script_cfg["autoUpdateSubscribedScripts"] = True
        script_cfg["selectedChannelName"] = "CNB"
        config.pop("ScriptConfig", None)
        config["scriptConfig"] = script_cfg
        write_file(config_path, config)
    logger.info(
        "已配置 BetterGI 脚本仓库自动更新(运行时预更新=已冻结)，渠道 CNB: "
        f"{config_path}"
    )
    return config_path


def ensure_switch_subscription(root_path: Path) -> bool:
    """确保切换账号脚本被订阅，返回脚本本地是否已就绪。本函数不删除任何东西。

    BGI 负责按订阅更新仓库脚本（运行前同步更新已冻结，改走后台
    ``autoUpdateSubscribedScripts``），这里只覆盖式写入订阅清单
    （``js/SwitchAccountMultipleMode``）并开启自动更新，保留用户已有订阅项与其余配置。
    脚本缺失（用户误删/初次使用）时交给 BGI 启动后自动补位；是否需要强制重建仓库由
    ``rebuild_script_repo_if_checkout_failed`` 在杀掉旧 BGI 进程之后单独决定。

    Returns:
        切换账号脚本当前是否已存在于本地（帮助日志判断是已就绪还是将现拉取）。
    """
    try:
        _ensure_script_subscription(root_path)
        _ensure_auto_update_on_cli(root_path)
    except Exception as e:
        logger.opt(exception=True).warning(f"切换账号脚本仓库订阅设置失败: {e}")
        raise
    present = switch_script_dir(root_path).is_dir()
    if not present:
        logger.info("切换账号脚本本地缺失，等待 BGI 启动后按订阅自动补位")
    return present


def rebuild_script_repo_if_checkout_failed(root_path: Path, script_id: str) -> bool:
    """上一轮 BGI 运行后脚本仍缺失时，删除本地中央仓库副本强制 BGI 完整重建。

    只看 MAS 自有目录里的检出失败标记（由 ``record_switch_checkout_result`` 在上一轮
    切号结束后写入），首次启用不会触发；调用方须在杀掉旧 BGI 进程之后再调用，
    避免删掉仍被使用或正在克隆中的仓库。无论是否真的删了目录，标记都会清除，
    下一轮重新计数。

    Returns:
        本次是否执行了强制重建（用于向调度台说明本轮要完整重建仓库）。
    """
    marker = _checkout_failed_marker(script_id)
    if switch_script_dir(root_path).is_dir():
        marker.unlink(missing_ok=True)
        return False
    if not marker.exists():
        return False
    repo_dir = root_path / _REPO_REL_DIR
    if repo_dir.is_dir():
        shutil.rmtree(repo_dir, ignore_errors=True)
        logger.warning(
            f"上一轮 BGI 运行后切换账号脚本仍缺失，已清理本地脚本仓库强制重建: {repo_dir}"
        )
    else:
        logger.warning(
            "上一轮 BGI 运行后切换账号脚本仍缺失，本地脚本仓库也不存在，等待 BGI 重新克隆"
        )
    marker.unlink(missing_ok=True)
    return True


def record_switch_checkout_result(root_path: Path, script_id: str) -> bool:
    """切号结束（BGI 已退出）后记录脚本是否已检出，返回脚本当前是否存在。

    仍缺失说明 BGI 这一轮没有把脚本补回来（后台更新未完成、渠道不通、
    仓库损坏等），写下标记供下一轮 ``rebuild_script_repo_if_checkout_failed`` 判断；
    已存在则清除标记。
    """
    marker = _checkout_failed_marker(script_id)
    if switch_script_dir(root_path).is_dir():
        marker.unlink(missing_ok=True)
        return True
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    logger.warning(
        "本轮 BGI 运行后切换账号脚本仍缺失，已记录标记，下一轮将强制重建脚本仓库"
    )
    return False


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
