"""脱敏 legacy JSON 语料工厂。

提供 :func:`build_desensitized_legacy_corpus`，返回 8 个根文件名到脱敏
legacy dict 的映射。每个样本覆盖该根的关键嵌套结构，敏感字段统一使用
占位 DPAPI 密文 ``"DPAPI:v1:REDACTED_BASE64_PLACEHOLDER"`` 替代，绝不
包含真实明文。

所有样本均按 ``legacy_production_roots_to_wire`` →
``production_wire_roots_to_legacy`` 的规范化形式构造，即：

- 所有已知字段均显式给出（与转换器默认值一致），避免默认值填充导致
  round-trip 不等价；
- 不使用历史别名（如 ``Data.Stage``、``Emulator.Data.Type``、
  ``PluginConfig.Data.Config``、ScriptConfig 顶层 ``UserData``）；
- 敏感字段为空字符串或 DPAPI 占位密文，满足回滚边界
  ``_validate_secret_for_rollback`` 的要求；
- ``ToolsConfig.SubConfigsInfo.GameSign_Accounts`` 为空 dict，因为
  Config v2 不把它作为 Tools 根的持久化字段（由独立
  ``GameSignAccounts.json`` 持有），round-trip 后会丢失；round-trip
  比较时需对 ToolsConfig 特殊处理。

ScriptConfig 使用 ``GeneralConfig``（最简脚本类型）和 ``MaaConfig`` 两种
脚本，UserData 使用 ``GeneralUserConfig`` 和 ``MaaUserConfig`` 的最小
合法结构。由于 :mod:`app.configuration.roots.script` 对路径类字段有
运行时校验（必须指向现有目录），路径类字段统一使用空字符串。

PlanConfig 的 ``TimeSet`` 嵌套结构在 PlanConfig 根中不存在；PlanConfig
的嵌套是 ``ALL``/``Monday``..``Sunday`` 共 8 个 PlanGroup，每个包含 7 个
计划字段。``TimeSet`` 嵌套结构属于 ``QueueConfig``。

unverified 字段：
- ``ScriptConfig`` 的 ``MaaUserConfig`` 中 ``InfrastMode``/``CustomInfrast``
  相关字段仅使用默认值，未覆盖自定义基建模式分支；
- ``ScriptConfig`` 的 ``MaaEndConfig``/``SrcConfig``/``M9AConfig``/
  ``MaaFWConfig``/``OkwwConfig``/``PluginScriptConfig`` 类型未在 corpus
  中出现，仅覆盖 ``GeneralConfig`` 和 ``MaaConfig``。
"""

from __future__ import annotations

from typing import Any

# DPAPI 占位密文：以 "DPAPI:" 前缀开头，满足 is_probable_dpapi_ciphertext
_SECRET_PLACEHOLDER = "DPAPI:v1:REDACTED_BASE64_PLACEHOLDER"

# 固定 UUID（规范形式，确保 round-trip 后 key 不变）
_UID_CONFIG_WEBHOOK_1 = "00000000-0000-0000-0000-000000000010"
_UID_EMULATOR_1 = "00000000-0000-0000-0000-000000000001"
_UID_EMULATOR_2 = "00000000-0000-0000-0000-000000000002"
_UID_PLAN_1 = "00000000-0000-0000-0000-000000000001"
_UID_SCRIPT_1 = "00000000-0000-0000-0000-000000000001"
_UID_SCRIPT_2 = "00000000-0000-0000-0000-000000000002"
_UID_MAA_USER_1 = "00000000-0000-0000-0000-000000000021"
_UID_GENERAL_USER_1 = "00000000-0000-0000-0000-000000000031"
_UID_QUEUE_1 = "00000000-0000-0000-0000-000000000001"
_UID_QUEUE_2 = "00000000-0000-0000-0000-000000000002"
_UID_TIME_SET_1 = "00000000-0000-0000-0000-000000000041"
_UID_QUEUE_ITEM_1 = "00000000-0000-0000-0000-000000000051"
_UID_QUEUE_ITEM_2 = "00000000-0000-0000-0000-000000000052"
_UID_PLUGIN_1 = "00000000-0000-0000-0000-000000000001"
_UID_PLUGIN_2 = "00000000-0000-0000-0000-000000000002"
_UID_GAME_SIGN_1 = "00000000-0000-0000-0000-000000000001"
_UID_GAME_SIGN_2 = "00000000-0000-0000-0000-000000000002"


