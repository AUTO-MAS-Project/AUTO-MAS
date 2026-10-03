#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

"""MSS（星塔旅人）特调回归测试：项目认领判据（纯函数，无 I/O）。

官方版与个人版等衍生版认成同一个脚本类型（MSSConfig）；无关项目必须落到通用 MaaFW。
判据只看 interface 的三个字段，所以用字典喂入即可。
"""

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from app.task.MSS.flavor import MSSFlavor, github_repo_name, is_mss_project

OFFICIAL = {
    "name": "MaaStellaSora",
    "github": "https://github.com/MaaStellaSora/MaaStellaSora",
    "mirrorchyan_rid": "SSAH",
}
PERSONAL = {
    "name": "MaaStellaSora-Personal",
    "github": "https://github.com/beichen24a1/MaaStellaSora-Personal",
}


def test_official_project_is_claimed() -> None:
    assert is_mss_project(OFFICIAL) is True


def test_personal_project_is_claimed() -> None:
    assert is_mss_project(PERSONAL) is True


def test_project_name_alone_is_enough() -> None:
    assert is_mss_project({"name": "MaaStellaSora"}) is True
    assert is_mss_project({"name": "maastellasora-personal"}) is True


def test_github_repo_alone_is_enough() -> None:
    assert (
        is_mss_project(
            {"github": "https://github.com/beichen24a1/MaaStellaSora-Personal"}
        )
        is True
    )
    assert (
        is_mss_project({"github": "https://github.com/MaaStellaSora/MaaStellaSora.git"})
        is True
    )


def test_unrelated_project_is_not_claimed() -> None:
    assert (
        is_mss_project({"name": "OtherProject", "github": "https://github.com/foo/bar"})
        is False
    )
    assert is_mss_project({}) is False
    ## 名字只是以 MSS 字样开头但并非本项目的，不认领
    assert is_mss_project({"name": "MaaStellaSoraX"}) is False


def test_github_side_uses_the_same_rule_as_name() -> None:
    ## 判据统一：github 与 name 同口径，只是同前缀（没有连字符）的不认领
    assert is_mss_project({"github": "https://github.com/foo/MaaStellaSoraX"}) is False
    assert (
        is_mss_project({"github": "https://github.com/foo/MaaStellaSoraPlus"}) is False
    )
    ## 连字符后缀的衍生版照旧认领
    assert (
        is_mss_project({"github": "https://github.com/foo/MaaStellaSora-Personal"})
        is True
    )
    ## 组织主页只有 owner 没有 repo，不是仓库，不认领
    assert is_mss_project({"github": "https://github.com/MaaStellaSora"}) is False
    ## 同理，光一个仓库名（没 owner）也不认领
    assert is_mss_project({"github": "MaaStellaSora"}) is False


def test_github_repo_name_parsing() -> None:
    assert (
        github_repo_name("https://github.com/MaaStellaSora/MaaStellaSora")
        == "MaaStellaSora"
    )
    assert (
        github_repo_name("https://github.com/MaaStellaSora/MaaStellaSora.git")
        == "MaaStellaSora"
    )
    assert (
        github_repo_name("https://github.com/beichen24a1/MaaStellaSora-Personal/")
        == "MaaStellaSora-Personal"
    )
    assert github_repo_name("") == ""
    assert github_repo_name("MaaStellaSora") == ""
    ## 组织主页没有仓库段
    assert github_repo_name("https://github.com/MaaStellaSora") == ""
    ## scp 风格
    assert (
        github_repo_name("git@github.com:beichen24a1/MaaStellaSora-Personal.git")
        == "MaaStellaSora-Personal"
    )
    ## 裸 owner/repo
    assert github_repo_name("foo/MaaStellaSora") == "MaaStellaSora"


## ---------------------------------------------------------------------------
## 个人版「灾变防线」的编排（一期只打一次，靠 Data.PersonalMssDefense 记账）
## ---------------------------------------------------------------------------

PERIOD_A = "2026-09-29T12:00+08:00"
PERIOD_B = "2026-10-27T12:00+08:00"

TASKS = [
    ("日常", "战斗_入口"),
    ("灾变防线", "灾变防线_入口"),
    ("爬塔", "星塔_入口_agent"),
]

## 建计划那一刻看到的运行状态；记录里的 seen_* 与它一致就表示「这一轮还没跑」
RUN_DATE = "2026-10-01"
RUN_TIMES = 3
RUN_STATUS = "成功"


