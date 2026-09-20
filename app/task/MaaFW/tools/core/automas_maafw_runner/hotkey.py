from __future__ import annotations

import re
from dataclasses import dataclass


class MaaFWHotkeyError(ValueError):
    """Raised when a PI hotkey cannot be mapped for the selected controller."""


@dataclass(frozen=True)
class MaaFWResolvedHotkey:
    primary: int
    modifiers: tuple[int, ...] = ()

    def placeholder_values(self, field_name: str) -> dict[str, int]:
        values = {
            f"{{{field_name}}}": self.primary,
            f"{{{field_name}}}.primary": self.primary,
            # MaaFW ProjectInterface examples use both placeholder styles:
            # ``{Field}.primary`` (legacy) and ``{Field.primary}`` (current).
            # Keep the legacy spelling while exposing the current spelling so
            # project pipeline overrides are resolved before they reach the
            # native parser.
            f"{{{field_name}.primary}}": self.primary,
        }
        for index, modifier in enumerate(self.modifiers, start=1):
            values[f"{{{field_name}}}.modifier{index}"] = modifier
            values[f"{{{field_name}.modifier{index}}}"] = modifier
        return values


_ALIASES = {
    "CONTROL": "CTRL",
    "CTL": "CTRL",
    "OPTION": "ALT",
    "COMMAND": "META",
    "CMD": "META",
    "WIN": "META",
    "WINDOWS": "META",
    "SUPER": "META",
    "ESC": "ESCAPE",
    "RETURN": "ENTER",
    "SPACEBAR": "SPACE",
    "ARROWLEFT": "LEFT",
    "ARROWRIGHT": "RIGHT",
    "ARROWUP": "UP",
    "ARROWDOWN": "DOWN",
    "PAGEUP": "PAGEUP",
    "PAGEDOWN": "PAGEDOWN",
    "PGUP": "PAGEUP",
    "PGDN": "PAGEDOWN",
    "DEL": "DELETE",
    "INS": "INSERT",
    "BACKTICK": "GRAVE",
    "BACKQUOTE": "GRAVE",
    "APOSTROPHE": "QUOTE",
    "EQUAL": "EQUALS",
    "ADD": "PLUS",
    "SUBTRACT": "MINUS",
}
_MODIFIER_KEYS = frozenset({"CTRL", "ALT", "SHIFT", "META"})
_FUNCTION_KEY_RE = re.compile(r"F([1-9]|1[0-9]|2[0-4])\Z")

_WIN32_KEYS = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "PRINTSCREEN": 0x2C,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "META": 0x5B,
    "MULTIPLY": 0x6A,
    "PLUS": 0x6B,
    "MINUS": 0x6D,
    "DECIMAL": 0x6E,
    "DIVIDE": 0x6F,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
    "SEMICOLON": 0xBA,
    "EQUALS": 0xBB,
    "COMMA": 0xBC,
    "PERIOD": 0xBE,
    "SLASH": 0xBF,
    "GRAVE": 0xC0,
    "BRACKETLEFT": 0xDB,
    "BACKSLASH": 0xDC,
    "BRACKETRIGHT": 0xDD,
    "QUOTE": 0xDE,
}

_ADB_KEYS = {
    "LEFT": 21,
    "RIGHT": 22,
    "UP": 19,
    "DOWN": 20,
    "ALT": 57,
    "SHIFT": 59,
    "TAB": 61,
    "SPACE": 62,
    "ENTER": 66,
    "BACKSPACE": 67,
    "GRAVE": 68,
    "MINUS": 69,
    "EQUALS": 70,
    "BRACKETLEFT": 71,
    "BRACKETRIGHT": 72,
    "BACKSLASH": 73,
    "SEMICOLON": 74,
    "QUOTE": 75,
    "SLASH": 76,
    "PLUS": 81,
    "PAGEUP": 92,
    "PAGEDOWN": 93,
    "ESCAPE": 111,
    "DELETE": 112,
    "CTRL": 113,
    "CAPSLOCK": 115,
    "SCROLLLOCK": 116,
    "META": 117,
    "PRINTSCREEN": 120,
    "PAUSE": 121,
    "HOME": 122,
    "END": 123,
    "INSERT": 124,
    "NUMLOCK": 143,
    "DIVIDE": 154,
    "MULTIPLY": 155,
    "DECIMAL": 158,
}