# ---------------------------------------------------------------------
# 辅助函数：生成完整的默认 group dict
# ---------------------------------------------------------------------


def _config_function_group() -> dict[str, object]:
    return {
        "HistoryRetentionTime": 0,
        "IfAllowSleep": False,
        "IfSilence": False,
        "IfAgreeBilibili": False,
        "IfBlockAd": False,
    }


def _config_voice_group() -> dict[str, object]:
    return {"Enabled": False, "Type": "simple"}


def _config_start_group() -> dict[str, object]:
    return {"IfSelfStart": False, "IfMinimizeDirectly": False}


def _config_ui_group() -> dict[str, object]:
    return {
        "IfShowTray": False,
        "IfToTray": False,
        "IfHideCloseButton": False,
    }


def _config_notify_group() -> dict[str, object]:
    return {
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


def _config_update_group() -> dict[str, object]:
    return {
        "IfAutoUpdate": False,
        "Source": "GitHub",
        "Channel": "stable",
        "ProxyAddress": "",
        "MirrorChyanCDK": _SECRET_PLACEHOLDER,
        "GitHubToken": _SECRET_PLACEHOLDER,
    }


def _config_data_group() -> dict[str, object]:
    return {
        "UID": "00000000-0000-0000-0000-000000000001",
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


def _webhook_entry(name: str = "测试 Webhook") -> dict[str, object]:
    """单个 Webhook 的规范 legacy 形状（密文字段用占位密文）。"""
    return {
        "Info": {"Name": name, "Enabled": True},
        "Data": {
            "Url": _SECRET_PLACEHOLDER,
            "Template": "template",
            "Headers": _SECRET_PLACEHOLDER,
            "Method": "POST",
        },
    }


def _config_sub_configs_info() -> dict[str, object]:
    return {
        "Notify_CustomWebhooks": {
            "instances": [
                {"uid": _UID_CONFIG_WEBHOOK_1, "type": "Webhook"},
            ],
            _UID_CONFIG_WEBHOOK_1: _webhook_entry("Config Webhook 1"),
        }
    }


def _build_config_json() -> dict[str, object]:
    """Config.json：GlobalConfig，含 Data/Function/Notify/Start/UI/Update/Voice/SubConfigsInfo.Notify_CustomWebhooks。"""
    return {
        "Function": _config_function_group(),
        "Voice": _config_voice_group(),
        "Start": _config_start_group(),
        "UI": _config_ui_group(),
        "Notify": _config_notify_group(),
        "Update": _config_update_group(),
        "Data": _config_data_group(),
        "SubConfigsInfo": _config_sub_configs_info(),
    }


def _emulator_info(name: str, type_: str, path: str) -> dict[str, object]:
    return {
        "Name": name,
        "Type": type_,
        "Path": path,
        "BossKey": "[ ]",
        "MaxWaitTime": 300,
        "ForceKillOnClose": True,
    }


def _build_emulator_config_json() -> dict[str, object]:
    """EmulatorConfig.json：MultipleConfig，含至少 2 个模拟器。"""
    return {
        "instances": [
            {"uid": _UID_EMULATOR_1, "type": "EmulatorConfig"},
            {"uid": _UID_EMULATOR_2, "type": "EmulatorConfig"},
        ],
        _UID_EMULATOR_1: {
            "Info": _emulator_info("LDPlayer", "ldplayer", "C:\\LDPlayer\\LDPlayer.exe"),
        },
        _UID_EMULATOR_2: {
            "Info": _emulator_info("MuMu", "mumu", "C:\\MuMu\\MuMuPlayer.exe"),
        },
    }


def _plan_group() -> dict[str, object]:
    return {
        "MedicineNumb": 0,
        "SeriesNumb": "0",
        "Stage": "-",
        "Stage_1": "-",
        "Stage_2": "-",
        "Stage_3": "-",
        "Stage_Remain": "-",
    }


def _build_plan_config_json() -> dict[str, object]:
    """PlanConfig.json：MultipleConfig，含至少 1 个 Plan（ALL + 7 个星期 group）。"""
    import calendar

    plan_entry: dict[str, object] = {
        "Info": {"Name": "默认计划", "Mode": "ALL"},
        "ALL": _plan_group(),
    }
    for day in calendar.day_name:
        plan_entry[day] = _plan_group()

    return {
        "instances": [
            {"uid": _UID_PLAN_1, "type": "MaaPlanConfig"},
        ],
        _UID_PLAN_1: plan_entry,
    }


def _general_user_entry(name: str = "通用用户") -> dict[str, object]:
    """GeneralUserConfig 的最小完整 legacy 形状。"""
    return {
        "Info": {
            "Name": name,
            "Status": True,
            "RemainedDay": -1,
            "IfScriptBeforeTask": False,
            "ScriptBeforeTask": "",
            "IfScriptAfterTask": False,
            "ScriptAfterTask": "",
            "Notes": "无",
        },
        "Data": {
            "LastProxyDate": "2000-01-01",
            "ProxyTimes": 0,
        },
        "Notify": {
            "Enabled": False,
            "IfSendStatistic": False,
            "IfSendMail": False,
            "ToAddress": "",
            "IfServerChan": False,
            "ServerChanKey": "",
        },
        "SubConfigsInfo": {
            "Notify_CustomWebhooks": {"instances": []},
        },
    }


def _maa_user_entry(name: str = "MAA 用户") -> dict[str, object]:
    """MaaUserConfig 的最小完整 legacy 形状。"""
    return {
        "Info": {
            "Name": name,
            "Status": True,
            "RemainedDay": -1,
            "IfScriptBeforeTask": False,
            "ScriptBeforeTask": "",
            "IfScriptAfterTask": False,
            "ScriptAfterTask": "",
            "Notes": "无",
            "Id": "",
            "Password": "",
            "Mode": "简洁",
            "StageMode": "Fixed",
            "Server": "Official",
            "Annihilation": "Annihilation",
            "InfrastMode": "Normal",
            "MedicineNumb": 0,
            "SeriesNumb": "0",
            "Stage": "-",
            "Stage_1": "-",
            "Stage_2": "-",
            "Stage_3": "-",
            "Stage_Remain": "-",
            "IfSkland": False,
            "SklandToken": "",
        },
        "Data": {
            "LastProxyDate": "2000-01-01",
            "LastSklandDate": "2000-01-01",
            "ProxyTimes": 0,
            "IfPassCheck": True,
            "CustomInfrast": "{ }",
            "InfrastIndex": "0",
        },
        "Task": {
            "IfStartUp": True,
            "IfFight": True,
            "IfInfrast": True,
            "IfRecruit": True,
            "IfMall": True,
            "IfAward": True,
            "IfRoguelike": False,
            "IfReclamation": False,
        },
        "Notify": {
            "Enabled": False,
            "IfSendStatistic": False,
            "IfSendMail": False,
            "ToAddress": "",
            "IfServerChan": False,
            "ServerChanKey": "",
            "IfSendSixStar": False,
        },
        "SubConfigsInfo": {
            "Notify_CustomWebhooks": {"instances": []},
        },
    }


def _general_script_entry(name: str = "通用脚本 1") -> dict[str, object]:
    """GeneralConfig 脚本的完整 legacy 形状。"""
    return {
        "Info": {
            "Name": name,
            "RootPath": "",
        },
        "Script": {
            "ScriptPath": "",
            "Arguments": "",
            "IfTrackProcess": False,
            "TrackProcessName": "",
            "TrackProcessExe": "",
            "TrackProcessCmdline": "",
            "ConfigPath": "",
            "ConfigPathMode": "File",
            "UpdateConfigMode": "Never",
            "LogPath": "",
            "LogPathFormat": "%Y-%m-%d",
            "LogTimeStart": 1,
            "LogTimeEnd": 1,
            "LogTimeFormat": "%Y-%m-%d %H:%M:%S",
            "SuccessLog": "",
            "ErrorLog": "",
        },
        "Game": {
            "Enabled": False,
            "Type": "Emulator",
            "Path": "",
            "URL": "",
            "ProcessName": "",
            "Arguments": "",
            "WaitTime": 0,
            "IfForceClose": False,
            "EmulatorId": "-",
            "EmulatorIndex": "-",
        },
        "Run": {
            "ProxyTimesLimit": 0,
            "RunTimesLimit": 3,
            "RunTimeLimit": 10,
        },
        "SubConfigsInfo": {
            "UserData": {
                "instances": [
                    {"uid": _UID_GENERAL_USER_1, "type": "GeneralUserConfig"},
                ],
                _UID_GENERAL_USER_1: _general_user_entry("通用用户"),
            },
        },
    }


def _maa_script_entry(name: str = "MAA 脚本") -> dict[str, object]:
    """MaaConfig 脚本的完整 legacy 形状。"""
    return {
        "Info": {
            "Name": name,
            "Path": "",
        },
        "Emulator": {
            "Id": "-",
            "Index": "-",
        },
        "Run": {
            "TaskTransitionMethod": "ExitEmulator",
            "ProxyTimesLimit": 0,
            "RunTimesLimit": 3,
            "AnnihilationTimeLimit": 40,
            "RoutineTimeLimit": 10,
            "AnnihilationAvoidWaste": False,
        },
        "SubConfigsInfo": {
            "UserData": {
                "instances": [
                    {"uid": _UID_MAA_USER_1, "type": "MaaUserConfig"},
                ],
                _UID_MAA_USER_1: _maa_user_entry("MAA 用户"),
            },
        },
    }


def _build_script_config_json() -> dict[str, object]:
    """ScriptConfig.json：MultipleConfig，含至少 2 个脚本条目。"""
    return {
        "instances": [
            {"uid": _UID_SCRIPT_1, "type": "GeneralConfig"},
            {"uid": _UID_SCRIPT_2, "type": "MaaConfig"},
        ],
        _UID_SCRIPT_1: _general_script_entry("通用脚本"),
        _UID_SCRIPT_2: _maa_script_entry("MAA 脚本"),
    }


def _time_set_entry(time: str = "08:00") -> dict[str, object]:
    import calendar

    return {
        "Info": {
            "Enabled": True,
            "Days": list(calendar.day_name),
            "Time": time,
        }
    }


def _queue_item_entry(script_id: str = "-") -> dict[str, object]:
    return {
        "Info": {"ScriptId": script_id},
    }


def _queue_entry(name: str = "队列") -> dict[str, object]:
    """单个 Queue 的完整 legacy 形状。"""
    return {
        "Info": {
            "Name": name,
            "TimeEnabled": False,
            "StartUpEnabled": False,
            "AfterAccomplish": "NoAction",
        },
        "Data": {
            "LastTimedStart": "2000-01-01 00:00",
        },
        "SubConfigsInfo": {
            "TimeSet": {
                "instances": [
                    {"uid": _UID_TIME_SET_1, "type": "TimeSet"},
                ],
                _UID_TIME_SET_1: _time_set_entry("08:00"),
            },
            "QueueItem": {
                "instances": [
                    {"uid": _UID_QUEUE_ITEM_1, "type": "QueueItem"},
                    {"uid": _UID_QUEUE_ITEM_2, "type": "QueueItem"},
                ],
                _UID_QUEUE_ITEM_1: _queue_item_entry("-"),
                _UID_QUEUE_ITEM_2: _queue_item_entry("-"),
            },
        },
    }


def _build_queue_config_json() -> dict[str, object]:
    """QueueConfig.json：MultipleConfig，含至少 2 个 QueueItem。"""
    return {
        "instances": [
            {"uid": _UID_QUEUE_1, "type": "QueueConfig"},
            {"uid": _UID_QUEUE_2, "type": "QueueConfig"},
        ],
        _UID_QUEUE_1: _queue_entry("主队列"),
        _UID_QUEUE_2: _queue_entry("备用队列"),
    }


def _build_tools_config_json() -> dict[str, object]:
    """ToolsConfig.json：含 ArknightsPC、GameSign、SubConfigsInfo.GameSign_Accounts（空）。

    注意：SubConfigsInfo.GameSign_Accounts 是 r6 历史嵌入副本，Config v2
    不把它作为 Tools 根的持久化字段。round-trip 后 SubConfigsInfo 会丢失，
    round-trip 比较时需对 ToolsConfig 特殊处理（排除 SubConfigsInfo）。
    """
    return {
        "ArknightsPC": {
            "Enabled": False,
            "PauseKey": "f10",
            "SelectDeployedKey": "w",
            "UseSkillKey": "r",
            "RetreatKey": "t",
            "NextFrameKey": "f",
            "AnotherQuitKey": "space",
        },
        "GameSign": {
            "Enabled": False,
            "NotifyEnabled": False,
            "WindowStart": "08:00",
            "WindowEnd": "22:00",
            "RunOnStartup": False,
            "ScheduledRun": True,
            "AutoStart": False,
            "LastSignDate": "2000-01-01",
            "ScheduledTime": "",
        },
        "SubConfigsInfo": {
            "GameSign_Accounts": {},
        },
    }


def _plugin_instance_entry(
    plugin: str, name: str, enabled: bool = True
) -> dict[str, object]:
    """单个 PluginInstanceConfig 的完整 legacy 形状。

    Data.ConfigRaw 使用 DPAPI 占位密文，满足回滚边界要求。
    """
    return {
        "Info": {
            "Plugin": plugin,
            "Id": "abc12",
            "Enabled": enabled,
            "Name": name,
        },
        "Data": {
            "ConfigRaw": _SECRET_PLACEHOLDER,
        },
    }


def _build_plugin_config_json() -> dict[str, object]:
    """PluginConfig.json：含至少 2 个 PluginInstanceConfig。"""
    return {
        "Data": {"Version": 1},
        "SubConfigsInfo": {
            "PluginInstances": {
                "instances": [
                    {"uid": _UID_PLUGIN_1, "type": "PluginInstanceConfig"},
                    {"uid": _UID_PLUGIN_2, "type": "PluginInstanceConfig"},
                ],
                _UID_PLUGIN_1: _plugin_instance_entry(
                    "example_plugin", "插件实例 1", True
                ),
                _UID_PLUGIN_2: _plugin_instance_entry(
                    "another_plugin", "插件实例 2", False
                ),
            }
        },
    }


def _game_sign_account_entry(name: str = "签到账号") -> dict[str, object]:
    """单个 GameSignAccountGroup 的完整 legacy 形状。"""
    return {
        "GameSignAccount": {
            "Name": name,
            "Enabled": True,
            "MiyousheToken": _SECRET_PLACEHOLDER,
            "KuroToken": "",
            "SklandToken": _SECRET_PLACEHOLDER,
            "LastSignDate": "2000-01-01",
        }
    }


def _build_game_sign_accounts_json() -> dict[str, object]:
    """GameSignAccounts.json：MultipleConfig，含至少 2 个 GameSignAccountGroup。"""
    return {
        "instances": [
            {"uid": _UID_GAME_SIGN_1, "type": "GameSignAccountGroup"},
            {"uid": _UID_GAME_SIGN_2, "type": "GameSignAccountGroup"},
        ],
        _UID_GAME_SIGN_1: _game_sign_account_entry("米游社账号"),
        _UID_GAME_SIGN_2: _game_sign_account_entry("森空岛账号"),
    }


def build_desensitized_legacy_corpus() -> dict[str, object]:
    """返回 8 个根文件名到脱敏 legacy dict 的映射。

    返回的 dict 的 key 是 legacy 文件名（如 ``"Config.json"``），value 是
    对应的脱敏 legacy dict。所有敏感字段（token/cookie/password/key）均
    使用占位密文 ``"DPAPI:v1:REDACTED_BASE64_PLACEHOLDER"`` 替代，绝不
    包含真实明文。

    EmulatorConfig.json 在此 corpus 中为非空根（含 2 个模拟器实例）。
    如需空根，可直接传入 ``{}`` 或 ``{"instances": []}``。
    """
    return {
        "Config.json": _build_config_json(),
        "EmulatorConfig.json": _build_emulator_config_json(),
        "PlanConfig.json": _build_plan_config_json(),
        "ScriptConfig.json": _build_script_config_json(),
        "QueueConfig.json": _build_queue_config_json(),
        "ToolsConfig.json": _build_tools_config_json(),
        "PluginConfig.json": _build_plugin_config_json(),
        "GameSignAccounts.json": _build_game_sign_accounts_json(),
    }


__all__ = ["build_desensitized_legacy_corpus"]
