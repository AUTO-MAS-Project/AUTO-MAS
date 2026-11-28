"""收尾回读只交付真实胜出的具名规则，不从通知正文反推原因。"""

import asyncio
import threading
import uuid

import pytest

from app.models.config.script import (
    OkNteConfig,
    OkNteUserConfig,
)
from app.task.OkNte.AutoProxy import AutoProxyTask as OkNte
from app.task.run_flow import observe_run
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
async def test_report_delivers_only_named_source_matches_once(tmp_path):
    uid = uuid.uuid4()
    _root, script, user = await create_runtime_tree(user_id=str(uid))
    config, account = OkNteConfig(), OkNteUserConfig()
    lines = "无法找到活跃度奖励领取框\nDailyRoutineTask:任务失败: 日常领取\n"
    key, node = "oknte.no_claim_reward", "⏭ 跳过: 日常领取（当日已领取）"
    proxy = OkNte(
        script,
        await activate_config(config),
        {uid: await activate_config(account)},
        None,
    )
    path = tmp_path / "current.log"
    path.touch()
    proxy._prepare_log_details(path, mode="逐条", enabled=True, rotated_name=None)
    path.write_text(lines, encoding="utf-8")

    seen = []
    with observe_run(
        lambda owner, p: seen.append(
            (owner, p.stage, p.state, p.key, threading.get_ident())
        )
    ):
        await asyncio.gather(proxy._close_log_details(), proxy._close_log_details())
    assert seen == [(proxy, "special", "matched", key, threading.get_ident())]
    assert node in [text for _, text, _ in proxy.user_state(user).push_log]
