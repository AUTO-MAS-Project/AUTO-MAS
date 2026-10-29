"""ZZZ-OD 动态映射与账号路由迁移对照，不启动上游脚本。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.log_box import LogCollect, log_box
from app.log_box.report import build_user_result_text
from app.log_box.results import LogEntry
from app.task.ZzzOd.push_log import (
    ACCOUNT_PREFIX_RE,
    ZZZOD_PUSH_RULES,
    ZzzLogSnapshot,
    make_zzzod_log_spec,
    make_zzzod_resolve,
)


def make_user(name, mode):
    return SimpleNamespace(
        name=name, result="运行结果", status="完成", push_log=[], push_log_mode=mode
    )


@pytest.mark.parametrize("mode_a", ["关闭", "逐条", "汇总"])
@pytest.mark.parametrize("mode_b", ["关闭", "逐条", "汇总"])
@pytest.mark.parametrize("native", [False, True])
def test_routed_report_matches_legacy_with_late_account_mapping(
    tmp_path, monkeypatch, mode_a, mode_b, native
):
    path = tmp_path / "log.txt"
    path.write_text("指令[ 邮件 ] 执行成功\n", encoding="utf-8")
    previous = [make_user("甲", mode_a), make_user("乙", mode_b)]
    current = [make_user("甲", mode_a), make_user("乙", mode_b)]
    old_users = {} if native else {user.name: user for user in previous}
    state = {"idx": {}, "users": {}, "apps": frozenset()}

    def route_old(log_type, text, timestamp):
        match = ACCOUNT_PREFIX_RE.match(text)
        if match is not None and match.group(1) in old_users:
            target = old_users[match.group(1)]
            if target.push_log_mode != "关闭":
                target.push_log.append((log_type, match.group(2), timestamp))
        else:
            previous[0].push_log.append((log_type, text, timestamp))

    enabled = mode_a != "关闭" or (not native and mode_b != "关闭")
    legacy = None
    if enabled:
        legacy = LogCollect(path, sink=route_old)
        legacy.open()
        for rule in ZZZOD_PUSH_RULES:
            legacy.collect(*rule)
    session = log_box.get_user_session(
        make_zzzod_log_spec(
            lambda: ZzzLogSnapshot(
                app_names=state["apps"],
                idx_names=state["idx"],
                users=state["users"],
                fallback_user=current[0],
            )
        ),
        user=current[0],
        mode=mode_a,
        enabled=enabled,
        paths=path,
    )
    # 运行期间整个映射被重新赋值，准备时不能提前取快照。
    state["idx"] = {1: "甲", 2: "乙", 9: "原生账号"}
    state["users"] = {} if native else {user.name: user for user in current}
    state["apps"] = frozenset({"邮件", "体力刷本", "领取活跃度"})
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            "开始加载实例配置 1\n"
            "指令[ 打开游戏 ] 执行成功\n"
            "指令[ 邮件 ] 执行成功\n应用已完成 邮件\n"
            "开始加载实例配置 2\n"
            "指令[ 战斗 ] 执行失败 返回状态 驱动盘数量已达到可拥有上限\n"
            "指令[ 体力刷本 ] 执行成功 返回状态 剩余电量 90\n"
            "指令[ 领取活跃度 ] 执行失败 返回状态 操作没有完成\n"
            "开始加载实例配置 9\n指令[ 邮件 ] 执行成功\n"
        )
    monkeypatch.setattr("app.log_box.pipeline.time.time", lambda: 1793240000.0)
    if legacy is not None:
        legacy.close(make_zzzod_resolve(set(state["apps"]), state["idx"]))

    async def scenario():
        await asyncio.gather(session.close(), session.close())
        await session.close()

    asyncio.run(scenario())
    assert [user.push_log for user in current] == [user.push_log for user in previous]
    for has_uncompleted in (False, True):
        assert build_user_result_text(current, has_uncompleted) == (
            build_user_result_text(previous, has_uncompleted)
        )
    if enabled:
        assert any("原生账号" in entry[1] for entry in current[0].push_log)
    if not native and mode_b != "关闭":
        assert current[1].push_log
        assert all(not entry[1].startswith("【乙】") for entry in current[1].push_log)


def test_runtime_binding_copies_maps_before_background_processing():
    current = make_user("甲", "汇总")
    other = make_user("乙", "汇总")
    idx, users = {1: "甲", 2: "乙"}, {"甲": current, "乙": other}
    spec = make_zzzod_log_spec(
        lambda: ZzzLogSnapshot(
            app_names=frozenset({"邮件"}),
            idx_names=idx,
            users=users,
            fallback_user=current,
        )
    )
    binding = spec.bind()
    idx.clear()
    users.clear()
    parsed = binding.postprocessor(
        [
            ("普通", "SEG:1", 1.0),
            ("普通", "OK:邮件", 2.0),
            ("普通", "SEG:2", 3.0),
            ("普通", "OK:邮件", 4.0),
        ]
    )
    binding.deliver([LogEntry.from_legacy(entry) for entry in parsed])
    assert [entry[1] for entry in current.push_log] == ["✅ 成功: 邮件"]
    assert [entry[1] for entry in other.push_log] == ["✅ 成功: 邮件"]


def test_single_account_unprefixed_nodes_keep_trigger_user_fallback():
    trigger = make_user("触发用户", "逐条")
    mapped = make_user("原生账号", "汇总")
    spec = make_zzzod_log_spec(
        lambda: ZzzLogSnapshot(
            app_names=frozenset({"邮件"}),
            idx_names={1: "原生账号"},
            users={"原生账号": mapped},
            fallback_user=trigger,
        )
    )
    binding = spec.bind()
    parsed = binding.postprocessor(
        [
            ("普通", "SEG:1", 1.0),
            ("普通", "OK:邮件", 2.0),
        ]
    )
    binding.deliver([LogEntry.from_legacy(entry) for entry in parsed])
    assert [entry[1] for entry in trigger.push_log] == ["✅ 成功: 邮件"]
    assert mapped.push_log == []
