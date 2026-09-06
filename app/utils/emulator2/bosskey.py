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

"""雷电老板键的读取与解码。

雷电**没有任何隐藏窗口的命令行**，老板键是它唯一的隐藏手段。而老板键是
**每个实例各一份**的（存在 ``leidianN.config`` 的 ``hotkeySettings.bossKey``），
旧配置里那个配置级的老板键输入框表达不了这件事——同一个雷电安装下，
用户完全可能给 3 号设了 Ctrl+\\ 而其余保持默认。

所以这里按实例读，不让用户填。

编码形如 ``{"modifiers": 2, "key": 220}``：``key`` 是 Windows 虚拟键码
（220 = 0xDC = ``VK_OEM_5`` = ``\\``），``modifiers`` 是位标志。

**实测只确认了 ``2 == Ctrl``**（同文件 26 个热键全部自洽：``{2,51}`` = Ctrl+3、
``{2,70}`` = Ctrl+F、``{0,112}`` = F1、``{0,27}`` = Esc、``{0,122}`` = F11）。
Alt / Shift 的位值**没有样本**，所以遇到未知位一律报「认不出」，
**不猜、不回落**——猜错的后果是按下一个用户没设过的组合键，比不隐藏更糟。
"""

from dataclasses import dataclass

#: 实测确认的修饰位。没有样本的位值不要往里加。
_MODIFIER_BITS: dict[int, str] = {
    2: "ctrl",
}

#: 雷电在没有 ``hotkeySettings`` 时使用的默认老板键（用户确认）。
DEFAULT_BOSS_KEY = {"modifiers": 2, "key": 81}  # Ctrl+Q


def _build_vk_table() -> dict[int, str]:
    table: dict[int, str] = {
        0x08: "backspace",
        0x09: "tab",
        0x0D: "enter",
        0x13: "pause",
        0x14: "caps lock",
        0x1B: "esc",
        0x20: "space",
        0x21: "page up",
        0x22: "page down",
        0x23: "end",
        0x24: "home",
        0x25: "left",
        0x26: "up",
        0x27: "right",
        0x28: "down",
        0x2C: "print screen",
        0x2D: "insert",
        0x2E: "delete",
        0xBA: ";",
        0xBB: "=",
        0xBC: ",",
        0xBD: "-",
        0xBE: ".",
        0xBF: "/",
        0xC0: "`",
        0xDB: "[",
        0xDC: "\\",
        0xDD: "]",
        0xDE: "'",
    }
    for offset in range(10):  # 0-9
        table[0x30 + offset] = str(offset)
    for offset in range(26):  # A-Z
        table[0x41 + offset] = chr(ord("a") + offset)
    for offset in range(24):  # F1-F24
        table[0x70 + offset] = f"f{offset + 1}"
    return table


#: Windows 虚拟键码 → ``keyboard`` 库的键名。
#: 小键盘、以及 ``+`` 这类会和组合键分隔符冲突的键**故意不收**——
#: 认不出时界面会把隐藏按钮置灰并说明，比发错键安全。
VK_TO_KEYBOARD_NAME = _build_vk_table()


@dataclass(frozen=True)
class BossKey:
    """解码结果。

    ``keys`` 为 ``None`` 表示认不出，此时**不能**退回任何猜测值，
    调用方应让隐藏操作不可用并把 ``reason`` 反馈给用户。
    """

    keys: tuple[str, ...] | None
    reason: str

    #: reason 取值
    #: - ``ok``                读到并认出了实例自己设的组合
    #: - ``default``           实例没设过, 用雷电默认 Ctrl+Q
    #: - ``unknown_modifier``  修饰位里有没验证过的位
    #: - ``unknown_key``       虚拟键码不在映射表里
    #: - ``disabled``          用户把老板键取消了 (雷电用 key=0 表示)
    #: - ``malformed``         字段结构不对

    @property
    def hotkey(self) -> str | None:
        """``keyboard`` 库接受的组合键字符串，如 ``ctrl+q``。"""
        return "+".join(self.keys) if self.keys else None


def decode_boss_key(raw: object) -> BossKey:
    """把 ``hotkeySettings.bossKey`` 的原始值解码成可发送的组合键。

    ``raw`` 为 ``None`` 表示该实例没设过老板键——这是常见情况
    （本机 0/1/2 号都没有 ``hotkeySettings``），按雷电默认处理。
    """
    if raw is None:
        raw = DEFAULT_BOSS_KEY
        fallback_reason = "default"
    else:
        fallback_reason = "ok"

    if not isinstance(raw, dict):
        return BossKey(keys=None, reason="malformed")

    key_code = raw.get("key")
    modifiers = raw.get("modifiers", 0)
    if not isinstance(key_code, int) or not isinstance(modifiers, int):
        return BossKey(keys=None, reason="malformed")
    if isinstance(key_code, bool) or isinstance(modifiers, bool):
        return BossKey(keys=None, reason="malformed")

    # 明确禁用热键的情况：雷电用 key=0 表示没绑。
    # 与 malformed 分开报——「用户主动取消了老板键」和「文件结构对不上」
    # 是两种完全不同的处境，界面要给不同的提示。
    if key_code == 0:
        return BossKey(keys=None, reason="disabled")

    parts: list[str] = []
    remaining = modifiers
    for bit, name in sorted(_MODIFIER_BITS.items()):
        if remaining & bit:
            parts.append(name)
            remaining &= ~bit
    if remaining:
        # 还有没认出的修饰位。这里绝不能忽略它继续发送——
        # 少发一个修饰键就是一个完全不同的组合。
        return BossKey(keys=None, reason="unknown_modifier")

    key_name = VK_TO_KEYBOARD_NAME.get(key_code)
    if key_name is None:
        return BossKey(keys=None, reason="unknown_key")

    parts.append(key_name)
    return BossKey(keys=tuple(parts), reason=fallback_reason)


def read_boss_key(instance_config: dict | None) -> BossKey:
    """从一份已解析的 ``leidianN.config`` 里取老板键。

    配置读不出来（``None``）与「实例没设过老板键」是两回事：前者不能当默认处理，
    因为我们根本不知道用户设的是什么。
    """
    if instance_config is None:
        return BossKey(keys=None, reason="malformed")
    return decode_boss_key(instance_config.get("hotkeySettings.bossKey"))
