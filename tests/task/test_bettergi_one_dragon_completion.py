#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

from app.task.BetterGI.AutoProxy import (
    _BGI_BUILTIN_FATAL,
    _BGI_ERR_STALL_MINUTES,
    _is_switch_script_updated,
    _latest_repo_progress,
    _one_dragon_sequence_done,
    _party_config_error,
)


def _progress(x: int, n: int) -> str:
    """构造 BetterGI 的「一条龙任务执行: X/N」进度行。"""
    return f"一条龙任务执行: {x}/{n}"


def test_mid_run_task_end_is_not_complete(tmp_path) -> None:
    """任务边界(非最后)的「任务结束」不得判为整条完成。

    这是崩溃根因之一：4 任务的一条龙在任务 1 完成后即输出「任务结束」，旧逻辑会把整条
    误判成功而提前强杀 BetterGI（曾把一龙狗砍在任务 2 的地图模板加载处）。现以权威收尾
    行「一条龙和配置组任务结束」为准，无该行即不算完成。
    """
    log = "".join(
        [_progress(1, 4), "\n→ 任务结束", _progress(2, 4), "\n提瓦特大陆地图模板加载中"]
    )
    assert _one_dragon_sequence_done(log) is False


def test_last_progress_line_still_mid_run(tmp_path) -> None:
    """进度停在 1/4、末尾是任务 1 的「任务结束」——无权威收尾行，不判完成。"""
    log = "".join([_progress(1, 4), "\n→ 任务结束"])
    assert _one_dragon_sequence_done(log) is False


def test_config_group_subtask_end_is_not_complete(tmp_path) -> None:
    """一条龙里配置组子任务（切换账号）的「任务结束」不得判为整条完成。

    这是本次回归根因：真正的一条龙任务还没开始，切换账号配置组结束即输出
    「配置组任务执行: 1/2」+「→ 任务结束」，旧逻辑按无进度行兜底判成功，
    在约 48 秒就把 BetterGI 强杀在真正的一条龙运行前。
    """
    log = "".join(
        [
            "启用配置组任务的数量: 2",
            "\n配置组任务执行: 1/2",
            "\n配置组 切换账号DHXYHO 加载完成，共1个脚本，开始执行",
            '\n→ "任务启动！"',
            "\n→ 开始执行JS脚本: 切换账号多模式",
            "\n→ 脚本执行结束",
            '\n→ "任务结束"',
            "\n配置组 切换账号DHXYHO 执行结束",
        ]
    )
    assert _one_dragon_sequence_done(log) is False


def test_generic_task_end_without_marker_is_not_complete(tmp_path) -> None:
    """仅泛化的「任务结束」而无权威收尾行，不判完成（兼容配置组/旧进度场景）。"""
    assert _one_dragon_sequence_done("任意日志\n→ 任务结束") is False


def test_full_sequence_complete(tmp_path) -> None:
    """全部任务跑完后打印权威收尾行「一条龙和配置组任务结束」才判整条完成。"""
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
            "\n一条龙和配置组任务结束",
        ]
    )
    assert _one_dragon_sequence_done(log) is True


def test_single_task_one_dragon(tmp_path) -> None:
    """单任务一条龙跑完 + 权威收尾行，判完成。"""
    log = "".join([_progress(1, 1), "\n→ 任务结束", "\n一条龙和配置组任务结束"])
    assert _one_dragon_sequence_done(log) is True


def test_sequence_done_marker_present(tmp_path) -> None:
    """日志命中唯一权威收尾行即判完成（即使其后还有杂散任务结束）。"""
    log = "\n一条龙和配置组任务结束\n→ 任务结束"
    assert _one_dragon_sequence_done(log) is True


def test_complete_with_stray_err_is_done(tmp_path) -> None:
    """日志里既有 [ERR]（可恢复的『任务级』异常）又走到权威收尾行 → 判整条完成。

    这是修复核心：BGI 的 TaskRunner 在某条子任务抛异常时会打印 [ERR] 但吞掉异常
    （不 rethrow），一条龙继续跑下一条最终仍正常收尾。若按 [ERR] 判失败会把本可跑完
    的一龙中途强杀。只要能命中收尾行，历史 [ERR] 一律视为可恢复。
    """
    log = "[ERR] Sequence contains no elements\n一条龙和配置组任务结束"
    assert _one_dragon_sequence_done(log) is True


def test_complete_with_multiple_errs_is_done(tmp_path) -> None:
    """多条任务都跳过（含 [ERR]）但仍走完收尾行 → 判完成。"""
    log = "\n".join(
        [
            "[ERR] 任务A异常",
            _progress(1, 3),
            "[ERR] 任务B异常",
            _progress(2, 3),
            _progress(3, 3),
            "一条龙和配置组任务结束",
        ]
    )
    assert _one_dragon_sequence_done(log) is True


def test_fatal_table_excludes_recoverable_err(tmp_path) -> None:
    """[ERR]/「任务执行异常」是任务级可恢复异常，不得进进程级致命表。"""
    needles = [n for n, _ in _BGI_BUILTIN_FATAL]
    assert "[ERR]" not in needles
    assert "任务执行异常" not in needles
    assert "[FTL]" in needles  # BGI 真正的进程级致命仍在表内


def test_err_stall_window(tmp_path) -> None:
    """[ERR] 后卡死兜底的静默阈值固定为 5 分钟（见 check_log 的 _BGI_ERR_STALL_MINUTES）。"""
    assert _BGI_ERR_STALL_MINUTES == 5


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