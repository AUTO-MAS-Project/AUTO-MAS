from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlparse

import pyautogui
from pydantic import AfterValidator

from app.utils.constants import DEFAULT_DATETIME
from app.utils.security import dpapi_decrypt, dpapi_encrypt


class EncryptedFieldMarker:
    """标记需要在对外读取时自动解密的字段。"""


def _to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def _validate_json_dict_string(value: str) -> str:
    text = _to_string(value)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return "{ }"
    return text if isinstance(parsed, dict) else "{ }"


def _validate_json_list_string(value: str) -> str:
    text = _to_string(value)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return "[ ]"
    return text if isinstance(parsed, list) else "[ ]"


def _validate_hhmm_string(value: str) -> str:
    text = _to_string(value)
    try:
        datetime.strptime(text, "%H:%M")
        return text
    except ValueError:
        return DEFAULT_DATETIME.strftime("%H:%M")


def _validate_ymd_hm_string(value: str) -> str:
    text = _to_string(value)
    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M")
        return text
    except ValueError:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M")


def _validate_ymd_string(value: str) -> str:
    text = _to_string(value)
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    except ValueError:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d")


def _validate_ymd_hms_string(value: str) -> str:
    text = _to_string(value)
    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return text
    except ValueError:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M:%S")


def _validate_url_string(value: str) -> str:
    text = _to_string(value)
    if text == "":
        return ""
    try:
        parsed = urlparse(text)
    except Exception:
        return ""
    return text if parsed.scheme and parsed.netloc else ""


def _validate_keyboard_key(value: str) -> str:
    text = _to_string(value).lower()
    return text if text in pyautogui.KEYBOARD_KEYS else ""


def _normalize_encrypted_string(value: str) -> str:
    text = _to_string(value)
    if text == "":
        return ""
    try:
        dpapi_decrypt(text)
        return text
    except Exception:
        return dpapi_encrypt(text)


def decrypt_encrypted_string(value: str) -> str:
    if value == "":
        return ""
    try:
        return dpapi_decrypt(value)
    except Exception:
        return "数据损坏, 请重新设置"


JsonDictString = Annotated[str, AfterValidator(_validate_json_dict_string)]
JsonListString = Annotated[str, AfterValidator(_validate_json_list_string)]
HHMMString = Annotated[str, AfterValidator(_validate_hhmm_string)]
YmdHmString = Annotated[str, AfterValidator(_validate_ymd_hm_string)]
YmdString = Annotated[str, AfterValidator(_validate_ymd_string)]
YmdHmsString = Annotated[str, AfterValidator(_validate_ymd_hms_string)]
UrlString = Annotated[str, AfterValidator(_validate_url_string)]
KeyboardKeyString = Annotated[str, AfterValidator(_validate_keyboard_key)]
EncryptedString = Annotated[
    str,
    EncryptedFieldMarker(),
    AfterValidator(_normalize_encrypted_string),
]


__all__ = [
    "JsonDictString",
    "JsonListString",
    "HHMMString",
    "YmdHmString",
    "YmdString",
    "YmdHmsString",
    "UrlString",
    "KeyboardKeyString",
    "EncryptedString",
    "EncryptedFieldMarker",
    "decrypt_encrypted_string",
]
