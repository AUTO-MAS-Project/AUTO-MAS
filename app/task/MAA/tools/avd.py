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

"""MAA 在魔改 AVD 上的截图通道：冒充 MuMu 的截图接口。

MaaCore（v6.18.0 实测）对魔改 AVD 没有截图增强，走 adb 单次约 250 ms。它的 MuMu 通道
只是在配置的 MuMu 目录下 ``LoadLibrary`` ``shell\\sdk\\external_renderer_ipc.dll`` 再按名字
取四个函数，所以放一个自己写的同名 DLL（``res/avdshim``，读模拟器的截图共享内存
``SHM_videmulator<控制台端口>``）就能让 MaaCore 选中 MumuExtras，稳态 3 ms（预研 §5）。

MAA 侧的连接配置按 MAA 6.18.0 源码写（``MaaWpfGui/Configuration/Single/Settings/
ConnectSettings.cs``、``ConnectionExtra/Mumu12Extra.cs``、``Models/EmulatorConnectionExtra/
MuMu12Extra.cs``、MaaCore ``Controller/AdbController.cpp``）：

- ``Config = MuMuEmulator12``：连接预设设为 MuMu，MaaCore 才会测 MumuExtras；
- ``Extras.MuMuEmulator12 = {IsEnabled, EmulatorPath, EnableBridgeConnection, InstanceIndex}``：
  **``EnableBridgeConnection`` 必须开**——GUI 只在它开着时把 ``index`` 传给 MaaCore，
  否则 MaaCore 按地址端口反推 MuMu 实例号（``127.0.0.1:20031`` 会被算成 241），
  假 DLL 就去读一块不存在的共享内存；``InstanceIndex`` 填控制台端口（假 DLL 认 ≥ 5554 的
  值为端口）；
- ``TouchMode = MaaTouch``：官方镜像上 minitouch 打不开输入设备（预研 §6.9），而 MuMu 预设
  的默认触控 ``MumuExtras`` 要真 MuMu 的输入接口，假 DLL 不提供；
- ``AutoDetect = false``：不让 MAA 自己去认模拟器改掉上面这些。

这些键和 MAS 注入的其它运行参数一样，由原生配置快照在任务结束后还原。

MAA v6.19.0 复核过：上面的新键名与取值不变；MaaCore 先找 ``nx_device\\15.0``、``nx_device\\12.0``
下的 DLL，最后才是 ``shell\\sdk``，假目录只放最后这一处也能加载；触控多了 ``MumuExtras`` 一档，
``TouchMode = MaaTouch`` 时 GUI 传给 MaaCore 的 ``touch`` 为假，仍走 maatouch。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from app.core import Config
from app.utils import emulator2 as _utils_emulator2
from app.utils import get_logger

logger = get_logger("魔改 AVD MAA 截图")

SHIM_SOURCE = Config.resource_path / "avdshim" / "external_renderer_ipc.dll"

#: MAA 截图用的假 MuMu 目录（``<根>\mumu-shim\shell\sdk\external_renderer_ipc.dll``）。
MUMU_SHIM_DIR = "mumu-shim"

#: MAA 的触控模式（``TouchMode`` 枚举名，gui.new.json 存的就是名字）。
MAA_TOUCH_MODE = "MaaTouch"
MAA_CONNECT_CONFIG = "MuMuEmulator12"


def shim_root(root: str | Path) -> Path:
    """假 MuMu 目录，MAA 的 MuMu 路径填它。"""
    return Path(root) / MUMU_SHIM_DIR


def shim_dll(root: str | Path) -> Path:
    return shim_root(root) / "shell" / "sdk" / "external_renderer_ipc.dll"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_mumu_shim(root: str | Path) -> Path:
    """确保 ``<根>\\mumu-shim\\shell\\sdk\\external_renderer_ipc.dll`` 是随本体发的那一份。

    随本体更新 DLL 也会变，所以不只看在不在，内容不同就覆盖。正在被 MAA 加载时覆盖会失败，
    那就留着旧的并记警告——旧的也能用，下次运行前再换。
    """
    target = shim_dll(root)
    if not SHIM_SOURCE.is_file():
        raise FileNotFoundError(f"缺少截图组件 {SHIM_SOURCE}")
    if target.is_file() and _sha256(target) == _sha256(SHIM_SOURCE):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(SHIM_SOURCE, target)
    except OSError as e:
        if target.is_file():
            logger.warning(f"更新 MAA 截图组件失败，继续使用旧文件: {e}")
            return target
        raise
    logger.info(f"已放置 MAA 截图组件: {target}")
    return target


def build_maa_connect_settings(
    root: str | Path, console_port: int, current: dict[str, Any] | None
) -> dict[str, Any]:
    """在 ``gui.new.json`` 当前配置的 ``Gui.ConnectSettings`` 上叠加魔改 AVD 需要的项。

    ``current`` 原样保留其余键（``AdbPath``、``AddressHistory`` 等），只改下面这几项；
    返回新字典，不改入参。
    """
    settings = dict(current or {})
    extras = dict(settings.get("Extras") or {})
    mumu = dict(extras.get(MAA_CONNECT_CONFIG) or {})
    mumu.update(
        {
            "IsEnabled": True,
            "EmulatorPath": str(shim_root(root)),
            "EnableBridgeConnection": True,
            "InstanceIndex": int(console_port),
        }
    )
    extras[MAA_CONNECT_CONFIG] = mumu
    if not str(settings.get("AdbPath") or "").strip():
        # 用户的 MAA 从没配过 adb（只装了魔改 AVD 的新用户）时才补 SDK 自带的 adb；
        # 已经配了的不动——换 adb 可能和雷电 / MuMu 自带的 adb 抢 5037
        settings["AdbPath"] = str(_utils_emulator2.avd.components.adb_exe(root))
    settings.update(
        {
            "AutoDetect": False,
            "AlwaysAutoDetect": False,
            "Config": MAA_CONNECT_CONFIG,
            "Extras": extras,
            "TouchMode": MAA_TOUCH_MODE,
        }
    )
    return settings


def screencap_fallback_status(log: str) -> str | None:
    """魔改 AVD 实例上 MAA 截图回落到普通 adb 时给运行结果用的说法；没回落返回 ``None``。"""
    method = detect_screencap_fallback(log)
    if method is None:
        return None
    return (
        f"MAA 在魔改 AVD 上没用上截图增强（{method}），截图回落到普通 adb 会很慢，"
        "本次判失败；请检查 MAA 的连接设置是否被改动，或 MAA 版本是否过旧"
    )


#: MAA 界面日志里「最快截图耗时: 5ms (MumuExtras)」那一行（各界面语言的写法），括号里是选中的方式。
#: MAS 每次运行都把 MAA 界面语言设成 zh-cn，其余语言是防用户在 MAA 里改回去时漏判。原文取自
#: MAA v6.18.0 的 MAA.dll 内嵌语言资源（各语言的 WPF 资源字典，格式都是 ``<前缀>: {0}ms ({1})``），
#: v6.19.0 的 MAA.dll 里五种写法都还在；按 zh-cn、zh-tw、en-us、ja-jp、ko-kr 排列。
MAA_FASTEST_SCREENCAP_PREFIXES = (
    "最快截图耗时",
    "最快截圖耗時",
    "Screenshot test tasks",
    "スクリーンショット テストには",
    "스크린샷 캡처 속도",
)
MAA_MUMU_EXTRAS_METHOD = "MumuExtras"
#: MAA 提示「MuMu 截图增强未生效」的各语言开头（同上，取自 v6.18.0 的 MAA.dll）。
MAA_MUMU_NOT_ENABLED_MARKERS = (
    "MuMu 截图增强未生效",
    "MuMu 截圖增強未生效",
    "MuMu screenshot enhancement is not working",
    "MuMu スクリーンショットの強化 が有効になっていません",
    "MuMu 스크린샷 강화 기능이 활성화되지 않았습니다",
)


def detect_screencap_fallback(log: str) -> str | None:
    """从 MAA 界面日志判断魔改 AVD 实例上截图有没有回落到普通 adb。

    回落了返回 MAA 实际选中的方式（给报错用），没回落或还没测完返回 ``None``。
    魔改 AVD 上普通 adb 截图约 250 ms，用户明确说过「不如不做」，所以一旦回落就要
    让这次运行失败，而不是静默变慢。
    """
    if any(marker in log for marker in MAA_MUMU_NOT_ENABLED_MARKERS):
        return "MuMu 截图增强未生效"
    for line in reversed(log.splitlines()):
        if not any(prefix in line for prefix in MAA_FASTEST_SCREENCAP_PREFIXES):
            continue
        head, sep, tail = line.rpartition("(")
        method = tail.rstrip(") \r\n") if sep else ""
        if method and method != MAA_MUMU_EXTRAS_METHOD:
            return method
        return None
    return None
