"""宿主选择退路所需的会话结果契约，不改变 close 的异常隔离语义。"""

import asyncio
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from app.log_box import EntrySpec, LogBinding, LogSpec, SessionResult, log_box
from app.log_box.results import LogEntry


def user():
    return SimpleNamespace(push_log=[], push_log_mode="汇总")


@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize("count", [0, 2])
def test_success_and_empty_result_are_distinguishable(standalone, count):
    entries = [LogEntry("普通", "节点", 1.0)] * count
    spec = EntrySpec(
        bind=lambda: LogBinding(read=lambda: entries, deliver=lambda _: None)
    )
    session = (
        log_box.get_entry_session(spec)
        if standalone
        else log_box.get_user_session(spec, user=user(), mode="汇总")
    )
    initial = session.result
    assert initial == SessionResult("pending")
    assert asyncio.run(session.close()) is None
    assert initial.status == "pending"
    assert session.result == SessionResult("succeeded", entry_count=count)
    asyncio.run(session.close())
    assert session.result.entry_count == count
    with pytest.raises(FrozenInstanceError):
        session.result.status = "failed"
    with pytest.raises(AttributeError):
        session.result = initial


@pytest.mark.parametrize("standalone", [False, True])
def test_disabled_is_distinct_from_success(standalone):
    def bind():
        raise AssertionError("关闭不能读取来源")

    spec = EntrySpec(bind=bind)
    session = (
        log_box.get_entry_session(spec, enabled=False)
        if standalone
        else log_box.get_user_session(spec, user=user(), mode="关闭")
    )
    asyncio.run(session.close())
    assert session.result == SessionResult("disabled")


@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize("stage", ["bind", "read", "deliver"])
def test_failure_stage_does_not_expose_exception_or_retry(standalone, stage):
    received = []

    def fail():
        raise RuntimeError("不得放入状态的异常详情")

    def bind():
        if stage == "bind":
            fail()

        def read():
            if stage == "read":
                fail()
            return [LogEntry("普通", "节点", 1.0)]

        def deliver(entries):
            received.extend(entries)
            if stage == "deliver":
                fail()

        return LogBinding(read=read, deliver=deliver)

    spec = EntrySpec(bind=bind)
    session = (
        log_box.get_entry_session(spec)
        if standalone
        else log_box.get_user_session(spec, user=user(), mode="汇总")
    )
    asyncio.run(session.close())
    snapshot = session.result
    asyncio.run(session.close())
    assert session.result is snapshot
    assert snapshot == SessionResult("failed", failure_stage=stage)
    assert len(received) == (1 if stage == "deliver" else 0)


def test_log_source_initialization_failure_keeps_legacy_notice(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("测试打开故障")

    monkeypatch.setattr("app.log_box.session.LogCollect", fail)
    target = user()
    session = log_box.get_user_session(
        LogSpec(rules=(), failure_text="原有提示"),
        user=target,
        mode="汇总",
        paths=[tmp_path / "log.txt"],
    )
    asyncio.run(session.close())
    assert session.result == SessionResult("failed", failure_stage="initialize")
    assert [item[1] for item in target.push_log] == ["原有提示"]


def test_log_source_reports_delivered_count(tmp_path):
    path = tmp_path / "run.log"
    path.write_text("任务完成\n", encoding="utf-8")
    target = user()
    session = log_box.get_user_session(
        LogSpec(rules=(("任务完成", '"原样节点"'),)),
        user=target,
        mode="汇总",
        paths=[path],
        start_from_end=False,
    )
    asyncio.run(session.close())
    assert session.result == SessionResult("succeeded", entry_count=1)
    assert len(target.push_log) == 1


@pytest.mark.parametrize("read_fails", [False, True])
def test_cleanup_failure_preserves_first_failure_and_known_delivery_count(
    tmp_path, monkeypatch, read_fails
):
    from app.log_box import TranslationSpec

    class Translator:
        def load(self, *args, **kwargs):
            pass

        def load_supplement(self, *args, **kwargs):
            pass

        def translate(self, line):
            return line

        def clear(self):
            raise RuntimeError("清理故障")

    def resolve(entries):
        if read_fails:
            raise RuntimeError("读取故障")
        return entries

    monkeypatch.setattr("app.log_box.session.PoTranslator", Translator)
    path = tmp_path / "run.log"
    path.write_text("任务完成\n", encoding="utf-8")
    target = user()
    session = log_box.get_user_session(
        LogSpec(
            rules=(("任务完成", '"原样节点"'),),
            postprocessor=resolve,
            translation=TranslationSpec(paths=()),
        ),
        user=target,
        mode="汇总",
        paths=[path],
        start_from_end=False,
    )
    asyncio.run(session.close())
    assert session.result == SessionResult(
        "failed",
        entry_count=0 if read_fails else 1,
        failure_stage="read" if read_fails else "cleanup",
    )
    assert len(target.push_log) == (0 if read_fails else 1)


def test_user_delivery_preserves_missing_timestamp_and_legacy_pair():
    from app.log_box.report import build_user_result_text
    from app.models.task import UserItem

    target = UserItem(user_id="test", name="测试用户", status="完成")
    target.push_log.append(("普通", "旧二元组"))
    spec = EntrySpec(
        bind=lambda: LogBinding(read=lambda: [LogEntry("普通", "✅ 成功: 邮件")])
    )
    session = log_box.get_user_session(spec, user=target, mode="逐条")
    asyncio.run(session.close())
    assert target.push_log == [("普通", "旧二元组"), ("普通", "✅ 成功: 邮件", None)]
    assert session.result == SessionResult("succeeded", entry_count=1)
    text = build_user_result_text([target], False)
    assert text.endswith("旧二元组\n✅ 成功: 邮件")
