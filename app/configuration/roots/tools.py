"""工具配置的原生 Config v2 根与 r6 兼容转换。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, Field, PrivateAttr

from app.configuration import (
    ConfigEntry,
    ConfigGroup,
    Virtual,
    WireDict,
    virtual_field,
)
from app.configuration.roots.game_sign import (
    assert_game_sign_accounts_ownership_consistent,
)
from app.utils.constants import KEYBOARD_KEYS

_ARKNIGHTS_PC_DEFAULTS: dict[str, object] = {
    "Enabled": False,
    "PauseKey": "f10",
    "SelectDeployedKey": "w",
    "UseSkillKey": "r",
    "RetreatKey": "t",
    "NextFrameKey": "f",
    "AnotherQuitKey": "space",
}
_ARKNIGHTS_PC_VIRTUAL_FIELDS = frozenset({"Status"})

_GAME_SIGN_DEFAULTS: dict[str, object] = {
    "Enabled": False,
    "NotifyEnabled": False,
    "WindowStart": "08:00",
    "WindowEnd": "22:00",
    "RunOnStartup": False,
    "ScheduledRun": True,
    "AutoStart": False,
    "LastSignDate": "2000-01-01",
    "ScheduledTime": "",
}
_GAME_SIGN_VIRTUAL_FIELDS = frozenset({"Status", "Result"})

_ROOT_GROUPS = frozenset({"ArknightsPC", "GameSign"})
_GAME_SIGN_COLLECTION_NAME = "GameSign_Accounts"


def _not_connected() -> bool:
    return False


def _validate_keyboard_key(value: str) -> str:
    if value not in KEYBOARD_KEYS:
        raise ValueError("值必须是 pyautogui 兼容键盘按键名称")
    return value


def _validate_hhmm(value: str) -> str:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        raise ValueError("时间必须使用 HH:mm 格式") from None
    return value


def _validate_ymd(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from None
    return value


KeyboardKey = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_validate_keyboard_key),
]
HHMM = Annotated[str, Field(strict=True), AfterValidator(_validate_hhmm)]
YMD = Annotated[str, Field(strict=True), AfterValidator(_validate_ymd)]


class ToolsConfig(ConfigEntry):
    """独立 ``ToolsConfig.json`` 的工具配置根。

    游戏签到账号不属于此根。r6 虽会把账号集合同时写入
    ``ToolsConfig.SubConfigsInfo`` 与 ``GameSignAccounts.json``，Config v2
    只把后者作为账号根。
    """

    class ArknightsPCGroup(ConfigGroup):
        # ArknightsPC - 是否启用工具
        Enabled: Annotated[bool, Field(strict=True)] = False
        # ArknightsPC - 暂停键
        PauseKey: KeyboardKey = "f10"
        # ArknightsPC - 选中已部署干员键
        SelectDeployedKey: KeyboardKey = "w"
        # ArknightsPC - 释放技能键
        UseSkillKey: KeyboardKey = "r"
        # ArknightsPC - 撤退键
        RetreatKey: KeyboardKey = "t"
        # ArknightsPC - 下一帧键
        NextFrameKey: KeyboardKey = "f"
        # ArknightsPC - 自定义退出/暂停键
        AnotherQuitKey: KeyboardKey = "space"
        # ArknightsPC - 运行状态标签
        Status: Virtual[str] = None

    class GameSignGroup(ConfigGroup):
        # GameSign - 是否启用签到
        Enabled: Annotated[bool, Field(strict=True)] = False
        # GameSign - 签到后是否发送通知
        NotifyEnabled: Annotated[bool, Field(strict=True)] = False
        # GameSign - 签到窗口起点
        WindowStart: HHMM = "08:00"
        # GameSign - 签到窗口终点
        WindowEnd: HHMM = "22:00"
        # GameSign - 是否在启动时运行
        RunOnStartup: Annotated[bool, Field(strict=True)] = False
        # GameSign - 是否定时运行
        ScheduledRun: Annotated[bool, Field(strict=True)] = True
        # GameSign - 是否立即开始
        AutoStart: Annotated[bool, Field(strict=True)] = False
        # GameSign - 上次签到日期
        LastSignDate: YMD = "2000-01-01"
        # GameSign - 今日随机签到时间；空串表示尚未生成
        ScheduledTime: Annotated[str, Field(strict=True)] = ""
        # GameSign - 启用状态标签
        Status: Virtual[str] = None
        # GameSign - 本次进程内签到结果
        Result: Virtual[str] = None

    ArknightsPC: ArknightsPCGroup = Field(default_factory=ArknightsPCGroup)
    GameSign: GameSignGroup = Field(default_factory=GameSignGroup)

    _arknights_pc_running: bool = PrivateAttr(default=False)
    _arknights_pc_get_connected: Callable[[], bool] = PrivateAttr(
        default_factory=lambda: _not_connected
    )
    _game_sign_result_data: dict[str, object] = PrivateAttr(default_factory=dict)

    @property
    def arknights_pc_running(self) -> bool:
        return self._arknights_pc_running

    @arknights_pc_running.setter
    def arknights_pc_running(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("arknights_pc_running 必须是布尔值")
        self._arknights_pc_running = value

    @property
    def arknights_pc_get_connected(self) -> Callable[[], bool]:
        return self._arknights_pc_get_connected

    @arknights_pc_get_connected.setter
    def arknights_pc_get_connected(
        self,
        callback: Callable[[], bool],
    ) -> None:
        if not callable(callback):
            raise TypeError("arknights_pc_get_connected 必须可调用")
        self._arknights_pc_get_connected = callback

    @property
    def arknights_pc_connected(self) -> bool:
        return self._arknights_pc_get_connected()

    @property
    def arknights_pc_keys(self) -> list[str]:
        """返回 r6 热键操作顺序，不包含暂停键。"""

        return [
            self.ArknightsPC.SelectDeployedKey,
            self.ArknightsPC.UseSkillKey,
            self.ArknightsPC.RetreatKey,
            self.ArknightsPC.NextFrameKey,
            self.ArknightsPC.AnotherQuitKey,
        ]

    @virtual_field("ArknightsPC.Status")
    def arknights_pc_status(self) -> str:
        if not self.ArknightsPC.Enabled:
            return json.dumps(
                {"text": "未启用", "color": "gray"},
                ensure_ascii=False,
            )
        if not self._arknights_pc_running:
            return json.dumps(
                {"text": "已暂停", "color": "yellow"},
                ensure_ascii=False,
            )
        if self.arknights_pc_connected:
            return json.dumps(
                {"text": "运行中", "color": "green"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"text": "未连接", "color": "red"},
            ensure_ascii=False,
        )

    @virtual_field("GameSign.Status")
    def game_sign_status(self) -> str:
        if not self.GameSign.Enabled:
            return json.dumps(
                {"text": "未启用", "color": "gray"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"text": "已启用", "color": "green"},
            ensure_ascii=False,
        )

    @virtual_field("GameSign.Result")
    def game_sign_result(self) -> str:
        return json.dumps(self._game_sign_result_data, ensure_ascii=False)


def _require_dict(value: object, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{path} 必须是对象")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{path} 的键必须是字符串")
    return value


def _normalize_arknights_pc(
    value: object,
    *,
    path: str,
    legacy: bool,
) -> WireDict:
    group = _require_dict(value, path=path)
    allowed = set(_ARKNIGHTS_PC_DEFAULTS)
    if legacy:
        allowed.update(_ARKNIGHTS_PC_VIRTUAL_FIELDS)
    unknown = sorted(set(group) - allowed)
    if unknown:
        raise ValueError(
            "未知工具配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )

    if legacy and "Status" in group and not isinstance(group["Status"], str):
        raise TypeError(f"{path}.Status 必须是字符串")

    normalized = dict(_ARKNIGHTS_PC_DEFAULTS)
    normalized.update(
        {
            name: group[name]
            for name in _ARKNIGHTS_PC_DEFAULTS
            if name in group
        }
    )
    if not isinstance(normalized["Enabled"], bool):
        raise TypeError(f"{path}.Enabled 必须是布尔值")
    for name in (
        "PauseKey",
        "SelectDeployedKey",
        "UseSkillKey",
        "RetreatKey",
        "NextFrameKey",
        "AnotherQuitKey",
    ):
        value = normalized[name]
        if not isinstance(value, str):
            raise TypeError(f"{path}.{name} 必须是字符串")
        _validate_keyboard_key(value)
    return normalized


def _normalize_game_sign(
    value: object,
    *,
    path: str,
    legacy: bool,
) -> WireDict:
    group = _require_dict(value, path=path)
    allowed = set(_GAME_SIGN_DEFAULTS)
    if legacy:
        allowed.update(_GAME_SIGN_VIRTUAL_FIELDS)
    unknown = sorted(set(group) - allowed)
    if unknown:
        raise ValueError(
            "未知工具配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )

    if legacy:
        for name in _GAME_SIGN_VIRTUAL_FIELDS:
            if name in group and not isinstance(group[name], str):
                raise TypeError(f"{path}.{name} 必须是字符串")

    normalized = dict(_GAME_SIGN_DEFAULTS)
    normalized.update(
        {
            name: group[name]
            for name in _GAME_SIGN_DEFAULTS
            if name in group
        }
    )
    for name in (
        "Enabled",
        "NotifyEnabled",
        "RunOnStartup",
        "ScheduledRun",
        "AutoStart",
    ):
        if not isinstance(normalized[name], bool):
            raise TypeError(f"{path}.{name} 必须是布尔值")
    for name in (
        "WindowStart",
        "WindowEnd",
        "LastSignDate",
        "ScheduledTime",
    ):
        if not isinstance(normalized[name], str):
            raise TypeError(f"{path}.{name} 必须是字符串")
    _validate_hhmm(normalized["WindowStart"])
    _validate_hhmm(normalized["WindowEnd"])
    _validate_ymd(normalized["LastSignDate"])
    return normalized


def legacy_tools_to_wire(
    legacy_data: object,
    *,
    standalone_game_sign_accounts_legacy: object | None,
) -> WireDict:
    """将 r6 ``ToolsConfig.json`` 纯转换为 Config v2 Wire。

    调用方必须显式提供独立 ``GameSignAccounts.json`` 的解析结果（文件缺失
    时传 ``None``）。转换复用账号根的所有权检查；两份非空副本不同、
    任一副本结构非法或含明文 token 时均 fail-closed。账号数据和三个虚拟
    缓存字段不会进入 Tools Wire。
    """

    root = _require_dict(legacy_data, path="$")
    unknown_root = sorted(set(root) - _ROOT_GROUPS - {"SubConfigsInfo"})
    if unknown_root:
        raise ValueError(
            "未知工具配置路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )

    sub_configs = _require_dict(
        root.get("SubConfigsInfo", {}),
        path="$.SubConfigsInfo",
    )
    unknown_sub_configs = sorted(
        set(sub_configs) - {_GAME_SIGN_COLLECTION_NAME}
    )
    if unknown_sub_configs:
        raise ValueError(
            "未知工具配置路径: "
            + ", ".join(
                f"$.SubConfigsInfo.{name}" for name in unknown_sub_configs
            )
        )

    assert_game_sign_accounts_ownership_consistent(
        standalone_legacy=standalone_game_sign_accounts_legacy,
        tools_config_legacy=root,
    )

    return {
        "ArknightsPC": _normalize_arknights_pc(
            root.get("ArknightsPC", {}),
            path="$.ArknightsPC",
            legacy=True,
        ),
        "GameSign": _normalize_game_sign(
            root.get("GameSign", {}),
            path="$.GameSign",
            legacy=True,
        ),
    }


def tools_wire_to_legacy(wire_data: object) -> dict[str, Any]:
    """将 Tools Config v2 Wire 纯转换为可回滚的 r6 配置。

    回滚结果只包含 Tools 根拥有的持久字段。虚拟字段由 r6 重新计算；
    ``GameSign_Accounts`` 由独立 ``GameSignAccounts.json`` 回滚，不在这里
    复制，因此此函数不存在把账号明文 token 写入 Tools 文件的路径。
    """

    root = _require_dict(wire_data, path="$")
    unknown_root = sorted(set(root) - _ROOT_GROUPS)
    if unknown_root:
        raise ValueError(
            "未知工具配置路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )

    return {
        "ArknightsPC": _normalize_arknights_pc(
            root.get("ArknightsPC", {}),
            path="$.ArknightsPC",
            legacy=False,
        ),
        "GameSign": _normalize_game_sign(
            root.get("GameSign", {}),
            path="$.GameSign",
            legacy=False,
        ),
    }


__all__ = [
    "ToolsConfig",
    "legacy_tools_to_wire",
    "tools_wire_to_legacy",
]
