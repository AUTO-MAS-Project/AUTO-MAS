"""宿主主配置的原生 Config v2 根与 r6 兼容转换。"""

from __future__ import annotations

import calendar
import json
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from pydantic import AfterValidator, Field

from app.configuration import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    Virtual,
    WireDict,
    collection,
    encrypted,
    virtual_field,
)
from app.configuration.v2.support.security import is_probable_dpapi_ciphertext
from app.utils.constants import MATERIALS_MAP, RESOURCE_STAGE_INFO, UTC8

LEGACY_WEBHOOK_TYPE = "Webhook"
V2_WEBHOOK_TYPE = "Webhook"
CUSTOM_WEBHOOKS_NAME = "Notify_CustomWebhooks"

_FUNCTION_DEFAULTS: dict[str, object] = {
    "HistoryRetentionTime": 0,
    "IfAllowSleep": False,
    "IfSilence": False,
    "IfAgreeBilibili": False,
    "IfBlockAd": False,
}
_VOICE_DEFAULTS: dict[str, object] = {
    "Enabled": False,
    "Type": "simple",
}
_START_DEFAULTS: dict[str, object] = {
    "IfSelfStart": False,
    "IfMinimizeDirectly": False,
}
_UI_DEFAULTS: dict[str, object] = {
    "IfShowTray": False,
    "IfToTray": False,
    "IfHideCloseButton": False,
}
_NOTIFY_DEFAULTS: dict[str, object] = {
    "SendTaskResultTime": "不推送",
    "IfSendStatistic": False,
    "IfSendSixStar": False,
    "IfPushPlyer": False,
    "IfSendMail": False,
    "IfKoishiSupport": False,
    "KoishiServerAddress": "ws://localhost:5140/AUTO_MAS",
    "KoishiToken": "",
    "SMTPServerAddress": "",
    "AuthorizationCode": "",
    "FromAddress": "",
    "ToAddress": "",
    "IfServerChan": False,
    "ServerChanKey": "",
}
_UPDATE_DEFAULTS: dict[str, object] = {
    "IfAutoUpdate": False,
    "Source": "GitHub",
    "Channel": "stable",
    "ProxyAddress": "",
    "MirrorChyanCDK": "",
    "GitHubToken": "",
}
_DATA_DEFAULTS: dict[str, object] = {
    "LastStatisticsUpload": "2000-01-01 00:00:00",
    "LastStageUpdated": "2000-01-01 00:00:00",
    "StageETag": "",
    "StageData": "{ }",
    "LastNoticeUpdated": "2000-01-01 00:00:00",
    "NoticeETag": "",
    "IfShowNotice": True,
    "Notice": "{ }",
    "LastWebConfigUpdated": "2000-01-01 00:00:00",
    "WebConfig": "[ ]",
}
_WEBHOOK_INFO_DEFAULTS: dict[str, object] = {
    "Name": "新自定义 Webhook 通知",
    "Enabled": True,
}
_WEBHOOK_DATA_DEFAULTS: dict[str, object] = {
    "Url": "",
    "Template": "",
    "Headers": "{ }",
    "Method": "POST",
}

_ROOT_GROUPS = frozenset(
    {"Function", "Voice", "Start", "UI", "Notify", "Update", "Data"}
)
_HISTORY_RETENTION_OPTIONS = frozenset({7, 15, 30, 60, 90, 180, 365, 0})
_LEGACY_ALREADY_ENCRYPTED_FIELDS = frozenset(
    {
        ("Notify", "AuthorizationCode"),
        ("Update", "MirrorChyanCDK"),
        ("Update", "GitHubToken"),
    }
)


def _new_host_uid() -> str:
    return str(uuid4())


def _validate_uuid_text(value: str) -> str:
    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise ValueError("UID 必须是 UUID 字符串") from None
    return value


