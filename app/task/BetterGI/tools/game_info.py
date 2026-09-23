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

"""BetterGI 游戏客户端信息（路径透传 + 渠道识别）。

官服 / B服 / 国际服是三个独立客户端（账号体系互相隔离：B站账号只能登录B服
客户端），而 BetterGI 全局只配置一个游戏路径（``genshinStartConfig.installPath``）。
本模块提供：

- 渠道识别：安装目录 ``config.ini`` 的 ``[General] channel/cps``（B服
  ``channel=14 / cps=bilibili``，官服 ``channel=1``；国际服客户端主程序为
  ``GenshinImpact.exe`` 与官服/B服的 ``YuanShen.exe`` 天然可分），标记来自
  社区长期沿用的事实标准（1.6→5.x 多版本稳定）。
- 生效路径解析：用户级 ``Switch.GamePath``（留空跟随 BGI 全局配置）。

⚠️ 用户级路径是「临时覆盖」：MAS 按生效路径自行拉起游戏、BGI 启动后 attach
运行中的客户端（按进程名识别），**绝不写回 BetterGI 的全局配置**——
``installPath`` 是全局单值，写入会污染其他「跟随全局」的用户与 BGI 本体
（2026-09-23 实机：B服用户的推送把官服用户的生效客户端顶掉）。

键值属上游私有格式，只透传读写、不建平行模型；读取走严格解析（响亮失败）。
"""

from pathlib import Path

import psutil

from app.task.proxy_helpers import find_pids_by_name
from app.utils import get_logger
from app.utils.io import read_dict_file

logger = get_logger("BetterGI 游戏信息")

# BetterGI 主配置相对路径（与 account_switch._BGI_CONFIG_REL_PATH 一致）
_BGI_CONFIG_REL_PATH = Path("User") / "config.json"

# 渠道常量（与用户配置 Switch.Resource 的取值口径对齐）
CHANNEL_OFFICIAL = "官服"
CHANNEL_BILIBILI = "B服"
CHANNEL_GLOBAL = "国际服"


def detect_channel(game_exe: Path) -> str | None:
    """识别游戏客户端渠道，返回 官服 / B服 / 国际服，无法识别返回 None。

    - 主程序 ``GenshinImpact.exe`` → 国际服客户端（与国服 ``YuanShen.exe`` 天然可分）；
    - ``YuanShen.exe`` 读安装目录 ``config.ini`` 的 ``[General]``：
      ``cps`` 含 ``bilibili`` 或 ``channel=14`` → B服；``channel=1`` → 官服。
    """
    name = game_exe.name.casefold()
    if name == "genshinimpact.exe":
        return CHANNEL_GLOBAL
    if name != "yuanshen.exe":
        return None
    ini_path = game_exe.parent / "config.ini"
    try:
        text = ini_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning(f"读取游戏渠道配置失败（忽略渠道识别）: {ini_path} - {e}")
        return None
    channel = ""
    cps = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith((";", "#", "[")):
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        key = key.strip().casefold()
        if key == "channel":
            channel = value.strip()
        elif key == "cps":
            cps = value.strip().casefold()
    if "bilibili" in cps or channel == "14":
        return CHANNEL_BILIBILI
    if channel == "1":
        return CHANNEL_OFFICIAL
    logger.info(f"未能识别游戏渠道（config.ini channel={channel!r} cps={cps!r}）")
    return None


def read_game_info(
    root_path: Path, user_game_path: str = ""
) -> dict[str, str | None]:
    """读取 BetterGI 游戏客户端信息（供用户页透传展示）。

    Args:
        root_path: BetterGI 根目录。
        user_game_path: 用户级路径（非空时展示该路径的渠道标注）。

    Returns:
        dict: ``installPath``（生效路径：用户级优先，否则 BGI 全局）、
        ``globalPath``（BGI 全局原值）、``channel``（识别结果或 None）、
        ``source``（"用户" / "全局"）。
    """
    config_path = root_path / _BGI_CONFIG_REL_PATH
    data = read_dict_file(config_path)
    start_config = data.get("genshinStartConfig")
    global_path = (
        str(start_config.get("installPath") or "").strip()
        if isinstance(start_config, dict)
        else ""
    )
    user_path = str(user_game_path or "").strip()
    effective = user_path or global_path
    channel = detect_channel(Path(effective)) if effective else None
    return {
        "installPath": effective or None,
        "globalPath": global_path or None,
        "channel": channel,
        "source": "用户" if user_path else "全局",
    }


def resolve_game_exe(root_path: Path, user_game_path: str = "") -> Path:
    """解析任务运行使用的游戏主程序路径（用户级覆盖优先，临时生效）。

    用户填写了 ``Switch.GamePath`` 时直接返回该路径（MAS 自行拉起游戏、BGI
    attach 运行中的客户端，**不写 BetterGI 全局配置**）；未填写时透传返回
    BGI 全局配置路径。路径不存在时响亮报错。

    Raises:
        ConfigCorruptedError: BGI 配置损坏（严格解析，不静默降级）。
        RuntimeError: 未配置游戏路径或路径不存在。
    """
    user_path = str(user_game_path or "").strip()
    if user_path:
        game_exe = Path(user_path)
    else:
        config_path = root_path / _BGI_CONFIG_REL_PATH
        data = read_dict_file(config_path)
        start_config = data.get("genshinStartConfig")
        install_path = (
            str(start_config.get("installPath") or "").strip()
            if isinstance(start_config, dict)
            else ""
        )
        if not install_path:
            raise RuntimeError(
                f"未在 BetterGI 配置中找到游戏路径（{config_path} 的 "
                "genshinStartConfig.installPath），请先在 BetterGI 设置中配置游戏路径"
            )
        game_exe = Path(install_path)
    if not game_exe.is_file():
        raise RuntimeError(
            f"游戏路径不存在: {game_exe}，请检查 BetterGI 设置或该用户的游戏客户端配置"
        )
    return game_exe


def find_running_game_exe(process_names: tuple[str, ...]) -> Path | None:
    """按进程名查找运行中的游戏客户端，返回其 exe 路径；读不到路径返回 None。

    提权进程的路径读取可能被拒（AccessDenied）——返回 None 让调用方按
    「无法判断」处理，不参与一致性比较。
    """
    for name in process_names:
        for pid in find_pids_by_name(name):
            try:
                exe = psutil.Process(pid).exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            if exe:
                return Path(exe)
    return None


def same_path(left: Path, right: Path) -> bool:
    """Windows 路径一致性比较（大小写不敏感 + 规范化分隔符）。"""

    def normalize(path: Path) -> str:
        import os

        return os.path.normcase(os.path.normpath(str(path)))

    return normalize(left) == normalize(right)
