#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

from app.task.BetterGI.AutoProxy import _one_dragon_sequence_done


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