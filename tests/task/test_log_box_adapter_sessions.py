"""调用方迁移后保留原有日志节点、开关与重试归属。"""

import asyncio
from types import SimpleNamespace


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
