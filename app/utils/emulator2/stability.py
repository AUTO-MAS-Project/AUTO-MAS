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

"""稳定模式：一键关掉会干扰截图识别的模拟器功能。

脚本靠截图识别加固定坐标点击。模拟器上有一批"为了好看/省电"的功能会破坏这两个前提，
但它们散落在各家设置界面的不同角落，名字还都不一样。稳定模式把它们收成一个开关。

**每一项都标了依据等级，不要把推测和实证混在一起讲：**

- ``maa_documented``  MAA 官方文档明确点名
- ``maa_tracked``     MAA 的 issue 模板要求用户填报（说明 MAA 认为它与故障相关）
- ``mechanical``      对"截图 + 固定坐标"这套机制有直接的、可推理的破坏

**关掉稳定模式不会把这些项改回去。** 我们不知道用户原来想要什么值，
也没有理由替他猜；开关只表示"这几项现在是不是都处在安全状态"。
想要改回去，在模拟器自己的设置界面里改。
"""

from dataclasses import dataclass
from typing import Literal

EvidenceLevel = Literal["maa_documented", "maa_tracked", "mechanical"]


@dataclass(frozen=True)
class StabilityItem:
    """稳定模式管的一项设置。

    ``key`` 是模拟器自己的键名，``safe_value`` 是安全状态下它该有的值。
    ``unsafe_values`` 非空时表示"只有这些值算不安全"——用于枚举型设置，
    比如 MuMu 的显存使用策略只有"资源占用更小"这一档被 MAA 点名，
    其余档位都可以保留，不该一律改成同一个值。
    """

    field: str
    key: str
    safe_value: str
    evidence: EvidenceLevel
    unsafe_values: tuple[str, ...] = ()

    def is_safe(self, current: str | None) -> bool:
        if current is None:
            return False
        text = str(current).strip().casefold()
        if self.unsafe_values:
            return text not in {v.casefold() for v in self.unsafe_values}
        return text == self.safe_value.casefold()


#: 雷电 14。键都在实例配置里，与四项设置同一个文件、同一套写入通道。
LDPLAYER_ITEMS: tuple[StabilityItem, ...] = (
    # MAA 的 issue 模板要求填报"高帧率"，说明它被 MAA 视为故障相关因素
    StabilityItem(
        "highFrameRate", "basicSettings.heightFrameRate", "false", "maa_tracked"
    ),
    # 垂直同步会让画面按显示器节奏出帧，截到的可能是上一帧
    StabilityItem("verticalSync", "basicSettings.verticalSync", "false", "mechanical"),
    # 帧率浮层是**画在画面上的**，直接进截图，可能盖住要识别的元素
    StabilityItem("displayFps", "basicSettings.displayFps", "false", "mechanical"),
    # 自动旋转一转，固定坐标全废
    StabilityItem("autoRotate", "basicSettings.autoRotate", "false", "mechanical"),
)

#: MuMu 6。键走 ``MuMuManager setting``，与四项设置同一个通道。
MUMU_ITEMS: tuple[StabilityItem, ...] = (
    # 后台保活：MAA 的 issue 模板要求填报
    StabilityItem("keepAlive", "app_keptlive", "false", "maa_tracked"),
    # 动态调帧：MuMu 侧的"高帧率"对应项，同样被 issue 模板收集
    StabilityItem("highFrameRate", "dynamic_adjust_frame_rate", "false", "maa_tracked"),
    StabilityItem("verticalSync", "vertical_sync", "false", "mechanical"),
    StabilityItem("displayFps", "show_frame_rate", "false", "mechanical"),
    StabilityItem("autoRotate", "window_auto_rotate", "false", "mechanical"),
    # 显存使用策略：MAA 文档明确写了不要设成「资源占用更小」(dis)。
    # 只有这一档不安全，auto / perf 都保留——不该把用户的性能偏好一并改掉。
    StabilityItem(
        "vramStrategy",
        "renderer_strategy",
        "auto",
        "maa_documented",
        unsafe_values=("dis",),
    ),
)

ITEMS_BY_TYPE: dict[str, tuple[StabilityItem, ...]] = {
    "ldplayer": LDPLAYER_ITEMS,
    "mumu": MUMU_ITEMS,
}


def items_for(emulator_type: str) -> tuple[StabilityItem, ...]:
    return ITEMS_BY_TYPE.get(emulator_type, ())


def evaluate(
    items: tuple[StabilityItem, ...], current: dict[str, str | None]
) -> tuple[bool, list[str]]:
    """判断稳定模式是否已生效，并交回还不安全的字段名。

    读不到值的项算**不安全**——报"已开启"却其实没读到，比报"未开启"糟得多。
    """
    unsafe = [item.field for item in items if not item.is_safe(current.get(item.key))]
    return (not unsafe), unsafe


def safe_writes(
    items: tuple[StabilityItem, ...], current: dict[str, str | None]
) -> dict[str, str]:
    """要写哪些键才能进入安全状态。已经安全的项不重复写。"""
    return {
        item.key: item.safe_value
        for item in items
        if not item.is_safe(current.get(item.key))
    }