def resolve_hotkey(value: str, controller_type: str) -> MaaFWResolvedHotkey:
    parts = [_canonical_key(part) for part in value.split("+")]
    if not parts or any(not part for part in parts):
        raise MaaFWHotkeyError(f"快捷键格式无效: {value!r}")
    if len(parts) > 3:
        raise MaaFWHotkeyError("PI v2.8 hotkey 最多支持两个修饰键和一个主键")
    if len(set(parts)) != len(parts):
        raise MaaFWHotkeyError(f"快捷键包含重复按键: {value}")
    if len(parts) > 1:
        invalid_modifiers = [part for part in parts[:-1] if part not in _MODIFIER_KEYS]
        if invalid_modifiers:
            raise MaaFWHotkeyError(
                "组合键主键之前只能是 Ctrl/Alt/Shift/Meta: "
                + ", ".join(invalid_modifiers)
            )

    keycodes = tuple(_keycode(part, controller_type) for part in parts)
    return MaaFWResolvedHotkey(primary=keycodes[-1], modifiers=keycodes[:-1])


def _canonical_key(value: str) -> str:
    if value == " ":
        return "SPACE"
    normalized = value.strip()

    normalized = re.sub(r"[\s_-]+", "", normalized).upper()
    if (
        normalized.startswith("KEY")
        and len(normalized) == 4
        and normalized[-1].isalpha()
    ):
        normalized = normalized[-1]
    elif (
        normalized.startswith("DIGIT")
        and len(normalized) == 6
        and normalized[-1].isdigit()
    ):
        normalized = normalized[-1]

    punctuation_aliases = {
        ",": "COMMA",
        ".": "PERIOD",
        "/": "SLASH",
        "\\": "BACKSLASH",
        ";": "SEMICOLON",
        "'": "QUOTE",
        "`": "GRAVE",
        "[": "BRACKETLEFT",
        "]": "BRACKETRIGHT",
        "=": "EQUALS",
    }
    return _ALIASES.get(normalized, punctuation_aliases.get(normalized, normalized))


def _keycode(key: str, controller_type: str) -> int:
    if controller_type == "Win32":
        return _win32_keycode(key)
    if controller_type == "Adb":
        return _adb_keycode(key)
    raise MaaFWHotkeyError(
        f"AUTO-MAS Direct 暂不支持 {controller_type} 控制器的 hotkey 键码映射"
    )


def _win32_keycode(key: str) -> int:
    if len(key) == 1 and (key.isalpha() or key.isdigit()):
        return ord(key)
    function_match = _FUNCTION_KEY_RE.fullmatch(key)
    if function_match:
        return 0x70 + int(function_match.group(1)) - 1
    if key.startswith("NUMPAD") and key[6:].isdigit():
        number = int(key[6:])
        if 0 <= number <= 9:
            return 0x60 + number
    try:
        return _WIN32_KEYS[key]
    except KeyError as exc:
        raise MaaFWHotkeyError(f"Win32 不支持快捷键: {key}") from exc


def _adb_keycode(key: str) -> int:
    if len(key) == 1 and key.isalpha():
        return 29 + ord(key) - ord("A")
    if len(key) == 1 and key.isdigit():
        return 7 + int(key)
    function_match = _FUNCTION_KEY_RE.fullmatch(key)
    if function_match and int(function_match.group(1)) <= 12:
        return 131 + int(function_match.group(1)) - 1
    if key.startswith("NUMPAD") and key[6:].isdigit():
        number = int(key[6:])
        if 0 <= number <= 9:
            return 144 + number
    try:
        return _ADB_KEYS[key]
    except KeyError as exc:
        raise MaaFWHotkeyError(f"Adb 不支持快捷键: {key}") from exc
