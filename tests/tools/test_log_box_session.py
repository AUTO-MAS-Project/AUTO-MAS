"""声明式会话的隔离、线程交付和取消契约；无需脚本或通知渠道。"""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.log_box import LogCollect, LogSpec, LogType, TranslationSpec, log_box
from app.log_box.report import build_user_result_text


def make_user():
    return SimpleNamespace(
        name="账号", result="全部完成", status="完成", push_log=[], push_log_mode="汇总"
    )


@pytest.mark.parametrize("mode", ["逐条", "汇总"])
def test_session_matches_legacy_source_and_report(tmp_path, monkeypatch, mode):
    path = tmp_path / "run.log"
    path.write_text("完成: 历史任务\n", encoding="utf-8")
    rules = ((r"完成:", r'"✅ 成功: " + $((?:完成: )(.+))'),)

    def resolve(entries):
        assert all(isinstance(entry, tuple) and len(entry) == 3 for entry in entries)
        return list(reversed(entries))

    current, previous = make_user(), make_user()
    previous.push_log_mode = mode
    legacy = LogCollect(path, sink=lambda *entry: previous.push_log.append(entry))
    legacy.open()
    for rule in rules:
        legacy.collect(*rule)
    session = log_box.get_user_session(
        LogSpec(rules=rules, postprocessor=resolve), user=current, mode=mode, paths=path
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write("完成: 邮件\n完成: 每日任务\n")
    monkeypatch.setattr("app.log_box.pipeline.time.time", lambda: 100.0)
    legacy.close(resolve)
    asyncio.run(session.close())
    assert current.push_log == previous.push_log
    assert build_user_result_text([current], False) == build_user_result_text(
        [previous], False
    )


def test_off_does_not_touch_source_rules_or_emit_error():
    class UnreadablePaths:
        def __iter__(self):
            raise AssertionError("关闭模式不得枚举来源")

    user = make_user()
    session = log_box.get_user_session(
        LogSpec(rules=(("[", ""),), failure_text="采集异常"),
        user=user,
        mode="关闭",
        paths=UnreadablePaths(),
    )
    asyncio.run(session.close())
    assert user.push_log_mode == "关闭"
    assert user.push_log == []


def test_rule_failure_does_not_fail_script_and_marker_is_once(tmp_path):
    user = make_user()
    session = log_box.get_user_session(
        LogSpec(rules=(("[", ""),), failure_text="原有失败提示"),
        user=user,
        mode="汇总",
        paths=tmp_path / "run.log",
    )

    async def scenario():
        await asyncio.gather(session.close(), session.close())
        await session.close()

    asyncio.run(scenario())
    assert user.status == "完成"
    assert len(user.push_log) == 1
    assert user.push_log[0][:2] == (LogType.NORMAL, "原有失败提示")


def test_processor_failure_keeps_original_marker_and_no_partial_nodes(tmp_path):
    path = tmp_path / "run.log"
    path.write_text("任务完成\n", encoding="utf-8")

    def fail(entries):
        raise RuntimeError("后处理失败")

    user = make_user()
    session = log_box.get_user_session(
        LogSpec(
            rules=(("任务完成", ""),),
            postprocessor=fail,
            failure_text="⚠️ 节点采集失败",
        ),
        user=user,
        mode="逐条",
        paths=path,
        start_from_end=False,
    )
    asyncio.run(session.close())
    assert user.status == "完成"
    assert len(user.push_log) == 1
    assert user.push_log[0][:2] == (LogType.NORMAL, "⚠️ 节点采集失败")


def test_delivery_failure_does_not_escape_session(tmp_path):
    class UnwritableEntries(list):
        def append(self, entry):
            raise RuntimeError("结果落点不可写")

    path = tmp_path / "run.log"
    path.write_text("任务完成\n", encoding="utf-8")
    user = make_user()
    user.push_log = UnwritableEntries()
    session = log_box.get_user_session(
        LogSpec(rules=(("任务完成", ""),), failure_text="采集失败"),
        user=user,
        mode="汇总",
        paths=path,
        start_from_end=False,
    )
    asyncio.run(session.close())
    assert user.status == "完成"


@pytest.mark.parametrize("cancel", [False, True])
def test_processing_off_loop_and_delivery_before_cancel_returns(tmp_path, cancel):
    path = tmp_path / "run.log"
    path.write_text("任务完成\n", encoding="utf-8")
    started, release = threading.Event(), threading.Event()
    worker_threads, delivery_threads = [], []
    owner_thread = threading.get_ident()

    def resolve(entries):
        worker_threads.append(threading.get_ident())
        started.set()
        assert release.wait(timeout=5)
        return entries

    class TrackedEntries(list):
        def append(self, entry):
            delivery_threads.append(threading.get_ident())
            super().append(entry)

    user = make_user()
    user.push_log = TrackedEntries()
    session = log_box.get_user_session(
        LogSpec(rules=(("任务完成", ""),), postprocessor=resolve),
        user=user,
        mode="汇总",
        paths=path,
        start_from_end=False,
    )

    async def scenario():
        closing = asyncio.create_task(session.close())
        try:
            assert await asyncio.to_thread(started.wait, 2)
            assert user.push_log == []
            assert not closing.done()
            if cancel:
                closing.cancel()
                await asyncio.sleep(0)
                closing.cancel()
                await asyncio.sleep(0)
                assert not closing.done()
        finally:
            release.set()
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                await closing
        else:
            await closing
        await session.close()

    asyncio.run(scenario())
    assert worker_threads and all(thread != owner_thread for thread in worker_threads)
    assert delivery_threads == [owner_thread]
    assert len(user.push_log) == 1


def test_concurrent_close_delivers_once_for_each_user(tmp_path):
    path = tmp_path / "run.log"
    path.write_text("任务完成\n", encoding="utf-8")
    users = [make_user(), make_user()]
    sessions = [
        log_box.get_user_session(
            LogSpec(rules=(("任务完成", ""),)),
            user=user,
            mode="逐条",
            paths=path,
            start_from_end=False,
        )
        for user in users
    ]

    async def scenario():
        await asyncio.gather(
            *(session.close() for session in sessions for _ in range(3))
        )

    asyncio.run(scenario())
    assert [len(user.push_log) for user in users] == [1, 1]


@pytest.mark.parametrize("fail", [False, True])
def test_translation_is_released_after_delivery_or_processing_error(
    tmp_path, monkeypatch, fail
):
    from app.utils.common.i18n import PoTranslator

    native, supplement, path = [
        tmp_path / name for name in ("native.po", "extra.po", "run.log")
    ]
    native.write_text('msgid "Mail"\nmsgstr "原生译文"\n', encoding="utf-8")
    supplement.write_text('msgid "Mail"\nmsgstr "邮件"\n', encoding="utf-8")
    path.write_text("Mail\n", encoding="utf-8")
    user, releases = make_user(), []
    original_clear = PoTranslator.clear

    def clear(translator):
        releases.append(list(user.push_log))
        original_clear(translator)

    def process(line):
        if fail:
            raise RuntimeError("翻译之后的处理器失败")
        return line

    monkeypatch.setattr(PoTranslator, "clear", clear)
    session = log_box.get_user_session(
        LogSpec(
            rules=(("邮件", ""),),
            preprocessor=process,
            translation=TranslationSpec(paths=(native,), supplements=(supplement,)),
            failure_text="采集失败",
        ),
        user=user,
        mode="汇总",
        paths=path,
        start_from_end=False,
    )

    async def scenario():
        await session.close()
        await session.close()

    asyncio.run(scenario())
    assert len(releases) == 1
    assert user.status == "完成"
    assert user.push_log[0][1] == ("采集失败" if fail else "邮件")
    assert bool(releases[0]) is not fail


def test_disabled_collection_does_not_load_translation(tmp_path, monkeypatch):
    from app.utils.common.i18n import PoTranslator

    def fail(*args, **kwargs):
        raise AssertionError("关闭的采集器不得加载翻译文件")

    monkeypatch.setattr(PoTranslator, "load", fail)
    user = make_user()
    session = log_box.get_user_session(
        LogSpec(rules=(("[", ""),), translation=TranslationSpec(paths=("missing.po",))),
        user=user,
        mode="汇总",
        enabled=False,
        paths=tmp_path / "run.log",
    )
    asyncio.run(session.close())
    assert user.push_log == []


def test_explicit_collection_switch_is_independent_of_display_mode(tmp_path):
    path = tmp_path / "run.log"
    path.write_text("任务完成\n", encoding="utf-8")
    user = make_user()
    session = log_box.get_user_session(
        LogSpec(rules=(("任务完成", ""),)),
        user=user,
        mode="关闭",
        enabled=True,
        paths=path,
        start_from_end=False,
    )
    asyncio.run(session.close())
    assert len(user.push_log) == 1
    assert build_user_result_text([user], False) == "账号: 全部完成"


@pytest.mark.parametrize("failure", ["load", "clear"])
def test_translation_resource_errors_keep_script_success_and_existing_marker(
    tmp_path, monkeypatch, failure
):
    from app.utils.common.i18n import PoTranslator

    path = tmp_path / "run.log"
    path.write_text("邮件\n", encoding="utf-8")
    released = []
    original_clear = PoTranslator.clear

    def clear(translator):
        released.append(True)
        if failure == "clear":
            raise RuntimeError("词表清理失败")
        original_clear(translator)

    def fail_load(*args, **kwargs):
        raise RuntimeError("词表加载失败")

    monkeypatch.setattr(PoTranslator, "clear", clear)
    if failure == "load":
        monkeypatch.setattr(PoTranslator, "load", fail_load)
    user = make_user()
    session = log_box.get_user_session(
        LogSpec(
            rules=(("邮件", ""),),
            translation=TranslationSpec(paths=()),
            failure_text="原有采集失败提示",
        ),
        user=user,
        mode="汇总",
        paths=path,
        start_from_end=False,
    )

    async def scenario():
        await session.close()
        await session.close()

    asyncio.run(scenario())
    assert released == [True]
    assert user.status == "完成"
    expected = (
        ["邮件", "原有采集失败提示"] if failure == "clear" else ["原有采集失败提示"]
    )
    assert [entry[1] for entry in user.push_log] == expected