class FakeConfig:
    """够用的用户配置替身：``get`` 读内存字典，``set`` 记下来。"""

    def __init__(self, data: dict[str, dict[str, Any]] | None = None) -> None:
        self.data = {group: dict(items) for group, items in (data or {}).items()}
        self.writes: list[tuple[str, str, str]] = []
        self.fail_writes = False

    def get(self, group: str, name: str) -> Any:
        try:
            return self.data[group][name]
        except KeyError:
            raise AttributeError(f"{group}.{name}") from None

    async def set(self, group: str, name: str, value: Any, commit: bool = True) -> bool:
        if self.fail_writes:
            raise ValueError("配置已锁定")
        self.data.setdefault(group, {})[name] = value
        self.writes.append((group, name, value))
        return True

    def record(self) -> dict[str, Any]:
        raw = self.data.get("Data", {}).get("PersonalMssDefense")
        return json.loads(raw) if isinstance(raw, str) else {}


def _armed_record(**overrides: Any) -> str:
    """一份「上一轮编排过、等结算」的记录；seen_* 与默认运行状态一致（= 还没跑）。"""

    record: dict[str, Any] = {
        "period": PERIOD_A,
        "done": False,
        "armed": True,
        "failed_days": [],
        "seen_date": RUN_DATE,
        "seen_times": str(RUN_TIMES),
        "seen_status": RUN_STATUS,
    }
    record.update(overrides)
    return json.dumps(record)


def _config(record: str | None = None, **run_state: Any) -> FakeConfig:
    data: dict[str, Any] = {
        "LastProxyDate": RUN_DATE,
        "ProxyTimes": RUN_TIMES,
        "LastProxyStatus": RUN_STATUS,
    }
    data.update(run_state)
    if record is not None:
        data["PersonalMssDefense"] = record
    return FakeConfig({"Info": {"PlanMode": "Fixed"}, "Data": data})


def _interface(tasks: list[tuple[str, str]] | None = None) -> Any:
    entries = tasks if tasks is not None else TASKS
    return SimpleNamespace(
        task=[SimpleNamespace(name=name, entry=entry) for name, entry in entries],
        option={},
    )


def _decorate(
    *,
    ids: list[str] | None = None,
    config: FakeConfig | None = None,
    period: str | None = PERIOD_A,
    enabled: bool = True,
    tasks: list[tuple[str, str]] | None = None,
) -> tuple[list[str], FakeConfig, list[str]]:
    config = config if config is not None else _config()
    logs: list[str] = []
    flavor = MSSFlavor(
        activity_probe=lambda: False,
        defense_period_probe=lambda: period,
        personal_mss_probe=lambda: enabled,
    )
    result, _ = flavor.decorate_selection(
        _interface(tasks),
        ids if ids is not None else ["日常"],
        {},
        script_config=None,
        user_config=config,
        resource_name=None,
        send_log=logs.append,
    )
    return result, config, logs


def test_defense_is_skipped_when_switch_is_off() -> None:
    result, config, _ = _decorate(enabled=False)
    assert result == ["日常"]
    assert config.record() == {}


def test_defense_is_ignored_when_project_has_no_such_task() -> None:
    result, config, _ = _decorate(tasks=[("日常", "战斗_入口")])
    assert result == ["日常"]
    assert config.record() == {}


def test_defense_is_added_before_climb_on_first_run() -> None:
    result, config, logs = _decorate(ids=["日常", "爬塔"])
    assert result == ["日常", "灾变防线", "爬塔"]
    record = config.record()
    assert record["period"] == PERIOD_A
    assert record["done"] is False
    assert record["armed"] is True
    assert record["failed_days"] == []
    ## 顺手把当时的运行状态记下来，下一轮拿它比「这一轮跑没跑」
    assert record["seen_status"] == RUN_STATUS
    assert record["seen_times"] == str(RUN_TIMES)
    assert any("还没打，已加入队列" in line for line in logs)


def test_defense_is_added_even_with_an_empty_queue() -> None:
    result, _, _ = _decorate(ids=[])
    assert result == ["灾变防线"]


def test_successful_run_marks_the_period_done() -> None:
    """跑过一轮并成功：ProxyTimes 会被 +1，据此才认「打过了」。"""

    config = _config(_armed_record(), ProxyTimes=RUN_TIMES + 1)
    result, config, logs = _decorate(ids=["日常", "灾变防线"], config=config)
    assert result == ["日常"]
    assert config.record()["done"] is True
    assert any("已完成，本轮跳过" in line for line in logs)


def test_cross_day_success_still_marks_the_period_done() -> None:
    """跨天时 ProxyTimes 会被清零，判据得看日期不只是看次数。"""

    config = _config(
        _armed_record(),
        LastProxyDate="2026-10-02",
        ProxyTimes=1,
    )
    result, config, _ = _decorate(ids=["日常", "灾变防线"], config=config)
    assert result == ["日常"]
    assert config.record()["done"] is True


def test_failed_run_records_one_failed_day_and_retries() -> None:
    config = _config(_armed_record(), LastProxyStatus="失败")
    result, config, _ = _decorate(ids=["日常", "爬塔"], config=config)
    assert result == ["日常", "灾变防线", "爬塔"]
    record = config.record()
    assert len(record["failed_days"]) == 1
    assert record["done"] is False
    assert record["armed"] is True


