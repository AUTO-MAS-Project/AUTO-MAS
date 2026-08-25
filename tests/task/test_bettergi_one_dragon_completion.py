#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

from app.task.BetterGI.AutoProxy import (
    _is_switch_script_updated,
    _latest_repo_progress,
    _one_dragon_sequence_done,
    _party_config_error,
)


def _progress(x: int, n: int) -> str:
    """构造 BetterGI 的「一条龙任务执行: X/N」进度行。"""
    return f"一条龙任务执行: {x}/{n}"


def test_mid_run_task_end_is_not_complete(tmp_path) -> None:
    """任务边界(非最后一个)的「任务结束」不得判为整条完成。

    这是崩溃根因：4 任务的一条龙在任务 1 完成后即输出「任务结束」，旧逻辑会把整条
    一条龙误判成功而提前强杀 BetterGI（曾把一龙狗砍在任务 2 的地图模板加载处）。
    """
    log = "".join(
        [_progress(1, 4), "\n→ 任务结束", _progress(2, 4), "\n提瓦特大陆地图模板加载中"]
    )
    assert _one_dragon_sequence_done(log) is False


def test_last_progress_line_still_mid_run(tmp_path) -> None:
    """进度停在 1/4、末尾恰好是任务 1 的「任务结束」——仍不判完成。"""
    log = "".join([_progress(1, 4), "\n→ 任务结束"])
    assert _one_dragon_sequence_done(log) is False


def test_full_sequence_complete(tmp_path) -> None:
    """最后一个任务的「任务结束」（进度 X/N 已到 X==N）才判整条完成。"""
    log = "".join(
        [
            _progress(1, 4),
            "\n→ 任务结束",
            _progress(2, 4),
            "\n→ 任务结束",
            _progress(3, 4),
            "\n→ 任务结束",
            _progress(4, 4),
            "\n→ 任务结束",
        ]
    )
    assert _one_dragon_sequence_done(log) is True


def test_single_task_one_dragon(tmp_path) -> None:
    """单任务一条龙（1/1 + 任务结束）应判完成。"""
    log = "".join([_progress(1, 1), "\n→ 任务结束"])
    assert _one_dragon_sequence_done(log) is True


def test_legacy_no_progress_line_fallback(tmp_path) -> None:
    """旧版 BGI 无进度行时，退化为「任务结束」单判（兼容单任务一条龙）。"""
    log = "任意日志\n→ 任务结束"
    assert _one_dragon_sequence_done(log) is True


def _progress_msg(*lines: str) -> str:
    """拼一段含 Serilog 头行 + 消息行的仓库进展日志。"""
    return "".join(f"[08:00:0{i}] 00:00:00.000\n{l.strip()}\n" for i, l in enumerate(lines))


def test_repo_progress_reports_download(tmp_path) -> None:
    """首次克隆/冷启动阶段应转述「正在下载」。"""
    log = _progress_msg("浅克隆仓库: https://cnb.cool/bettergi/bettergi-scripts-list")
    assert "正在从脚本仓库下载脚本" in _latest_repo_progress(log)


def test_repo_progress_reports_up_to_date(tmp_path) -> None:
    """仓库已是最新时给出明确文案。"""
    log = _progress_msg("本地仓库已是最新")
    assert _latest_repo_progress(log) == "脚本仓库已是最新，无需下载"


def test_repo_progress_takes_latest_line(tmp_path) -> None:
    """多段进展累计时取最近一条（逆序匹配）。"""
    log = _progress_msg(
        "浅克隆仓库: x",
        "自动更新订阅脚本完成: 成功 31 个, 失败 0 个",
    )
    assert _latest_repo_progress(log).startswith("脚本仓库更新完成")
    assert "成功 31 个" in _latest_repo_progress(log)


def test_repo_progress_ignores_head_lines(tmp_path) -> None:
    """无进展（仅时间戳头行）返回 None。"""
    assert _latest_repo_progress("[08:00:00] INFO") is None


def test_repo_progress_skips_bracketed_lines(tmp_path) -> None:
    """带方括号前缀的行不算进展消息。"""
    log = _progress_msg("[08:00:00][Info] 浅克隆仓库: x")
    assert _latest_repo_progress(log) is None


def test_is_switch_script_updated(tmp_path) -> None:
    """检出切号脚本后判为已更新。"""
    assert _is_switch_script_updated('更新脚本成功: "js/SwitchAccountMultipleMode"') is True
    assert _is_switch_script_updated("浅克隆仓库: x") is False


def test_party_config_error_scan_not_found(tmp_path) -> None:
    """OCR 扫描找不到队伍（未找到队伍）→ 报出队伍名。"""
    log = '\n尝试切换至队伍: "锄地队"\n未找到队伍: "锄地队"，返回主界面\n'
    assert _party_config_error(log) == "锄地队"


def test_party_config_error_exception(tmp_path) -> None:
    """SwitchPartyTask 取不到匹配项抛异常（自动地脉花等 [ERR]）→ 报出队伍名。"""
    log = (
        '\n尝试切换至队伍: "锄地队"\n'
        "自动地脉花执行失败\nInvalidOperationException: Sequence contains no elements\n"
    )
    assert _party_config_error(log) == "锄地队"


def test_party_config_error_no_switch(tmp_path) -> None:
    """无切队尝试时不算配置错误。"""
    assert _party_config_error("自动地脉花执行失败: Sequence contains no elements") is None


def test_party_config_error_false_positive_hint(tmp_path) -> None:
    """仅有提示短语但没有切队尝试行时不算配置错误。"""
    assert _party_config_error("Sequence contains no elements 但无切队") is None