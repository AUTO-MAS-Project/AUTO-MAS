#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""游戏社区凭据解析和本地校验边界。

该模块只保存格式、字段名和本地校验状态，不保存、截断、脱敏或改写原始 Token。
平台适配器仍负责真实上游认证、刷新和网络请求。
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .community_contract import CredentialStatus


CredentialFormat = Literal["empty", "opaque", "cookie", "json"]


@dataclass(frozen=True)
class CommunityCredentialInfo:
    """不包含凭据值的解析摘要，供编排层判断凭据形态。"""

    token_field: str
    format: CredentialFormat
    fields: tuple[str, ...] = ()
    configured: bool = False

    def has_any(self, *field_names: str) -> bool:
        """判断 JSON/Cookie 是否包含任一指定字段名。"""

        return any(field_name in self.fields for field_name in field_names)


def _cookie_field_names(raw_token: str) -> tuple[str, ...]:
    fields = set()
    for item in raw_token.split(";"):
        key, separator, _ = item.strip().partition("=")
        if separator and key:
            fields.add(key.strip())
    return tuple(sorted(fields))


def _json_field_names(raw_token: str) -> tuple[str, ...] | None:
    if not raw_token.startswith("{"):
        return None
    try:
        payload = json.loads(raw_token)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return tuple(sorted(str(key) for key in payload if isinstance(key, str)))


def parse_community_credential(
    token_field: str, raw_token: object
) -> CommunityCredentialInfo:
    """解析凭据外形，原始值始终由调用方持有且不会被本模块写回。"""

    text = raw_token if isinstance(raw_token, str) else str(raw_token or "")
    text = text.strip()
    if not text:
        return CommunityCredentialInfo(token_field, "empty")

    if token_field == "MiyousheToken":
        fields = _cookie_field_names(text)
        if fields:
            return CommunityCredentialInfo(
                token_field, "cookie", fields, configured=True
            )

    fields = _json_field_names(text)
    if fields is not None:
        return CommunityCredentialInfo(token_field, "json", fields, configured=True)

    # 保留旧版纯 Token、损坏 JSON 和未知平台 Token 的“已配置”语义。
    return CommunityCredentialInfo(token_field, "opaque", configured=True)


def is_community_credential_configured(token_field: str, raw_token: object) -> bool:
    """判断凭据是否非空，不对平台有效性作结论。"""

    return parse_community_credential(token_field, raw_token).configured


CredentialValidator = Callable[[str], object]


def _validate_skland(raw_token: str) -> object:
    from .skland import validate_skland_credential

    return validate_skland_credential(raw_token)


def _validate_miyoushe(raw_token: str) -> object:
    from .miyoushe import validate_miyoushe_cookie

    return validate_miyoushe_cookie(raw_token)


def _validate_kuro(raw_token: str) -> object:
    from .kuro import validate_kuro_credential

    return validate_kuro_credential(raw_token)


def _validate_taygedo(raw_token: str) -> object:
    from .taygedo import validate_taygedo_credential

    return validate_taygedo_credential(raw_token)


_CREDENTIAL_VALIDATORS: dict[str, CredentialValidator] = {
    "SklandToken": _validate_skland,
    "MiyousheToken": _validate_miyoushe,
    "KuroToken": _validate_kuro,
    "TaygedoToken": _validate_taygedo,
}


def _credential_error_state(reason: str) -> Literal["incomplete", "invalid"]:
    if any(marker in reason for marker in ("缺少", "不能为空", "必须", "不应")):
        return "incomplete"
    return "invalid"


def validate_community_credential(
    token_field: str, raw_token: object
) -> CredentialStatus:
    """执行提供方本地凭据校验，不代表上游 Token 仍然有效。"""

    info = parse_community_credential(token_field, raw_token)
    if not info.configured:
        return CredentialStatus(token_field, "empty", info.fields)

    validator = _CREDENTIAL_VALIDATORS.get(token_field)
    if validator is None:
        return CredentialStatus(token_field, "valid", info.fields)

    text = raw_token if isinstance(raw_token, str) else str(raw_token or "")
    try:
        validator(text)
    except ValueError as exc:
        reason = str(exc).strip() or "凭据格式无效"
        return CredentialStatus(
            token_field,
            _credential_error_state(reason),
            info.fields,
            reason,
        )
    except Exception:
        return CredentialStatus(
            token_field,
            "invalid",
            info.fields,
            "凭据本地校验失败",
        )
    return CredentialStatus(token_field, "valid", info.fields)


# 旧名称继续作为历史调用兼容入口。
GameSignCredentialInfo = CommunityCredentialInfo
parse_game_sign_credential = parse_community_credential
is_game_sign_credential_configured = is_community_credential_configured
validate_game_sign_credential = validate_community_credential