def test_a_plan_that_never_ran_does_not_settle() -> None:
    """建了计划但这一轮没跑到 run()（游戏维护、控制方式没配好都会这样）。

    这时 LastProxyStatus 还停在一个跟本轮无关的旧「成功」上，照着它结算就会把这一期
    误判成打过了、整期不再打。判据要求建计划时看到的那三个值真的变过。
    """

    config = _config(_armed_record())
    result, config, logs = _decorate(ids=["日常", "爬塔"], config=config)
    ## 仍然把它编排上，而不是判成「已完成」
    assert result == ["日常", "灾变防线", "爬塔"]
    record = config.record()
    assert record["done"] is False
    assert record["failed_days"] == []
    assert not any("已完成" in line for line in logs)


def test_a_legacy_record_without_snapshot_is_left_armed() -> None:
    """没有 seen_* 的旧记录不结算——宁可下轮再判，也不能凭一个旧状态误判成功。"""

    legacy = json.dumps(
        {"period": PERIOD_A, "done": False, "armed": True, "failed_days": []}
    )
    config = _config(legacy)
    result, config, _ = _decorate(ids=["日常", "爬塔"], config=config)
    assert result == ["日常", "灾变防线", "爬塔"]
    assert config.record()["done"] is False
    ## 这一轮 arm 时把快照补上，下一轮才有得比
    assert config.record()["seen_status"] == RUN_STATUS


def test_malformed_record_is_treated_as_empty() -> None:
    """failed_days 被写成字符串时逐字符遍历会直接顶到放弃阈值，整期不打。"""

    broken = json.dumps(
        {"period": PERIOD_A, "done": False, "armed": False, "failed_days": "abc"}
    )
    result, config, _ = _decorate(ids=["日常", "爬塔"], config=_config(broken))
    assert result == ["日常", "灾变防线", "爬塔"]
    record = config.record()
    assert record["failed_days"] == []
    assert record["done"] is False


def test_retry_on_the_same_day_does_not_add_another_failed_day() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    config = _config(
        _armed_record(failed_days=[today]),
        LastProxyStatus="失败",
    )
    _, config, _ = _decorate(ids=["日常"], config=config)
    assert config.record()["failed_days"] == [today]


def test_defense_is_given_up_after_three_failed_days() -> None:
    config = _config(
        _armed_record(
            armed=False,
            failed_days=["2026-09-29", "2026-09-30", "2026-10-01"],
        )
    )
    result, config, logs = _decorate(ids=["日常", "灾变防线", "爬塔"], config=config)
    assert result == ["日常", "爬塔"]
    assert any("不再编排" in line for line in logs)


def test_a_new_period_starts_over() -> None:
    config = _config(_armed_record(period=PERIOD_A, done=True, armed=False))
    result, config, _ = _decorate(ids=["日常", "爬塔"], config=config, period=PERIOD_B)
    assert result == ["日常", "灾变防线", "爬塔"]
    record = config.record()
    assert record["period"] == PERIOD_B
    assert record["done"] is False
    assert record["armed"] is True
    assert record["failed_days"] == []


def test_unknown_period_leaves_the_queue_alone() -> None:
    result, config, logs = _decorate(ids=["日常"], period=None)
    assert result == ["日常"]
    assert config.record() == {}
    assert any("取不到" in line for line in logs)


def test_unwritable_record_does_not_inject_the_task() -> None:
    config = _config()
    config.fail_writes = True
    result, _, logs = _decorate(ids=["日常", "爬塔"], config=config)
    assert result == ["日常", "爬塔"]
    assert any("写入失败" in line for line in logs)


def test_manually_selected_defense_is_accounted_for() -> None:
    """用户自己勾的也照记，否则手动跑成功的那次永远算不出「这期打过了」。"""

    config = _config()
    ## 第一次：记录是空的，只把它编排上并记下 armed 与当时的运行状态，队列原样
    result, config, _ = _decorate(ids=["日常", "灾变防线", "爬塔"], config=config)
    assert result == ["日常", "灾变防线", "爬塔"]
    assert config.record()["armed"] is True

    ## 跑成功了（ProxyTimes 变了），第二次就认得出来「这期打过了」
    config.data["Data"]["ProxyTimes"] = RUN_TIMES + 1
    result, config, _ = _decorate(ids=["日常", "灾变防线", "爬塔"], config=config)
    assert result == ["日常", "爬塔"]
    assert config.record()["done"] is True


def test_only_instance_is_kept_when_it_is_done() -> None:
    """队列里只剩它时不能摘空，否则引擎会把这一轮判成「无法构建运行计划」。"""

    config = _config(_armed_record(done=True, armed=False))
    result, _, logs = _decorate(ids=["灾变防线"], config=config)
    assert result == ["灾变防线"]
    assert any("只有它" in line for line in logs)