def _validate_datetime_text(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError("时间必须使用 YYYY-MM-DD HH:MM:SS 格式") from None
    return value


def _validate_json_dict_text(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError("值必须是 JSON 字典字符串") from None
    if not isinstance(parsed, dict):
        raise ValueError("值必须是 JSON 字典字符串")
    return value


def _validate_json_list_text(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError("值必须是 JSON 列表字符串") from None
    if not isinstance(parsed, list):
        raise ValueError("值必须是 JSON 列表字符串")
    return value


def _validate_url_text(value: str) -> str:
    if value == "":
        return value
    try:
        parsed = urlparse(value)
    except Exception:
        raise ValueError("值必须是包含协议和网络位置的 URL") from None
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("值必须是包含协议和网络位置的 URL")
    return value


def _build_stage_projection(raw: str, *, now: datetime | None = None) -> str:
    """按 r6 ``GlobalConfig.getStage`` 语义生成前端关卡投影。"""

    try:
        raw_stage_data = json.loads(raw)
        if not isinstance(raw_stage_data, dict):
            return "{ }"

        current = now if now is not None else datetime.now(tz=UTC8)
        activity_stage_drop_info: list[dict[str, object]] = []
        activity_stage_combobox: list[dict[str, object]] = []

        for side_story in raw_stage_data.values():
            activity = side_story["Activity"]
            if (
                datetime.strptime(
                    activity["UtcStartTime"],
                    "%Y/%m/%d %H:%M:%S",
                ).replace(tzinfo=UTC8)
                < current
                < datetime.strptime(
                    activity["UtcExpireTime"],
                    "%Y/%m/%d %H:%M:%S",
                ).replace(tzinfo=UTC8)
            ):
                for stage in side_story["Stages"]:
                    activity_stage_combobox.append(
                        {
                            "label": stage["Display"],
                            "value": stage["Value"],
                        }
                    )
                    if "SSReopen" in stage["Display"]:
                        continue
                    if stage["Drop"] in MATERIALS_MAP:
                        drop_id = stage["Drop"]
                    elif "玉" in stage["Drop"]:
                        drop_id = "30012"
                    else:
                        drop_id = "NotFound"
                    activity_stage_drop_info.append(
                        {
                            "Display": stage["Display"],
                            "Value": stage["Value"],
                            "Drop": drop_id,
                            "DropName": MATERIALS_MAP.get(
                                stage["Drop"],
                                stage["Drop"],
                            ),
                            "Activity": activity,
                        }
                    )
    except (KeyError, TypeError, ValueError):
        return "{ }"

    stage_data: dict[str, object] = {"Info": activity_stage_drop_info}
    for day in range(0, 8):
        resource_stages = [
            {"label": stage["text"], "value": stage["value"]}
            for stage in RESOURCE_STAGE_INFO
            if day in stage["days"] or day == 0
        ]
        group_name = calendar.day_name[day - 1] if day > 0 else "ALL"
        stage_data[group_name] = (
            resource_stages[0:1]
            + activity_stage_combobox
            + resource_stages[1:]
        )
    return json.dumps(stage_data, ensure_ascii=False)


class Webhook(ConfigEntry):
    """单个自定义 Webhook。"""

    class InfoGroup(ConfigGroup):
        Name: Annotated[str, Field(strict=True)] = "新自定义 Webhook 通知"
        Enabled: Annotated[bool, Field(strict=True)] = True

    class DataGroup(ConfigGroup):
        # URL 与请求头在当前宿主中属于加密存储字段。
        Url: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_url_text),
            encrypted(),
        ] = ""
        Template: Annotated[str, Field(strict=True)] = ""
        Headers: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_json_dict_text),
            encrypted(),
        ] = "{ }"
        Method: Literal["POST", "GET"] = "POST"

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Data: DataGroup = Field(default_factory=DataGroup)


class CustomWebhooks(ConfigCollection[Webhook]):
    """``Config.Notify_CustomWebhooks`` 嵌套集合。"""

    _default_entry_types = (Webhook,)


