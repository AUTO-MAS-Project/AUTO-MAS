"""ZZZ 自己固定运行后映射和交付账号结果。"""

import asyncio

from app.task.ZzzOd.AutoProxy import AutoProxyTask
from tests.runtime_support import RuntimeStub as SimpleNamespace


def user(name, mode):
    return SimpleNamespace(name=name, push_log=[], push_log_mode=mode)


def _proxy_for_log(first):
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.user_state = lambda user: user
    proxy.callbacks = SimpleNamespace()
    proxy.cur_user_item = first
    proxy._idx_names = {1: "甲", 2: "乙", 9: "原生账号"}
    proxy._push_user_book = {}
    proxy._app_name_book = {"mail": "邮件"}
    return proxy


def _run_close(proxy):
    async def run():
        await asyncio.gather(proxy._close_log_details(), proxy._close_log_details())
        await proxy._close_log_details()

    asyncio.run(run())


def test_late_mapping_routes_known_accounts_and_keeps_native_fallback(tmp_path):
    first = user("甲", "逐条")
    proxy = _proxy_for_log(first)
    path = tmp_path / "log.txt"
    path.write_text("", encoding="utf-8")
    proxy._prepare_log_details(path, mode="逐条", enabled=True, rotated_name=None)
    proxy._push_user_book = {"甲": first}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            "开始加载实例配置 1\n指令[ 邮件 ] 执行成功\n"
            "开始加载实例配置 9\n指令[ 邮件 ] 执行成功\n"
        )

    _run_close(proxy)
    assert len(first.push_log) == 2
    assert any("原生账号" in entry[1] for entry in first.push_log)


def test_trigger_account_off_keeps_other_enabled_account_details(tmp_path):
    first, second = user("甲", "关闭"), user("乙", "逐条")
    proxy = _proxy_for_log(first)
    proxy._push_user_book = {"甲": first, "乙": second}
    path = tmp_path / "log.txt"
    path.write_text("", encoding="utf-8")
    proxy._prepare_log_details(
        path,
        mode="关闭",
        enabled=True,
        rotated_name=None,
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            "开始加载实例配置 1\n指令[ 邮件 ] 执行成功\n"
            "开始加载实例配置 2\n指令[ 邮件 ] 执行成功\n"
        )

    asyncio.run(proxy._close_log_details())
    assert first.push_log == []
    assert [entry[1] for entry in second.push_log] == ["✅ 成功: 邮件"]


def test_single_account_unprefixed_node_keeps_trigger_fallback(tmp_path):
    first, mapped = user("触发用户", "逐条"), user("原生账号", "汇总")
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.user_state = lambda user: user
    proxy.callbacks = SimpleNamespace()
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
