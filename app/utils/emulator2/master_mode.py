#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""Emulator 2.0 的「大雷主人模式」。

沿用全局 ``Function.IfBlockAd`` 开关，启动时应用或恢复设置；失败只记警告。
雷电分三层：安装级 ``globalsetting --cleanmode`` 管安卓桌面，VM 冷启动后生效，游戏中心仍可打开；
宿主窗口那层（加载页轮播、开机全屏页）``cleanmode`` 管不到，走渠道配置
``data\\data.ini`` 的 ``adshow`` / ``launchadshow``，见 :func:`apply_ldplayer_data_ini`；
Windows 桌面右下角的推广弹窗又是另一个进程，前两层都管不到，见 :func:`apply_ldplayer_partner`。
MuMu 处理宿主缓存及五个桌面组件，关闭时撤销占位并恢复组件；组件状态跨重启保留。
``MuMuManager sh`` 不要求开启 ``root_permission``；组件必须用 ``pm disable``，
``pm disable-user`` 会静默返回 default，不能代替。

宿主层（雷电 ``data.ini`` 与弹窗程序、MuMu 缓存占位）跟着安装走：MuMu 的小程序弹窗由常驻的
``MuMuNxService.exe`` 在实例启动等事件时用 ``ProgramAds`` 里缓存好的图直接画，多开器手动
起实例也会弹；雷电的桌面弹窗由系统服务定时拉起，连实例都不用开。所以门面在起这条配置里的
任一台设备前对每条安装调一次 :func:`apply_host_mode`，而不是只在起对应实例时处理。
"""

import os
import shutil
from pathlib import Path

from app.utils import get_logger

logger = get_logger("Emulator2 大雷主人模式")

#: MuMu 6 商店包名与模式管理的五个桌面组件。
MUMU_STORE_PACKAGE = "com.mumu.store"
MUMU_MODE_COMPONENTS: tuple[str, ...] = (
    "com.mumu.store.widget.appWidgetProvider.AdBannerWidgetProvider",
    "com.mumu.store.widget.appWidgetProvider.DailyDiscoveryWidgetProvider",
    "com.mumu.store.widget.appWidgetProvider.HotActivityWidgetProvider",
    "com.mumu.store.widget.appWidgetProvider.FlashSaleWidgetProvider",
    "com.mumu.login_handler.LoginServerReceiver",
)

#: MuMu 6 的安卓桌面（魔改 Lawnchair）。组件状态变了之后要重启它才会重画。
MUMU_LAUNCHER_PACKAGE = "app.lawnchair"

#: 一条 ``MuMuManager sh`` 最多等多久。它底层的 ``NemuShell.exe`` 连不上管道会**无限重试**，
#: 见过一次卡死，所以必须带超时；正常一批 pm 命令一两秒就完。
MUMU_SH_TIMEOUT = 20.0

#: ``MuMuManager sh`` 超时后要顺手清掉的孤儿进程名。
MUMU_SH_HELPER_IMAGE = "NemuShell.exe"


def is_master_mode_enabled() -> bool:
    """从旧版全局开关读取「大雷主人模式」状态，读取失败按关闭处理。"""
    try:
        from app.core import Config

        return bool(Config.get("Function", "IfBlockAd"))
    except Exception as e:  # noqa: BLE001 - 配置层的问题不该拖垮启动
        logger.warning(f"读取「大雷主人模式」配置失败，按关闭处理: {e}")
        return False


# ---- 雷电 ----------------------------------------------------------------


def ldplayer_clean_mode_args(enabled: bool) -> tuple[str, ...]:
    """``ldconsole globalsetting --cleanmode 1|0`` 的参数。"""
    return ("globalsetting", "--cleanmode", "1" if enabled else "0")


#: 雷电渠道配置 ``<安装目录>\data\data.ini`` 里管宿主窗口推广位的两个键。
#: ``dnplayer.exe`` 每次实例启动都用 ``GetPrivateProfileStringW`` 读 ``[setting]`` 段：
#: 缺省当 ``1``，只有字面 ``0`` 算关；``adshow`` 是总闸，``launchadshow`` 单管加载页轮播，
#: 两个都要为 ``0`` 加载页才不画。定制版安装包就是靠这个文件关推广的。
LDPLAYER_HOST_KEYS: tuple[str, ...] = ("adshow", "launchadshow")

#: 记录本模式往 ``data.ini`` 写过哪些键及其原值，关闭时只撤自己写的：
#: 渠道自带的 ``0`` 不动，用户显式写的 ``1`` 原样还回去。
LDPLAYER_MARKER_KEY = "automas_master_mode"

#: 标记值里「原来没有这个键」的写法。
_LDPLAYER_ABSENT = "-"

_LDPLAYER_SECTION = "setting"


def ldplayer_data_ini_path(install_dir: Path) -> Path:
    """雷电渠道配置的位置：``ldconsole.exe`` 所在目录下的 ``data\\data.ini``。"""
    return install_dir / "data" / "data.ini"


def _ini_value(raw: str) -> str:
    """按 ``GetPrivateProfileString`` 的口径取值：去首尾空白，再去一层成对引号。"""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def _split_ini(text: str) -> list[tuple[str | None, str | None, str]]:
    """把 INI 拆成 ``(所在段, 键, 原始行)``；段与键都已 casefold，非键行的键为 ``None``。"""
    rows: list[tuple[str | None, str | None, str]] = []
    section: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().casefold()
            rows.append((section, None, line))
            continue
        key: str | None = None
        if "=" in line and not stripped.startswith((";", "#")):
            key = line.split("=", 1)[0].strip().casefold()
        rows.append((section, key, line))
    return rows


def apply_ldplayer_data_ini(path: Path, enabled: bool) -> bool:
    """按开关写入或撤销 ``data.ini`` 里的宿主推广开关，返回文件是否被改动。

    开着：把 :data:`LDPLAYER_HOST_KEYS` 都写成 ``0``，并用 :data:`LDPLAYER_MARKER_KEY`
    记下每个键的原值（没有就记 ``-``）；标记已存在时不重写，免得把自己写的 ``0`` 当原值。
    关着：只在有标记时动手，按标记把键删掉或还回原值，再去掉标记；没标记说明从没开过，
    文件一个字都不碰。文件本身按原编码写回（有 UTF-16 BOM 就保持 UTF-16，否则按字节
    原样保留），新行统一 CRLF，写临时文件后替换。
    """
    raw = path.read_bytes() if path.is_file() else b""
    utf16 = raw.startswith(b"\xff\xfe")
    text = raw.decode("utf-16") if utf16 else raw.decode("latin-1")
    rows = _split_ini(text)

    in_section = [i for i, (sec, _, _) in enumerate(rows) if sec == _LDPLAYER_SECTION]
    current: dict[str, str] = {}
    key_rows: dict[str, int] = {}
    for i in in_section:
        _, key, line = rows[i]
        if key is not None:
            key_rows[key] = i
            current[key] = _ini_value(line.split("=", 1)[1])

    if enabled:
        if LDPLAYER_MARKER_KEY not in current:
            originals = {
                key: current.get(key, _LDPLAYER_ABSENT) for key in LDPLAYER_HOST_KEYS
            }
            if all(v == "0" for v in originals.values()):
                return False  # 渠道包本来就关着，不留标记，关闭模式时也不用还
            marker = ",".join(f"{k}:{v}" for k, v in originals.items())
            wanted = {key: "0" for key in LDPLAYER_HOST_KEYS}
            wanted[LDPLAYER_MARKER_KEY] = marker
        else:
            wanted = {key: "0" for key in LDPLAYER_HOST_KEYS}
        if all(current.get(k) == v for k, v in wanted.items()):
            return False
        remove: set[str] = set()
    else:
        marker = current.get(LDPLAYER_MARKER_KEY)
        if marker is None:
            return False
        wanted = {}
        remove = {LDPLAYER_MARKER_KEY}
        for item in marker.split(","):
            key, _, original = item.partition(":")
            key = key.strip().casefold()
            if key not in LDPLAYER_HOST_KEYS:
                continue
            if original == _LDPLAYER_ABSENT:
                remove.add(key)
            else:
                wanted[key] = original

    lines: list[str | None] = [line for _, _, line in rows]
    for key in remove:
        if key in key_rows:
            lines[key_rows[key]] = None
    new_lines: list[str] = []
    for key, value in wanted.items():
        if key in key_rows:
            lines[key_rows[key]] = f"{key}={value}"
        else:
            new_lines.append(f"{key}={value}")
    if new_lines:
        # 插在 [setting] 段末尾；没有这个段就在文件末尾补一个
        if in_section:
            last = in_section[-1]
            lines[last + 1 : last + 1] = new_lines
        else:
            lines.extend([f"[{_LDPLAYER_SECTION}]", *new_lines])
    output = "\r\n".join(line for line in lines if line is not None) + "\r\n"

    encoded = output.encode("utf-16") if utf16 else output.encode("latin-1")
    tmp = path.with_name(path.name + ".automas-tmp")
    tmp.write_bytes(encoded)
    os.replace(tmp, path)
    return True


#: 雷电 Windows 桌面推广弹窗的程序。系统服务 ``ldplayerservice.exe`` 每 30 分钟拉起一次它的
#: **改名副本**（``--fromserver``），跟有没有实例在跑无关；副本名安装时随机生成，记在
#: 安装目录的 ``partnername.data``（UTF-16LE 的一行文件名）。开机时服务还会从原件重新
#: copy 出副本，所以原件和副本都得处理。
LDPLAYER_PARTNER_EXE = "ldplayerpartner.exe"
LDPLAYER_PARTNER_NAME_FILE = "partnername.data"

#: 改名用的后缀。改名后服务只记一行 ``CreateProcessAsUser error:2``、20 秒后重试一次就放弃；
#: 自更新逻辑写在这个 exe 自己里面，服务不会把它下载回来，雷电本体升级时才会重新释放。
LDPLAYER_OFF_SUFFIX = ".automas-off"


def _decode_partner_name(raw: bytes) -> str:
    """``partnername.data`` 的内容：带不带 BOM 的 UTF-16LE 都见过，纯 ASCII 也认。"""
    if raw.startswith(b"\xff\xfe"):
        raw = raw[2:]
    text = (
        raw.decode("utf-16-le", "ignore") if b"\x00" in raw else raw.decode("latin-1")
    )
    return text.strip().strip("\x00").strip()


def ldplayer_partner_exes(install_dir: Path) -> list[Path]:
    """弹窗程序的原件和 ``partnername.data`` 指向的副本；副本名读不到或不像文件名就只有原件。"""
    paths = [install_dir / LDPLAYER_PARTNER_EXE]
    name_file = install_dir / LDPLAYER_PARTNER_NAME_FILE
    try:
        name = _decode_partner_name(name_file.read_bytes())
    except OSError:
        return paths
    lowered = name.casefold()
    if (
        not lowered.endswith(".exe")
        or Path(name).name != name
        or lowered == LDPLAYER_PARTNER_EXE
    ):
        return paths
    paths.append(install_dir / name)
    return paths


def apply_ldplayer_partner(install_dir: Path, enabled: bool) -> bool:
    """按开关给弹窗程序改名或改回来，返回是否真的动了文件。

    开着：原名存在就加 :data:`LDPLAYER_OFF_SUFFIX`；改名对正在运行的 exe 也成立。雷电升级
    重新释放过原名时，旧的改名件被新件顶掉，留下的始终是最新版。关着：只把自己改名的文件
    改回去；原名已经被雷电补回来时，旧的改名件就是多余的，删掉。任何一处失败只记警告。
    """
    changed = False
    for exe in ldplayer_partner_exes(install_dir):
        off = exe.with_name(exe.name + LDPLAYER_OFF_SUFFIX)
        try:
            if enabled:
                if exe.is_file():
                    os.replace(exe, off)
                    changed = True
            elif off.is_file():
                if exe.exists():
                    off.unlink()
                else:
                    os.replace(off, exe)
                changed = True
        except OSError as e:
            logger.warning(f"处理「大雷主人模式」弹窗程序失败 {exe}: {e}")
    return changed


# ---- MuMu：安卓端 ----------------------------------------------------------


def mumu_component_shell(enabled: bool) -> str:
    """一条 ``sh -c`` 里把五个组件一起禁用 / 启用。

    合成一条是为了只起一次 ``NemuShell.exe``：它连不上就无限重试，起五次就有五次机会卡住。
    """
    verb = "pm disable --user 0" if enabled else "pm enable"
    return "; ".join(
        f"{verb} {MUMU_STORE_PACKAGE}/{component}" for component in MUMU_MODE_COMPONENTS
    )


def mumu_component_applied(output: str, enabled: bool) -> bool:
    """从 ``pm disable`` / ``pm enable`` 的合并输出判断五条是否都落了。

    ``pm`` 每条成功都会打 ``new state: disabled``（或 ``enabled``）；少一条就是有组件没处理到。
    """
    wanted = "new state: disabled" if enabled else "new state: enabled"
    return output.count(wanted) >= len(MUMU_MODE_COMPONENTS)


# ---- MuMu：Windows 侧占位 --------------------------------------------------


def mumu_splash_placeholder_paths(appdata: Path | None = None) -> list[Path]:
    """MuMu 6 在 Windows 侧需要占位的缓存目录：小程序弹窗的 ``ProgramAds``。

    实例开屏图的 ``startupImage`` 不在这里：实测实例一启动 MuMu 就把占位文件删掉、重建目录并
    重新下载，占了也白占。
    """
    base = appdata if appdata is not None else Path(os.getenv("APPDATA") or "")
    return [base / "Netease" / "MuMuPlayer" / "data" / "ProgramAds"]


def apply_splash_placeholders(paths: list[Path], enabled: bool) -> bool:
    """占位或撤销占位，返回是否真的动了文件。

    开着：目录整个删掉、原地放一个同名空文件，MuMu 就写不进缓存图；实测常驻服务遇到文件
    不会把它改回目录，只记「no cache ads」。关着：只删我们放的那个空文件，目录让 MuMu 自己重建。
    任何一处失败只记警告，继续处理下一处。
    """
    changed = False
    for path in paths:
        try:
            if enabled:
                if path.is_file():
                    continue
                if path.is_dir():
                    shutil.rmtree(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                changed = True
            elif path.is_file():
                path.unlink()
                changed = True
        except OSError as e:
            logger.warning(f"处理「大雷主人模式」缓存占位失败 {path}: {e}")
    return changed


# ---- 安装级入口 ------------------------------------------------------------


def apply_host_mode(
    emulator_type: str, manager_exe: Path | None, enabled: bool
) -> bool:
    """按开关对齐**一条安装**的宿主层，返回是否有改动。

    宿主层跟着安装走，不跟着实例走：MuMu 的小程序弹窗由常驻的多开器在它自己启动时弹，
    雷电的加载页轮播由 ``dnplayer.exe`` 读安装目录的渠道配置、桌面弹窗由系统服务定时拉起，
    都和这次起的是哪台实例无关，所以门面在起这条配置里的任一台设备前，对配置下的每条安装
    都调一次。雷电的两层各自独立，一层失败不影响另一层。不认识的类型什么都不做。
    """
    if emulator_type == "mumu":
        return apply_splash_placeholders(mumu_splash_placeholder_paths(), enabled)
    if emulator_type == "ldplayer" and manager_exe is not None:
        install_dir = manager_exe.parent
        changed = apply_ldplayer_partner(install_dir, enabled)
        try:
            changed = (
                apply_ldplayer_data_ini(ldplayer_data_ini_path(install_dir), enabled)
                or changed
            )
        except OSError as e:
            logger.warning(f"处理「大雷主人模式」渠道配置失败 {install_dir}: {e}")
        return changed
    return False
