"""日志专项迁移对照：保留原有解析、归并和报告的可观察结果。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.log_box import LogCollect, log_box
from app.log_box.report import build_user_result_text
from app.task.BAAH.tools.push_log import BAAH_LOG_SPEC, BAAH_PUSH_RULES, baah_resolve
from app.task.MaaEnd.push_log import MAAEND_LOG_SPEC, MAAEND_PUSH_RULES, maaend_resolve
from app.task.Okww.push_log import OKWW_PUSH_RULES, make_okww_log_spec, okww_resolve
from app.utils.common.i18n import PoTranslator


@pytest.mark.parametrize("mode", ["逐条", "汇总", "关闭"])
@pytest.mark.parametrize("adapter", ["okww", "baah", "maaend"])
def test_adapter_report_matches_legacy(tmp_path, monkeypatch, mode, adapter):
    translator = None
    if adapter == "okww":
        import app.task.Okww.push_log as okww

        native = tmp_path / okww.OKWW_REL_I18N_PO
        native.parent.mkdir(parents=True)
        native.write_text('msgid "Mail"\nmsgstr "领取邮件"\n', encoding="utf-8")
        supplement = tmp_path / "extra.po"
        supplement.write_text('msgid "Mail"\nmsgstr "领取邮件"\n', encoding="utf-8")
        monkeypatch.setattr(okww, "_okww_supplement_po", lambda: supplement)
        translator = PoTranslator().load([native]).load_supplement([supplement])
        spec, rules, resolve = (
            make_okww_log_spec(tmp_path),
            OKWW_PUSH_RULES,
            okww_resolve,
        )
        stages = ["Mail\n先约电台\n切换账号失败\n乐园任务完成\n"]
    elif adapter == "baah":
        spec, rules, resolve = BAAH_LOG_SPEC, BAAH_PUSH_RULES, baah_resolve
        stages = [
            "执行任务InCafe\n任务InCafe执行结束\n"
            "任务Daily执行前条件不成立或超时\n执行任务Mail\n运行出错: Mail超时\n"
        ]
    else:
        spec, rules, resolve = MAAEND_LOG_SPEC, MAAEND_PUSH_RULES, maaend_resolve
        stages = [
            "[2026-10-29 07:02:00] 任务开始: 邮件\n"
            "[2026-10-29 07:03:00] 任务完成: 邮件\n",
            "[2026-10-29 07:04:00] 任务开始: 每日任务\n",
        ]
    paths = []
    for index, text in enumerate(stages):
        path = tmp_path / f"stage-{index}.log"
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    previous, current = [
        SimpleNamespace(
            name="用户",
            result="代理完成",
            push_log=[],
            push_log_mode=mode,
            status="完成",
        )
        for _ in range(2)
    ]
    enabled = mode != "关闭"
    legacy = None
    if enabled:
        legacy = LogCollect(
            paths,
            sink=lambda *entry: previous.push_log.append(entry),
            start_from_end=False,
        )
        legacy.open(translator.translate if translator is not None else None)
        for rule in rules:
            legacy.collect(*rule)
    session = log_box.get_user_session(
        spec, user=current, mode=mode, paths=paths, start_from_end=False
    )
    monkeypatch.setattr("app.log_box.pipeline.time.time", lambda: 1793228520.0)
    if legacy is not None:
        legacy.close(resolve)
    asyncio.run(session.close())
    assert current.push_log == previous.push_log
    if enabled:
        assert current.push_log
    assert build_user_result_text([current], True) == build_user_result_text(
        [previous], True
    )


def test_baah_retry_keeps_only_latest_run_and_closes_once(tmp_path):
    from app.task.BAAH.AutoProxy import AutoProxyTask

    user = SimpleNamespace(name="用户", push_log=[], push_log_mode="汇总")
    proxy = SimpleNamespace(cur_user_item=user, push_log_enabled=True, log_collect=None)

    async def scenario():
        for task in ("InCafe", "Daily"):
            path = tmp_path / f"{task}.log"
            path.write_text("启动信息\n", encoding="utf-8")
            proxy.script_log_path = path
            AutoProxyTask._start_log_collect(proxy)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"执行任务{task}\n任务{task}执行结束\n")
            await AutoProxyTask._close_log_collect(proxy)
            await AutoProxyTask._close_log_collect(proxy)
        return user.push_log

    entries = asyncio.run(scenario())
    assert len(entries) == 1
    assert entries[0][1] == "✅ 成功: Daily"
