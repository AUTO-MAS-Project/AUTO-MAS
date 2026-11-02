"""调用方迁移后保留原有日志节点、开关与重试归属。"""

import asyncio
import importlib
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("mode", ["逐条", "汇总", "关闭"])
@pytest.mark.parametrize("adapter", ["Okww", "BAAH", "MaaEnd"])
def test_adapter_keeps_frozen_node_outputs(tmp_path, monkeypatch, mode, adapter):
    module = importlib.import_module(f"app.task.{adapter}.AutoProxy")
    proxy = module.AutoProxyTask.__new__(module.AutoProxyTask)
    user = SimpleNamespace(push_log=[], push_log_mode=mode)
    proxy.cur_user_item = user
    if adapter == "Okww":
        proxy.script_root_path = tmp_path
        native = tmp_path / module._push_log.OKWW_REL_I18N_PO
        native.parent.mkdir(parents=True)
        native.write_text('msgid "Mail"\nmsgstr "领取邮件"\n', encoding="utf-8")
        supplement = tmp_path / "extra.po"
        supplement.write_text("", encoding="utf-8")
        monkeypatch.setattr(module._push_log, "_okww_supplement_po", lambda: supplement)
        text = "Mail\n先约电台\n切换账号失败\n乐园任务完成\n"
        expected = [
            "✅ 成功: 邮件",
            "✅ 成功: 先约电台",
            "❌ 失败: 切换账号",
            "✅ 成功: 每周乐园",
        ]
    elif adapter == "BAAH":
        text = "执行任务InCafe\n任务InCafe执行结束\n任务Daily执行前条件不成立或超时\n执行任务Mail\n运行出错: Mail超时\n"
        expected = ["✅ 成功: InCafe", "⏭ 跳过: Daily", "❌ 失败: Mail"]
    else:
        text = "[2026-10-29 07:02:00] 任务开始: 邮件\n[2026-10-29 07:03:00] 任务完成: 邮件\n[2026-10-29 07:04:00] 任务开始: 每日任务\n"
        expected = ["✅ 成功: 邮件", "❌ 失败: 每日任务"]
    path = tmp_path / "run.log"
    if adapter == "MaaEnd":
        proxy.push_log_enabled = mode != "关闭"
        path.write_text(text, encoding="utf-8")
        asyncio.run(proxy._append_stage_log_details([path]))
    else:
        path.write_text("历史内容\n", encoding="utf-8")
        proxy._prepare_log_details(
            path, mode=mode, enabled=mode != "关闭", rotated_name=None
        )
        with path.open("a", encoding="utf-8") as stream:
            stream.write(text)
        asyncio.run(proxy._close_log_details())
    assert [entry[1] for entry in user.push_log] == (expected if mode != "关闭" else [])


def test_baah_retry_keeps_only_latest_run_and_closes_once(tmp_path):
    from app.task.BAAH.AutoProxy import AutoProxyTask

    proxy = AutoProxyTask.__new__(AutoProxyTask)
    user = SimpleNamespace(push_log=[], push_log_mode="汇总")
    proxy.cur_user_item = user
    proxy.push_log_enabled = True

    async def run():
        for task in ("InCafe", "Daily"):
            path = tmp_path / f"{task}.log"
            path.write_text("启动信息\n", encoding="utf-8")
            proxy.script_log_path = path
            proxy._start_log_collect()
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"执行任务{task}\n任务{task}执行结束\n")
            await proxy._close_log_collect()
            await proxy._close_log_collect()

    asyncio.run(run())
    assert len(user.push_log) == 1
    assert user.push_log[0][1] == "✅ 成功: Daily"
