"""直控 + 快速配置：把面板值写进 BGI 原生一条龙配置时，不得改动用户的任务启停。

2026-09-18/19 用户反馈「直控模式下任务跑不起来」：AutoProxy 在直控下把组的开关列表留空
（面板 Groups 不参与直控），而 ``apply_groups`` 把空表理解成「全部关掉」，于是运行期间
用户启好的内置一条龙任务全被写成关闭 —— 一条龙部分瞬间结束、只剩自定义配置组任务在跑
（两份日志 + 本机复现均坐实）。这里按写入函数的行为立回归。
"""

import json
from pathlib import Path

from app.task.BetterGI.tools import one_dragon, one_dragon_plan

_CONFIG_NAME = "MAS测试"
_BUILTIN_UID = "2c7d8a5b-ab15-4b41-96a3-b6dcda401112"
_OTHER_BUILTIN_UID = "8f0a1d62-2f6b-4c2a-9d6e-1c3b5a7e9f01"
_CUSTOM_UID = "5b1c9d34-7a2e-4f81-8c6d-0e2f4a6b8c10"


def _seed(tmp_path: Path, enabled: dict[str, bool] | None = None) -> Path:
    """造一份最小原生一条龙配置：1 内置任务（默认可换成关）+ 1 自定义配置组。"""
    path = one_dragon.one_dragon_path(tmp_path, _CONFIG_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "Name": _CONFIG_NAME,
                "TaskDefinitions": {
                    _BUILTIN_UID: "领取邮件",
                    _OTHER_BUILTIN_UID: "自动地脉花",
                    _CUSTOM_UID: "自动晶蝶",
                },
                "TaskOrder": [_BUILTIN_UID, _CUSTOM_UID],
                "TaskEnabledList": {
                    _BUILTIN_UID: True,
                    _OTHER_BUILTIN_UID: False,
                    _CUSTOM_UID: True,
                    **(enabled or {}),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _write(tmp_path: Path, **overrides) -> dict:
    written = one_dragon.write_native_one_dragon(
        tmp_path, _CONFIG_NAME, [], **overrides
    )
    assert written is not None
    return written


def test_empty_group_list_keeps_enabled_builtin_task_on(tmp_path):
    path = _seed(tmp_path)

    written = _write(tmp_path, party_name="通用队")

    # 回归核心：内置任务仍是启用（此前会被写成 false，任务直接不跑）
    assert written["TaskEnabledList"][_BUILTIN_UID] is True
    assert written["TaskOrder"] == [_BUILTIN_UID, _CUSTOM_UID]
    # 非组字段照旧写进去（面板值该写的还得写）
    assert written["PartyName"] == "通用队"
    assert json.loads(path.read_text(encoding="utf-8"))["PartyName"] == "通用队"


def test_empty_group_list_keeps_disabled_task_off(tmp_path):
    _seed(tmp_path, {_BUILTIN_UID: False})

    written = _write(tmp_path)

    # 用户自己关掉的任务不能被「保留启停」顺手打开，也不该凭空补进队列
    assert written["TaskEnabledList"][_BUILTIN_UID] is False
    assert _OTHER_BUILTIN_UID not in written["TaskOrder"]


def test_empty_group_list_keeps_custom_group_state(tmp_path):
    _seed(tmp_path)

    written = _write(tmp_path)

    # 自定义配置组不由 MAS 管理（直控）：启用状态与引用原样保留
    assert written["TaskEnabledList"][_CUSTOM_UID] is True
    assert written["TaskDefinitions"][_CUSTOM_UID] == "自动晶蝶"


def test_caller_supplied_groups_still_switch_tasks(tmp_path):
    _seed(tmp_path)

    # 显式给开关时按开关走（原有语义不变）：只开「自动地脉花」→ 领取邮件关、地脉花补建并开
    written = one_dragon.write_native_one_dragon(
        tmp_path, _CONFIG_NAME, ["自动地脉花"]
    )

    assert written is not None
    assert written["TaskEnabledList"][_BUILTIN_UID] is False
    by_name = {written["TaskDefinitions"][uid]: uid for uid in written["TaskOrder"]}
    assert written["TaskEnabledList"][by_name["自动地脉花"]] is True


def test_plan_weekly_tables_flatten_to_native_keys():
    """2026-09-19 ⑥：Plan 里的嵌套周表要展平成一条龙顶层键，才能随快速配置写进原生配置。

    此前周表整体不参与对齐，直控 + 快速配置下面板改了周表却不生效（BGI 仍按自己那份
    旧周表执行），执行层路径与原生路径对同一份 Plan 得出不同结果。
    """
    settings = one_dragon_plan.plan_steps_to_native_settings(
        [
            {
                "name": "自动秘境",
                "settings": {
                    "domainName": "步骤级秘境",
                    "partyName": "步骤级队伍",
                    "weeklyDomainEnabled": True,
                    "weeklyDomain": {
                        "default": {"domainName": "默认秘境", "reward": "1"},
                        "Monday": {"domainName": "周一秘境", "run": True},
                        "Tuesday": {"domainName": "周二秘境", "run": False},
                    },
                },
            },
            {
                "name": "自动地脉花",
                "settings": {
                    "leyLineDailyEnabled": False,
                    "weeklyLeyLine": {
                        "default": {"country": "蒙德", "type": "藏金之花"},
                        "Monday": {"country": "璃月", "type": "启示之花", "run": True},
                    },
                },
            },
        ]
    )

    domain = settings["自动秘境"]
    assert domain["MondayDomainName"] == "周一秘境"
    assert domain["DomainRunMonday"] is True
    # 未勾选的行也必须写：False 是「当天不执行」的唯一载体
    assert domain["DomainRunTuesday"] is False
    assert domain["SundayWeeklySelectedValue"] == "1"
    assert domain["WeeklyDomainEnabled"] is True
    # 默认行覆盖步骤级（与执行层 main.js 的「当天行 → 默认行 → 步骤级」取值链一致）
    assert domain["DomainName"] == "默认秘境"

    leyline = settings["自动地脉花"]
    assert leyline["LeyLineMondayCountry"] == "璃月"
    assert leyline["LeyLineMondayType"] == "启示之花"
    assert leyline["LeyLineRunMonday"] is True
    assert leyline["LeyLineDefaultType"] == "藏金之花"


def test_plan_group_with_only_false_weekly_flag_is_kept():
    """PR #896 review：返回值按真值过滤的是「整桶」而非叶子值，False 不会被丢掉。

    触发条件取自 review——快速配置用户取消勾选某个工作日，而它是该组唯一写出的值。
    """
    settings = one_dragon_plan.plan_steps_to_native_settings(
        [
            {
                "name": "自动秘境",
                "settings": {"weeklyDomain": {"Tuesday": {"run": False}}},
            }
        ]
    )

    # 桶里只有 False 也必须原样返回，否则原生表会保留旧的「已启用」标记
    assert settings == {"自动秘境": {"DomainRunTuesday": False}}


def test_combat_plan_settings_reach_native_one_dragon_file(tmp_path):
    """2026-09-19 ⑥：秘境/地脉花的 per-任务键与周表键要落一条龙文件。

    此前秘境的整桶只送去 write_global_domain_settings，而它的白名单只管「秘境刷取配置」
    那几个叶子，于是 DomainName / PartyName / WeeklyDomainEnabled / 周表键全被静默丢弃。
    """
    _seed(tmp_path)

    written = _write(
        tmp_path,
        native_step_settings={
            "自动秘境": {
                "DomainName": "某秘境",
                "PartyName": "秘境队",
                "WeeklyDomainEnabled": True,
                "MondayDomainName": "周一秘境",
                "DomainRunTuesday": False,
                # 全局段叶子（autoDomainConfig / autoArtifactSalvageConfig）：不进一条龙文件
                "originalResinUseCount": 3,
                "maxArtifactStar": "4",
            },
            "自动地脉花": {
                "LeyLineMondayType": "藏金之花",
                "LeyLineRunMonday": True,
            },
        },
    )

    assert written["DomainName"] == "某秘境"
    assert written["PartyName"] == "秘境队"
    assert written["WeeklyDomainEnabled"] is True
    assert written["MondayDomainName"] == "周一秘境"
    assert written["DomainRunTuesday"] is False
    assert written["LeyLineMondayType"] == "藏金之花"
    assert written["LeyLineRunMonday"] is True
    # 全局段叶子不落一条龙文件：各自写入器（全局 config.json）负责，避免留脏键
    assert "maxArtifactStar" not in written
    assert "originalResinUseCount" not in written