class GlobalConfig(ConfigEntry):
    """独立 ``Config.json`` 的宿主主配置根。"""

    class FunctionGroup(ConfigGroup):
        HistoryRetentionTime: Literal[7, 15, 30, 60, 90, 180, 365, 0] = 0
        IfAllowSleep: Annotated[bool, Field(strict=True)] = False
        IfSilence: Annotated[bool, Field(strict=True)] = False
        IfAgreeBilibili: Annotated[bool, Field(strict=True)] = False
        IfBlockAd: Annotated[bool, Field(strict=True)] = False

    class VoiceGroup(ConfigGroup):
        Enabled: Annotated[bool, Field(strict=True)] = False
        Type: Literal["simple", "noisy"] = "simple"

    class StartGroup(ConfigGroup):
        IfSelfStart: Annotated[bool, Field(strict=True)] = False
        IfMinimizeDirectly: Annotated[bool, Field(strict=True)] = False

    class UIGroup(ConfigGroup):
        IfShowTray: Annotated[bool, Field(strict=True)] = False
        IfToTray: Annotated[bool, Field(strict=True)] = False
        IfHideCloseButton: Annotated[bool, Field(strict=True)] = False

    class NotifyGroup(ConfigGroup):
        SendTaskResultTime: Literal["不推送", "任何时刻", "仅失败时"] = "不推送"
        IfSendStatistic: Annotated[bool, Field(strict=True)] = False
        IfSendSixStar: Annotated[bool, Field(strict=True)] = False
        IfPushPlyer: Annotated[bool, Field(strict=True)] = False
        IfSendMail: Annotated[bool, Field(strict=True)] = False
        IfKoishiSupport: Annotated[bool, Field(strict=True)] = False
        KoishiServerAddress: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_url_text),
        ] = "ws://localhost:5140/AUTO_MAS"
        KoishiToken: Annotated[str, Field(strict=True), encrypted()] = ""
        SMTPServerAddress: Annotated[str, Field(strict=True)] = ""
        AuthorizationCode: Annotated[str, Field(strict=True), encrypted()] = ""
        FromAddress: Annotated[str, Field(strict=True)] = ""
        ToAddress: Annotated[str, Field(strict=True)] = ""
        IfServerChan: Annotated[bool, Field(strict=True)] = False
        ServerChanKey: Annotated[str, Field(strict=True), encrypted()] = ""

    class UpdateGroup(ConfigGroup):
        IfAutoUpdate: Annotated[bool, Field(strict=True)] = False
        Source: Literal["GitHub", "MirrorChyan", "AutoSite", "CNB"] = "GitHub"
        Channel: Literal["stable", "beta"] = "stable"
        ProxyAddress: Annotated[str, Field(strict=True), encrypted()] = ""
        MirrorChyanCDK: Annotated[str, Field(strict=True), encrypted()] = ""
        GitHubToken: Annotated[str, Field(strict=True), encrypted()] = ""

    class DataGroup(ConfigGroup):
        UID: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_uuid_text),
        ] = Field(default_factory=_new_host_uid)
        LastStatisticsUpload: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_datetime_text),
        ] = "2000-01-01 00:00:00"
        LastStageUpdated: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_datetime_text),
        ] = "2000-01-01 00:00:00"
        StageETag: Annotated[str, Field(strict=True)] = ""
        StageData: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_json_dict_text),
        ] = "{ }"
        Stage: Virtual[str] = None
        LastNoticeUpdated: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_datetime_text),
        ] = "2000-01-01 00:00:00"
        NoticeETag: Annotated[str, Field(strict=True)] = ""
        IfShowNotice: Annotated[bool, Field(strict=True)] = True
        Notice: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_json_dict_text),
        ] = "{ }"
        LastWebConfigUpdated: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_datetime_text),
        ] = "2000-01-01 00:00:00"
        WebConfig: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_json_list_text),
        ] = "[ ]"

    Function: FunctionGroup = Field(default_factory=FunctionGroup)
    Voice: VoiceGroup = Field(default_factory=VoiceGroup)
    Start: StartGroup = Field(default_factory=StartGroup)
    UI: UIGroup = Field(default_factory=UIGroup)
    Notify: NotifyGroup = Field(default_factory=NotifyGroup)
    Update: UpdateGroup = Field(default_factory=UpdateGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    Notify_CustomWebhooks: CustomWebhooks = collection(Webhook)

    @virtual_field("Data.Stage")
    def get_stage(self) -> str:
        return _build_stage_projection(self.Data.StageData)


def _require_dict(value: object, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{path} 必须是对象")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{path} 的键必须是字符串")
    return value


def _require_group(
    value: object,
    *,
    defaults: dict[str, object],
    path: str,
) -> dict[str, object]:
    group = _require_dict(value, path=path)
    unknown = sorted(set(group) - set(defaults))
    if unknown:
        raise ValueError(
            "未知主配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    normalized = dict(defaults)
    normalized.update(group)
    return normalized


def _require_strings(
    group: dict[str, object],
    names: tuple[str, ...],
    *,
    path: str,
) -> None:
    for name in names:
        if not isinstance(group[name], str):
            raise TypeError(f"{path}.{name} 必须是字符串")


def _require_bools(
    group: dict[str, object],
    names: tuple[str, ...],
    *,
    path: str,
) -> None:
    for name in names:
        if not isinstance(group[name], bool):
            raise TypeError(f"{path}.{name} 必须是布尔值")


def _validate_secret_for_rollback(value: str, *, path: str) -> None:
    if value and not is_probable_dpapi_ciphertext(value):
        raise ValueError(f"{path} 必须为空或为 DPAPI 密文")


def _normalize_function(value: object, *, path: str) -> WireDict:
    group = _require_group(value, defaults=_FUNCTION_DEFAULTS, path=path)
    retention = group["HistoryRetentionTime"]
    if (
        not isinstance(retention, int)
        or isinstance(retention, bool)
        or retention not in _HISTORY_RETENTION_OPTIONS
    ):
        raise ValueError(f"{path}.HistoryRetentionTime 不在允许选项中")
    _require_bools(
        group,
        (
            "IfAllowSleep",
            "IfSilence",
            "IfAgreeBilibili",
            "IfBlockAd",
        ),
        path=path,
    )
    return group


def _normalize_voice(value: object, *, path: str) -> WireDict:
    group = _require_group(value, defaults=_VOICE_DEFAULTS, path=path)
    if not isinstance(group["Enabled"], bool):
        raise TypeError(f"{path}.Enabled 必须是布尔值")
    voice_type = group["Type"]
    if not isinstance(voice_type, str) or voice_type not in {"simple", "noisy"}:
        raise ValueError(f"{path}.Type 仅允许 simple 或 noisy")
    return group


def _normalize_start(value: object, *, path: str) -> WireDict:
    group = _require_group(value, defaults=_START_DEFAULTS, path=path)
    _require_bools(
        group,
        ("IfSelfStart", "IfMinimizeDirectly"),
        path=path,
    )
    return group


def _normalize_ui(value: object, *, path: str) -> WireDict:
    group = _require_group(value, defaults=_UI_DEFAULTS, path=path)
    _require_bools(
        group,
        ("IfShowTray", "IfToTray", "IfHideCloseButton"),
        path=path,
    )
    return group


def _normalize_notify(
    value: object,
    *,
    path: str,
    for_rollback: bool,
) -> WireDict:
    group = _require_group(value, defaults=_NOTIFY_DEFAULTS, path=path)
    _require_bools(
        group,
        (
            "IfSendStatistic",
            "IfSendSixStar",
            "IfPushPlyer",
            "IfSendMail",
            "IfKoishiSupport",
            "IfServerChan",
        ),
        path=path,
    )
    _require_strings(
        group,
        (
            "SendTaskResultTime",
            "KoishiServerAddress",
            "KoishiToken",
            "SMTPServerAddress",
            "AuthorizationCode",
            "FromAddress",
            "ToAddress",
            "ServerChanKey",
        ),
        path=path,
    )
    if group["SendTaskResultTime"] not in {"不推送", "任何时刻", "仅失败时"}:
        raise ValueError(f"{path}.SendTaskResultTime 不在允许选项中")
    _validate_url_text(str(group["KoishiServerAddress"]))

    for field_name in ("KoishiToken", "AuthorizationCode", "ServerChanKey"):
        secret = str(group[field_name])
        if (
            for_rollback
            or ("Notify", field_name) in _LEGACY_ALREADY_ENCRYPTED_FIELDS
        ):
            _validate_secret_for_rollback(
                secret,
                path=f"{path}.{field_name}",
            )
    return group


def _normalize_update(
    value: object,
    *,
    path: str,
    for_rollback: bool,
) -> WireDict:
    group = _require_group(value, defaults=_UPDATE_DEFAULTS, path=path)
    if not isinstance(group["IfAutoUpdate"], bool):
        raise TypeError(f"{path}.IfAutoUpdate 必须是布尔值")
    _require_strings(
        group,
        (
            "Source",
            "Channel",
            "ProxyAddress",
            "MirrorChyanCDK",
            "GitHubToken",
        ),
        path=path,
    )
    if group["Source"] not in {"GitHub", "MirrorChyan", "AutoSite", "CNB"}:
        raise ValueError(f"{path}.Source 不在允许选项中")
    if group["Channel"] not in {"stable", "beta"}:
        raise ValueError(f"{path}.Channel 仅允许 stable 或 beta")

    for field_name in ("ProxyAddress", "MirrorChyanCDK", "GitHubToken"):
        secret = str(group[field_name])
        if (
            for_rollback
            or ("Update", field_name) in _LEGACY_ALREADY_ENCRYPTED_FIELDS
        ):
            _validate_secret_for_rollback(
                secret,
                path=f"{path}.{field_name}",
            )
    return group


def _normalize_legacy_data(value: object, *, path: str) -> WireDict:
    raw = _require_dict(value, path=path)
    allowed = set(_DATA_DEFAULTS) | {"UID", "Stage"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(
            "未知主配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )

    normalized = dict(_DATA_DEFAULTS)
    normalized.update({key: raw[key] for key in _DATA_DEFAULTS if key in raw})

    # StageData 取代了更早版本的 Stage 原始数据。当前版本同时保留的 Stage
    # 是虚拟前端投影，只有 StageData 缺失时才按旧 ConfigItem alias 解释。
    if "StageData" not in raw and "Stage" in raw:
        normalized["StageData"] = raw["Stage"]
    elif "Stage" in raw:
        if not isinstance(raw["Stage"], str):
            raise TypeError(f"{path}.Stage 必须是字符串")
        _validate_json_dict_text(raw["Stage"])

    if "UID" in raw:
        if not isinstance(raw["UID"], str):
            raise TypeError(f"{path}.UID 必须是字符串")
        _validate_uuid_text(raw["UID"])
        normalized["UID"] = raw["UID"]

    _validate_data_values(normalized, path=path)
    return normalized


def _normalize_v2_data(value: object, *, path: str) -> WireDict:
    raw = _require_dict(value, path=path)
    allowed = set(_DATA_DEFAULTS) | {"UID"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(
            "未知主配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    normalized = dict(_DATA_DEFAULTS)
    normalized.update({key: raw[key] for key in _DATA_DEFAULTS if key in raw})
    if "UID" in raw:
        if not isinstance(raw["UID"], str):
            raise TypeError(f"{path}.UID 必须是字符串")
        _validate_uuid_text(raw["UID"])
        normalized["UID"] = raw["UID"]
    _validate_data_values(normalized, path=path)
    return normalized


def _validate_data_values(group: dict[str, object], *, path: str) -> None:
    _require_strings(
        group,
        (
            "LastStatisticsUpload",
            "LastStageUpdated",
            "StageETag",
            "StageData",
            "LastNoticeUpdated",
            "NoticeETag",
            "Notice",
            "LastWebConfigUpdated",
            "WebConfig",
        ),
        path=path,
    )
    if not isinstance(group["IfShowNotice"], bool):
        raise TypeError(f"{path}.IfShowNotice 必须是布尔值")
    for field_name in (
        "LastStatisticsUpload",
        "LastStageUpdated",
        "LastNoticeUpdated",
        "LastWebConfigUpdated",
    ):
        _validate_datetime_text(str(group[field_name]))
    _validate_json_dict_text(str(group["StageData"]))
    _validate_json_dict_text(str(group["Notice"]))
    _validate_json_list_text(str(group["WebConfig"]))


def _parse_uid(value: object, *, path: str) -> tuple[UUID, str]:
    if not isinstance(value, str):
        raise ValueError(f"{path} 必须是 UUID 字符串")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{path} 不是有效 UUID") from None
    return parsed, str(parsed)


def _parse_order(
    value: object,
    *,
    expected_type: str,
    path: str,
) -> list[tuple[UUID, str, str]]:
    if not isinstance(value, list):
        raise TypeError(f"{path} 必须是列表")
    order: list[tuple[UUID, str, str]] = []
    seen: set[UUID] = set()
    for index, item_value in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _require_dict(item_value, path=item_path)
        unknown = sorted(set(item) - {"uid", "type"})
        if unknown:
            raise ValueError(
                "未知主配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")
        uid, canonical_uid = _parse_uid(item["uid"], path=f"{item_path}.uid")
        if uid in seen:
            raise ValueError(f"{path} 包含重复 uid")
        if item["type"] != expected_type:
            raise ValueError(f"{item_path}.type 仅允许 {expected_type}")
        seen.add(uid)
        order.append((uid, canonical_uid, str(item["uid"])))
    return order


def _normalize_webhook(
    value: object,
    *,
    path: str,
    for_rollback: bool,
) -> WireDict:
    entry = _require_dict(value, path=path)
    unknown_groups = sorted(set(entry) - {"Info", "Data"})
    if unknown_groups:
        raise ValueError(
            "未知主配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )
    info = _require_group(
        entry.get("Info", {}),
        defaults=_WEBHOOK_INFO_DEFAULTS,
        path=f"{path}.Info",
    )
    data = _require_group(
        entry.get("Data", {}),
        defaults=_WEBHOOK_DATA_DEFAULTS,
        path=f"{path}.Data",
    )
    if not isinstance(info["Name"], str):
        raise TypeError(f"{path}.Info.Name 必须是字符串")
    if not isinstance(info["Enabled"], bool):
        raise TypeError(f"{path}.Info.Enabled 必须是布尔值")
    _require_strings(
        data,
        ("Url", "Template", "Headers", "Method"),
        path=f"{path}.Data",
    )
    if data["Method"] not in {"POST", "GET"}:
        raise ValueError(f"{path}.Data.Method 仅允许 POST 或 GET")

    url = str(data["Url"])
    headers = str(data["Headers"])
    if for_rollback:
        _validate_secret_for_rollback(url, path=f"{path}.Data.Url")
        _validate_secret_for_rollback(headers, path=f"{path}.Data.Headers")
    else:
        if not is_probable_dpapi_ciphertext(url):
            _validate_url_text(url)
        if not is_probable_dpapi_ciphertext(headers):
            _validate_json_dict_text(headers)
    return {"Info": info, "Data": data}


def _legacy_webhooks_to_wire(value: object) -> WireDict:
    collection_data = _require_dict(
        value,
        path=f"$.SubConfigsInfo.{CUSTOM_WEBHOOKS_NAME}",
    )
    order = _parse_order(
        collection_data.get("instances", []),
        expected_type=LEGACY_WEBHOOK_TYPE,
        path=f"$.SubConfigsInfo.{CUSTOM_WEBHOOKS_NAME}.instances",
    )
    raw_uid_keys = {raw_uid for _, _, raw_uid in order}
    unknown = sorted(set(collection_data) - {"instances"} - raw_uid_keys)
    if unknown:
        raise ValueError(
            f"$.SubConfigsInfo.{CUSTOM_WEBHOOKS_NAME} 包含孤儿或未知字段: "
            + ", ".join(unknown)
        )
    if any(raw_uid not in collection_data for _, _, raw_uid in order):
        raise ValueError(
            f"$.SubConfigsInfo.{CUSTOM_WEBHOOKS_NAME}.instances "
            "引用了缺失的数据项"
        )

    return {
        "order": [
            {"uid": canonical_uid, "type": V2_WEBHOOK_TYPE}
            for _, canonical_uid, _ in order
        ],
        "data": {
            canonical_uid: _normalize_webhook(
                collection_data[raw_uid],
                path=(
                    f"$.SubConfigsInfo.{CUSTOM_WEBHOOKS_NAME}."
                    f"{canonical_uid}"
                ),
                for_rollback=False,
            )
            for _, canonical_uid, raw_uid in order
        },
    }


def _webhooks_wire_to_legacy(value: object) -> dict[str, Any]:
    collection_data = _require_dict(value, path=f"$.{CUSTOM_WEBHOOKS_NAME}")
    unknown = sorted(set(collection_data) - {"order", "data"})
    if unknown:
        raise ValueError(
            "未知主配置路径: "
            + ", ".join(f"$.{CUSTOM_WEBHOOKS_NAME}.{name}" for name in unknown)
        )
    order = _parse_order(
        collection_data.get("order", []),
        expected_type=V2_WEBHOOK_TYPE,
        path=f"$.{CUSTOM_WEBHOOKS_NAME}.order",
    )
    raw_data = _require_dict(
        collection_data.get("data", {}),
        path=f"$.{CUSTOM_WEBHOOKS_NAME}.data",
    )
    data_by_uid: dict[UUID, tuple[str, object]] = {}
    for raw_uid, entry in raw_data.items():
        uid, canonical_uid = _parse_uid(
            raw_uid,
            path=f"$.{CUSTOM_WEBHOOKS_NAME}.data key",
        )
        if uid in data_by_uid:
            raise ValueError(f"$.{CUSTOM_WEBHOOKS_NAME}.data 包含重复 uid")
        data_by_uid[uid] = (canonical_uid, entry)

    ordered_uids = {uid for uid, _, _ in order}
    if ordered_uids != set(data_by_uid):
        raise ValueError(
            f"$.{CUSTOM_WEBHOOKS_NAME}.order 与 data 包含缺失或孤儿 uid"
        )

    legacy: dict[str, Any] = {"instances": []}
    for uid, canonical_uid, _ in order:
        _, entry = data_by_uid[uid]
        legacy["instances"].append(
            {"uid": canonical_uid, "type": LEGACY_WEBHOOK_TYPE}
        )
        legacy[canonical_uid] = _normalize_webhook(
            entry,
            path=f"$.{CUSTOM_WEBHOOKS_NAME}.data.{canonical_uid}",
            for_rollback=True,
        )
    return legacy


def legacy_config_to_wire(legacy_data: object) -> WireDict:
    """将 r6 ``Config.json`` 纯转换为 Config v2 持久化 Wire。

    ``Data.Stage`` 是可由 ``StageData`` 重建的虚拟缓存，不进入 v2 Wire。
    当更早版本只有 ``Data.Stage`` 时，按旧 ``legacy_name='Stage'`` 规则将
    其提升为 ``StageData``。其他未知字段、孤儿 Webhook、重复 UUID、
    非法类型和值均 fail-closed。

    缺失 UID 时不猜测或随机写入 Wire；激活 ``GlobalConfig`` 时由其与 r6
    相同的 UUID 默认工厂创建。
    """

    root = _require_dict(legacy_data, path="$")
    unknown_root = sorted(set(root) - _ROOT_GROUPS - {"SubConfigsInfo"})
    if unknown_root:
        raise ValueError(
            "未知主配置路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )

    sub_configs = _require_dict(
        root.get("SubConfigsInfo", {}),
        path="$.SubConfigsInfo",
    )
    unknown_sub_configs = sorted(set(sub_configs) - {CUSTOM_WEBHOOKS_NAME})
    if unknown_sub_configs:
        raise ValueError(
            "未知主配置路径: "
            + ", ".join(
                f"$.SubConfigsInfo.{name}" for name in unknown_sub_configs
            )
        )

    return {
        "Function": _normalize_function(
            root.get("Function", {}),
            path="$.Function",
        ),
        "Voice": _normalize_voice(root.get("Voice", {}), path="$.Voice"),
        "Start": _normalize_start(root.get("Start", {}), path="$.Start"),
        "UI": _normalize_ui(root.get("UI", {}), path="$.UI"),
        "Notify": _normalize_notify(
            root.get("Notify", {}),
            path="$.Notify",
            for_rollback=False,
        ),
        "Update": _normalize_update(
            root.get("Update", {}),
            path="$.Update",
            for_rollback=False,
        ),
        "Data": _normalize_legacy_data(root.get("Data", {}), path="$.Data"),
        CUSTOM_WEBHOOKS_NAME: _legacy_webhooks_to_wire(
            sub_configs.get(CUSTOM_WEBHOOKS_NAME, {}),
        ),
    }


def config_wire_to_legacy(wire_data: object) -> dict[str, Any]:
    """将 Config v2 持久化 Wire 纯转换为可回滚的 r6 ``Config.json``。

    所有非空敏感值（包括 Webhook URL/Headers）必须已经是 DPAPI 密文；
    函数不会把明文写入 rollback 数据。派生的 ``Data.Stage`` 不写回，
    r6 ``GlobalConfig`` 加载 ``StageData`` 后会按其虚拟字段规则重建。
    """

    root = _require_dict(wire_data, path="$")
    unknown_root = sorted(set(root) - _ROOT_GROUPS - {CUSTOM_WEBHOOKS_NAME})
    if unknown_root:
        raise ValueError(
            "未知主配置路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )

    return {
        "Function": _normalize_function(
            root.get("Function", {}),
            path="$.Function",
        ),
        "Voice": _normalize_voice(root.get("Voice", {}), path="$.Voice"),
        "Start": _normalize_start(root.get("Start", {}), path="$.Start"),
        "UI": _normalize_ui(root.get("UI", {}), path="$.UI"),
        "Notify": _normalize_notify(
            root.get("Notify", {}),
            path="$.Notify",
            for_rollback=True,
        ),
        "Update": _normalize_update(
            root.get("Update", {}),
            path="$.Update",
            for_rollback=True,
        ),
        "Data": _normalize_v2_data(root.get("Data", {}), path="$.Data"),
        "SubConfigsInfo": {
            CUSTOM_WEBHOOKS_NAME: _webhooks_wire_to_legacy(
                root.get(CUSTOM_WEBHOOKS_NAME, {}),
            )
        },
    }


__all__ = [
    "CUSTOM_WEBHOOKS_NAME",
    "CustomWebhooks",
    "GlobalConfig",
    "Webhook",
    "config_wire_to_legacy",
    "legacy_config_to_wire",
]
