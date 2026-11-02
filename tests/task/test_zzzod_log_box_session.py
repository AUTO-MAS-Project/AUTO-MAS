"""ZZZ 自己固定运行后映射和交付账号结果。"""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.task.ZzzOd.AutoProxy import AutoProxyTask


def user(name, mode):
    return SimpleNamespace(name=name, push_log=[], push_log_mode=mode)


@pytest.mark.parametrize("mode_a", ["关闭", "逐条", "汇总"])
@pytest.mark.parametrize("mode_b", ["关闭", "逐条", "汇总"])
@pytest.mark.parametrize("native", [False, True])
def test_late_mapping_routes_known_accounts_and_keeps_native_fallback(
    tmp_path, mode_a, mode_b, native
):
    first, second = user("甲", mode_a), user("乙", mode_b)
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_item = first
    proxy._idx_names, proxy._push_user_book, proxy._app_name_book = {}, {}, {}
    path = tmp_path / "log.txt"
    path.write_text("指令[ 邮件 ] 执行成功\n", encoding="utf-8")
    enabled = mode_a != "关闭" or (not native and mode_b != "关闭")
    proxy._prepare_log_details(path, mode=mode_a, enabled=enabled, rotated_name=None)
    # Mapping is established after collection starts, as it is during a real run.
    proxy._idx_names = {1: "甲", 2: "乙", 9: "原生账号"}
    proxy._push_user_book = {} if native else {"甲": first, "乙": second}
    proxy._app_name_book = {"mail": "邮件"}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            "开始加载实例配置 1\n指令[ 邮件 ] 执行成功\n开始加载实例配置 2\n指令[ 邮件 ] 执行成功\n开始加载实例配置 9\n指令[ 邮件 ] 执行成功\n"
        )

    async def run():
        await asyncio.gather(proxy._close_log_details(), proxy._close_log_details())
        await proxy._close_log_details()

    asyncio.run(run())
    if not enabled:
        assert first.push_log == second.push_log == []
        return
    assert any("原生账号" in entry[1] for entry in first.push_log)
    if native:
        assert len(first.push_log) == 3 and second.push_log == []
    else:
        assert any(entry[1] == "✅ 成功: 邮件" for entry in first.push_log) == (
            mode_a != "关闭"
        )
        assert bool(second.push_log) == (mode_b != "关闭")
        assert all(not entry[1].startswith("【乙】") for entry in second.push_log)


def test_single_account_unprefixed_node_keeps_trigger_fallback(tmp_path):
    first, mapped = user("触发用户", "逐条"), user("原生账号", "汇总")
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_item = first
    proxy._idx_names = {1: "原生账号"}
    proxy._push_user_book = {"原生账号": mapped}
    proxy._app_name_book = {"mail": "邮件"}
    path = tmp_path / "log.txt"
    path.write_text("", encoding="utf-8")
    proxy._prepare_log_details(path, mode="逐条", enabled=True, rotated_name=None)
    path.write_text("开始加载实例配置 1\n指令[ 邮件 ] 执行成功\n", encoding="utf-8")
    asyncio.run(proxy._close_log_details())
    assert [entry[1] for entry in first.push_log] == ["✅ 成功: 邮件"]
    assert mapped.push_log == []


def test_mapping_is_copied_before_worker_reads(tmp_path):
    first, second = user("甲", "汇总"), user("乙", "汇总")
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_item = first
    proxy._idx_names = {1: "甲", 2: "乙"}
    proxy._push_user_book = {"甲": first, "乙": second}
    proxy._app_name_book = {"mail": "邮件"}
    path = tmp_path / "log.txt"
    path.write_text("", encoding="utf-8")
    proxy._prepare_log_details(path, mode="汇总", enabled=True, rotated_name=None)
    path.write_text(
        "开始加载实例配置 1\n指令[ 邮件 ] 执行成功\n开始加载实例配置 2\n指令[ 邮件 ] 执行成功\n",
        encoding="utf-8",
    )
    started, release = threading.Event(), threading.Event()
    read = proxy._log_source.read_new

    def blocking_read():
        started.set()
        assert release.wait(5)
        return read()

    proxy._log_source.read_new = blocking_read

    async def run():
        task = asyncio.create_task(proxy._close_log_details())
        try:
            assert await asyncio.to_thread(started.wait, 3)
            proxy._idx_names.clear()
            proxy._push_user_book.clear()
            proxy._app_name_book.clear()
        finally:
            release.set()
        await task

    asyncio.run(run())
    assert [e[1] for e in first.push_log] == ["✅ 成功: 邮件"]
    assert [e[1] for e in second.push_log] == ["✅ 成功: 邮件"]
