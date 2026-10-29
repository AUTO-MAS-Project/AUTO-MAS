"""结构化节点来源的格式、隔离与交付契约。"""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.log_box import LogBinding, LogSpec, log_box
from app.log_box.results import LogEntry


def make_user():
    return SimpleNamespace(push_log=[], push_log_mode="汇总", status="完成")


def test_entry_source_never_opens_a_log_file(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("结构化来源不得创建文件采集器")

    monkeypatch.setattr("app.log_box.session.LogCollect", fail)
    monkeypatch.setenv("MAS_SCRIPT_LOG_PATH", str(tmp_path / "unrelated.log"))
    user, calls, threads = make_user(), [], []
    owner = threading.get_ident()

    def read():
        threads.append(threading.get_ident())
        return [LogEntry("普通", "✅ 成功: 邮件", 1.0)]

    def bind():
        calls.append(threading.get_ident())
        return LogBinding(read=read)

    session = log_box.get_user_session(
        LogSpec(rules=(), source="entries", bind=bind), user=user, mode="汇总"
    )

    async def scenario():
        await asyncio.gather(session.close(), session.close())
        await session.close()

    asyncio.run(scenario())
    assert calls == [owner]
    assert threads and all(thread != owner for thread in threads)
    assert user.push_log == [("普通", "✅ 成功: 邮件", 1.0)]


@pytest.mark.parametrize("result", [None, ("普通", "文本", 1.0), ["文本"]])
def test_invalid_entry_shape_is_isolated_and_does_not_partially_deliver(result):
    user = make_user()
    spec = LogSpec(
        rules=(),
        source="entries",
        bind=lambda: LogBinding(read=lambda: result),
        failure_text="原有提示",
    )
    session = log_box.get_user_session(spec, user=user, mode="汇总")
    asyncio.run(session.close())
    assert user.status == "完成"
    assert [entry[1] for entry in user.push_log] == ["原有提示"]


def test_read_failure_isolated_and_reported_once():
    def read():
        raise RuntimeError("结构化读取失败")

    user = make_user()
    session = log_box.get_user_session(
        LogSpec(
            rules=(),
            source="entries",
            bind=lambda: LogBinding(read=read),
            failure_text="原有提示",
        ),
        user=user,
        mode="汇总",
    )

    async def scenario():
        await session.close()
        await session.close()

    asyncio.run(scenario())
    assert user.status == "完成"
    assert [entry[1] for entry in user.push_log] == ["原有提示"]


def test_disabled_entry_source_does_not_bind_or_read():
    def bind():
        raise AssertionError("关闭来源时不得执行绑定")

    user = make_user()
    session = log_box.get_user_session(
        LogSpec(rules=(), source="entries", bind=bind), user=user, mode="关闭"
    )
    asyncio.run(session.close())
    assert user.push_log == []


@pytest.mark.parametrize(
    "field", ["rules", "preprocessor", "postprocessor", "translation"]
)
def test_entry_source_cannot_mix_text_processing(field):
    from app.log_box import TranslationSpec

    options = {
        "rules": (("pattern", ""),),
        "preprocessor": lambda line: line,
        "postprocessor": lambda entries: entries,
        "translation": TranslationSpec(paths=()),
    }
    kwargs = {"rules": (), "source": "entries", field: options[field]}
    with pytest.raises(ValueError):
        LogSpec(**kwargs)


def test_custom_entry_delivery_stays_on_host_and_does_not_duplicate_default():
    owner = threading.get_ident()
    received, user = [], make_user()

    def deliver(entries):
        assert threading.get_ident() == owner
        received.extend(entries)

    item = LogEntry("普通", "节点", 1.0)
    session = log_box.get_user_session(
        LogSpec(
            rules=(),
            source="entries",
            bind=lambda: LogBinding(read=lambda: [item], deliver=deliver),
        ),
        user=user,
        mode="汇总",
    )
    asyncio.run(session.close())
    assert received == [item]
    assert user.push_log == []


def test_cancelled_close_waits_for_entry_delivery_before_propagating():
    started, release = threading.Event(), threading.Event()
    user = make_user()

    def read():
        started.set()
        assert release.wait(timeout=5)
        return [LogEntry("普通", "已确认节点", 1.0)]

    session = log_box.get_user_session(
        LogSpec(rules=(), source="entries", bind=lambda: LogBinding(read=read)),
        user=user,
        mode="汇总",
    )

    async def scenario():
        closing = asyncio.create_task(session.close())
        try:
            assert await asyncio.to_thread(started.wait, 5)
            closing.cancel()
            await asyncio.sleep(0)
            assert not closing.done()
            assert user.push_log == []
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert user.push_log == [("普通", "已确认节点", 1.0)]
        await session.close()
        assert len(user.push_log) == 1

    asyncio.run(scenario())
