"""专项自己管理读取、交付和取消，不通过公共采集会话。"""

import asyncio
import importlib
import threading
from types import SimpleNamespace

import pytest


@pytest.fixture(params=["Okww", "OkNte", "BAAH", "ZzzOd"])
def capture(request, tmp_path, monkeypatch):
    adapter = request.param
    module = importlib.import_module(f"app.task.{adapter}.AutoProxy")
    proxy = module.AutoProxyTask.__new__(module.AutoProxyTask)
    user = SimpleNamespace(push_log=[], push_log_mode="汇总", status="完成")
    proxy.cur_user_item = user
    proxy.script_root_path = tmp_path
    proxy._push_user_book = {}
    proxy._idx_names = {}
    proxy._app_name_book = {}
    if adapter == "Okww":
        native = tmp_path / module._push_log.OKWW_REL_I18N_PO
        native.parent.mkdir(parents=True)
        native.write_text("", encoding="utf-8")
        supplement = tmp_path / "extra.po"
        supplement.write_text("", encoding="utf-8")
        monkeypatch.setattr(module._push_log, "_okww_supplement_po", lambda: supplement)
    if adapter == "ZzzOd":
        monkeypatch.setattr(
            module._push_log,
            "make_zzzod_resolve",
            lambda names, indices: lambda entries: entries,
        )
    path = tmp_path / "run.log"
    path.write_text("历史内容\n", encoding="utf-8")
    proxy._prepare_log_details(path, mode="汇总", enabled=True, rotated_name=None)
    assert proxy._log_pipeline is not None
    proxy._log_pipeline.line_rules.clear()
    proxy._log_pipeline.postprocessors.clear()
    proxy._log_pipeline.add_rule("完成:", '"✅ 成功: " + $((?:完成: )(.+))', "普通")
    with path.open("a", encoding="utf-8") as stream:
        stream.write("完成: 邮件\n")
    return proxy, user, path, module


def test_offset_concurrent_close_and_user_ownership(capture):
    proxy, user, path, module = capture
    other = SimpleNamespace(push_log=[], push_log_mode="汇总")
    proxy.cur_user_item = other

    async def run():
        await asyncio.gather(proxy._close_log_details(), proxy._close_log_details())
        await proxy._close_log_details()

    asyncio.run(run())
    assert [entry[1] for entry in user.push_log] == ["✅ 成功: 邮件"]
    assert other.push_log == []
    assert user.status == "完成"


@pytest.mark.parametrize("cancel", [False, True])
def test_worker_processing_and_host_delivery_finish_before_cancel(capture, cancel):
    proxy, user, path, module = capture
    started, release = threading.Event(), threading.Event()
    worker_threads, owner_threads = [], []
    owner = threading.get_ident()

    def process(entries):
        worker_threads.append(threading.get_ident())
        started.set()
        assert release.wait(5)
        return entries

    class Entries(list):
        def append(self, item):
            owner_threads.append(threading.get_ident())
            super().append(item)

    user.push_log = Entries()
    proxy._log_pipeline.postprocessors.append(process)

    async def run():
        closing = asyncio.create_task(proxy._close_log_details())
        try:
            assert await asyncio.to_thread(started.wait, 3)
            assert not closing.done() and user.push_log == []
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
        await proxy._close_log_details()

    asyncio.run(run())
    assert worker_threads and all(thread != owner for thread in worker_threads)
    assert owner_threads == [owner]


def test_processing_failure_isolated_without_partial_results(capture):
    proxy, user, path, module = capture

    def fail(entries):
        raise RuntimeError("processor failed")

    proxy._log_pipeline.postprocessors.append(fail)

    async def run():
        await proxy._close_log_details()
        await proxy._close_log_details()

    asyncio.run(run())
    expected = [] if module.__name__.split(".")[2] == "ZzzOd" else ["⚠️ 节点采集失败"]
    assert [entry[1] for entry in user.push_log] == expected
    assert user.status == "完成"


def test_disabled_caller_does_not_read_or_compile(capture):
    proxy, user, path, module = capture
    proxy._prepare_log_details(None, mode="关闭", enabled=False, rotated_name=None)
    asyncio.run(proxy._close_log_details())
    assert user.push_log == []
    assert proxy._log_source is None and proxy._log_pipeline is None


def test_initialization_failure_keeps_failure_policy_with_caller(capture, monkeypatch):
    proxy, user, path, module = capture

    def fail(*args, **kwargs):
        raise ValueError("invalid rule")

    monkeypatch.setattr(module.log_box.LogPipeline, "add_rule", fail)
    proxy._prepare_log_details(path, mode="汇总", enabled=True, rotated_name=None)
    asyncio.run(proxy._close_log_details())
    expected = [] if module.__name__.split(".")[2] == "ZzzOd" else ["⚠️ 节点采集失败"]
    assert [entry[1] for entry in user.push_log] == expected
    assert user.status == "完成"


def test_delivery_failure_is_not_retried(capture):
    proxy, user, path, module = capture
    attempts = []

    class Unwritable(list):
        def append(self, item):
            attempts.append(item)
            raise RuntimeError("sink failed")

    user.push_log = Unwritable()

    async def run():
        await proxy._close_log_details()
        before = len(attempts)
        await proxy._close_log_details()
        assert len(attempts) == before

    asyncio.run(run())
    assert attempts and user.status == "完成"


def test_okww_translation_cleanup_failure_preserves_delivered_nodes(
    tmp_path, monkeypatch
):
    from app.task.Okww import AutoProxy as module

    native = tmp_path / module._push_log.OKWW_REL_I18N_PO
    native.parent.mkdir(parents=True)
    native.write_text('msgid "Mail"\nmsgstr "领取邮件"\n', encoding="utf-8")
    supplement = tmp_path / "extra.po"
    supplement.write_text("", encoding="utf-8")
    monkeypatch.setattr(module._push_log, "_okww_supplement_po", lambda: supplement)
    proxy = module.AutoProxyTask.__new__(module.AutoProxyTask)
    user = SimpleNamespace(push_log=[], push_log_mode="汇总", status="完成")
    proxy.cur_user_item, proxy.script_root_path = user, tmp_path
    path = tmp_path / "run.log"
    path.write_text("", encoding="utf-8")
    proxy._prepare_log_details(path, mode="汇总", enabled=True, rotated_name=None)
    path.write_text("Mail\n", encoding="utf-8")

    def fail():
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(proxy._log_translator, "clear", fail)

    async def run():
        await proxy._close_log_details()
        await proxy._close_log_details()

    asyncio.run(run())
    assert [entry[1] for entry in user.push_log] == ["✅ 成功: 邮件", "⚠️ 节点采集失败"]
    assert user.status == "完成"
