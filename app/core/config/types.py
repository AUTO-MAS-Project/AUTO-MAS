from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlparse

import pyautogui
from loguru import logger
from pydantic import AfterValidator

from app.utils.constants import DEFAULT_DATETIME
from app.utils.security import dpapi_decrypt, dpapi_encrypt


class EncryptedFieldMarker:
    """标记需要在对外读取时自动解密的字段。"""


def _to_string(value: Any) -> str:
    """
    将任意值转换为字符串。

    Args:
        value: 要转换的值

    Returns:
        字符串表示，None 返回空字符串
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _validate_json_dict_string(value: Any) -> str:
    """
    校验并规范化 JSON 字典字符串。

    Args:
        value: 输入值

    Returns:
        有效的 JSON 字典字符串，失败时返回 "{ }"

    Raises:
        ValidationError: 如果输入不是字符串且无法转换
    """
    text = _to_string(value)
    if not text:
        raise ValueError("JSON 字典字符串不能为空")

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            logger.warning(f"JSON 不是字典类型: {text[:50]}...")
            raise ValueError("JSON 不是字典类型")
        return text
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}, 输入: {text[:50]}...")
        raise ValueError("JSON 字典字符串解析失败") from e


def _validate_json_list_string(value: Any) -> str:
    """
    校验并规范化 JSON 列表字符串。

    Args:
        value: 输入值

    Returns:
        有效的 JSON 列表字符串，失败时返回 "[ ]"
    """
    text = _to_string(value)
    if not text:
        raise ValueError("JSON 列表字符串不能为空")

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            logger.warning(f"JSON 不是列表类型: {text[:50]}...")
            raise ValueError("JSON 不是列表类型")
        return text
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}, 输入: {text[:50]}...")
        raise ValueError("JSON 列表字符串解析失败") from e


def _validate_hhmm_string(value: Any) -> str:
    """
    校验并规范化 HH:MM 时间字符串。

    Args:
        value: 输入值

    Returns:
        有效的 HH:MM 格式字符串，失败时返回默认时间
    """
    text = _to_string(value)
    if not text:
        return DEFAULT_DATETIME.strftime("%H:%M")

    try:
        datetime.strptime(text, "%H:%M")
        return text
    except ValueError as e:
        logger.warning(f"时间格式错误: {e}, 输入: {text}")
        return DEFAULT_DATETIME.strftime("%H:%M")


def _validate_ymd_hm_string(value: Any) -> str:
    """校验并规范化 YYYY-MM-DD HH:MM 日期时间字符串。"""
    text = _to_string(value)
    if not text:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M")

    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M")
        return text
    except ValueError as e:
        logger.warning(f"日期时间格式错误: {e}, 输入: {text}")
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M")


def _validate_ymd_string(value: Any) -> str:
    """校验并规范化 YYYY-MM-DD 日期字符串。"""
    text = _to_string(value)
    if not text:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d")

    try:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    except ValueError as e:
        logger.warning(f"日期格式错误: {e}, 输入: {text}")
        return DEFAULT_DATETIME.strftime("%Y-%m-%d")


def _validate_ymd_hms_string(value: Any) -> str:
    """校验并规范化 YYYY-MM-DD HH:MM:SS 日期时间字符串。"""
    text = _to_string(value)
    if not text:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M:%S")

    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return text
    except ValueError as e:
        logger.warning(f"日期时间格式错误: {e}, 输入: {text}")
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M:%S")


def _validate_url_string(value: Any) -> str:
    """
    校验并规范化 URL 字符串。

    Args:
        value: 输入值

    Returns:
        有效的 URL 字符串，失败时返回空字符串
    """
    text = _to_string(value)
    if not text:
        raise ValueError("URL 不能为空")

    try:
        parsed = urlparse(text)
        if not parsed.scheme or not parsed.netloc:
            logger.warning(f"URL 格式错误: {text}")
            raise ValueError("URL 格式错误")
        return text
    except ValueError:
        raise
    except TypeError as e:
        logger.warning(f"URL 解析失败: {e}, 输入: {text}")
        raise ValueError("URL 解析失败") from e


def _validate_keyboard_key(value: Any) -> str:
    """
    校验键盘按键字符串。

    Args:
        value: 输入值

    Returns:
        有效的按键字符串，失败时返回空字符串
    """
    text = _to_string(value).lower()
    if not text:
        raise ValueError("键盘按键不能为空")

    if text not in pyautogui.KEYBOARD_KEYS:
        logger.warning(f"无效的键盘按键: {text}")
        raise ValueError(f"无效的键盘按键: {text}")

    return text


def _normalize_encrypted_string(value: Any) -> str:
    """
    规范化加密字符串。

    如果输入已加密，则保持不变；否则加密。

    Args:
        value: 输入值

    Returns:
        加密后的字符串
    """
    text = _to_string(value)
    if not text:
        raise ValueError("加密字段不能为空")

    try:
        # 尝试解密，如果成功说明已加密
        dpapi_decrypt(text)
        return text
    except ValueError:
        # 解密失败，说明是明文，需要加密
        try:
            return dpapi_encrypt(text)
        except (ValueError, TypeError) as e:
            logger.error(f"加密失败: {e}, 输入长度: {len(text)}")
            raise ValueError("加密失败") from e


def decrypt_encrypted_string(value: str) -> str:
    """
    解密加密字符串。

    Args:
        value: 加密的字符串

    Returns:
        解密后的明文，失败时返回错误提示
    """
    if not value:
        return ""

    try:
        return dpapi_decrypt(value)
    except ValueError as e:
        logger.error(f"解密失败: {e}")
        raise ValueError("数据损坏，请重新设置") from e


# 类型别名定义
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
