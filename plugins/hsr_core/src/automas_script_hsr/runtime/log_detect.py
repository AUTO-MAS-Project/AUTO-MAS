#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import re
from typing import Callable


M7A_COMPLETION_MARKERS: tuple[str, ...] = ("停止运行",)

HSR_ECHO_OF_WAR_WEEKLY_REWARD_LIMIT = 3
# 审计 HSR-外部脚本日志语义审计.md §4.1/§4.2：源码未找到的字面量已直接移除；
# 保留的均为 M7A 源码（divergent_universe.py / currency_wars.py / daily.py）已确认存在。
HSR_EOW_INCOMPLETE_MARKERS: tuple[str, ...] = (
    "体力不足",
    "开拓力 < 30",
    "历战余响失败",
)
HSR_EOW_COMPLETE_MARKERS: tuple[str, ...] = (
    "体力计划已完成: 历战余响",
    "体力计划已完成：历战余响",
    "历战余响尚未刷新",
)
HSR_EOW_REWARD_COUNT_RE = re.compile(
    r"历战余响本周可领取奖励次数[:：]\s*(\d+)\s*/\s*3"
)
HSR_EOW_REMAINING_COUNT_RE = re.compile(
    r"本周[「\"]?历战余响[」\"；:：]?\s*剩余次数[:：]\s*(\d+)\s*/\s*3"
)
HSR_EOW_M7A_START_RE = re.compile(r"开始刷历战余响.*?每轮包含\s*(\d+)\s*次")
HSR_EOW_SRA_PLAN_RE = re.compile(r"任务\s+历战余响.*?将执行\s*(\d+)\s*次")

HSR_ENGLISH_FAILURE_RE = re.compile(
    r"(Traceback \(most recent call last\):|Failed to execute script|"
    r"Fatal error|SRAError\(|Exception:)"
)
HSR_CHINESE_FAILURE_MARKERS: tuple[str, ...] = (
    # 审计 HSR-外部脚本日志语义审计.md §4.2：原通用项（任务失败 / 执行失败 /
    # 运行失败 / 当前任务失败 / 启动任务失败 / 发生错误 / 出现错误 /
    # 发生异常 / 执行异常 / 运行异常）过宽，会与 SRA SRAError + M7A retry
    # 路径的"假失败"误判。仅保留与最终失败强相关的具体短语。
    "停止进一步执行",
    "主循环超时",
    "强制退出",
    "未识别到战斗按钮",
    "MemoryOfChaos 主循环失败",
    # ---- SRA 货币战争 final_failure（参考 HSR-外部脚本日志语义审计.md 2.5）----
    "[页面定位] 检测超时",            # CurrencyWars.py:159
    "等待挑战结束超时",               # CurrencyWars.py:708
    "货币战争开拓者名称为空",         # CosmicStrifeTask.py:34
    "旷宇纷争-货币战争任务失败",      # CosmicStrifeTask.py:63
    "旷宇纷争-货币战争刷开局任务失败",  # CosmicStrifeTask.py:50
)
HSR_BENIGN_FAILURE_MARKERS: tuple[str, ...] = (
    "未找到匹配文字",
    "未找到目标文字",
    "未匹配到目标文字",
    "目标图片：",
    "ImageNotFound:",
    "Error taking screenshot:",
    "Could not locate the image",
    "EOF when reading a line",
    "网络错误:",
    "HTTPSConnectionPool(",
    "Max retries exceeded",
    "SSLCertVerificationError",
    "certificate verify failed",
    "寻找图片出错：OpenCV",
    "cv::matchTemplate",
    "Assertion failed",
)
HSR_EOF_FAILURE_CONTEXT_MARKERS: tuple[str, ...] = (
    "EOF when reading a line",
    "pause_on_success",
    "pause_on_error",
    "utils\\console.py",
    "utils/console.py",
)
HSR_EOF_FAILURE_LINE_MARKERS: tuple[str, ...] = (
    "Traceback",
    "During handling of the above exception",
    "Failed to execute script",
    "unhandled exception",
    "utils\\console.py",
    "utils/console.py",
    "pause_on_success",
    "pause_on_error",
)
HSR_SCREENSHOT_WINDOW_UNAVAILABLE_MARKERS: tuple[str, ...] = (
    "Error taking screenshot:",
    "无法获取窗口客户区域",
    "窗口可能被最小化",
)


# ===== 模块级 final marker（审计 HSR-外部脚本日志语义审计.md §4.3）=====
HSR_DAILY_FINAL_SUCCESS_M7A: tuple[str, ...] = (
    "每日实训尚未刷新",                # daily.py:40/69
    "每日实训未开启",                  # daily.py:42/71
    "清体力未开启，跳过历战余响和清体力",  # daily.py:63
)
HSR_DAILY_FINAL_SUCCESS_SRA: tuple[str, ...] = (
    "任务完成：领取每日实训奖励",      # ReceiveRewardsTask.py:230
    "任务完成：领取邮件",              # ReceiveRewardsTask.py:146
    "任务完成：领取派遣奖励",          # ReceiveRewardsTask.py:198
    "任务完成：巡星之礼",              # ReceiveRewardsTask.py:173
    "任务完成：签证奖励",              # ReceiveRewardsTask.py:100
    "任务完成：领取兑换码",            # ReceiveRewardsTask.py:132
    "完成任务：领取无名勋礼奖励",      # ReceiveRewardsTask.py:255
    "没有可领取的奖励",                # ReceiveRewardsTask.py:94/97/99
)

HSR_DIVERGENT_FINAL_SUCCESS_M7A: tuple[str, ...] = (
    "已达到最高积分 12000，记录时间",   # divergent_universe.py:120
    "已达到最高积分 14000，记录时间",
    "已达到最高积分 18000，记录时间",
    "检测到积分奖励已由邮件发放，跳过积分检查",  # divergent_universe.py:104
    "「差分宇宙」积分奖励尚未刷新",     # daily.py:149
)
# SRA 差分宇宙和货币战争共用同一个 CosmicStrifeTask，都会打出
# 「旷宇纷争任务全部完成」。两个集合中同时存在该 marker 是预期行为，
# 歧义由 detect_weekly_completion 的 module_key 消除：
# sra_overrides（task_mapping.py）确保同一轮只启用其中一个，
# 调用方传入的 module_key 决定查哪组 marker。
HSR_DIVERGENT_FINAL_SUCCESS_SRA: tuple[str, ...] = (
    "Mission accomplished",            # DivergentUniverse.py:39
    "当前积分奖励: 18000/18000",       # DivergentUniverse.py:216
    "旷宇纷争任务全部完成",            # CosmicStrifeTask.py:25  ⚠️需配合 sra_overrides
)

HSR_CURRENCY_WARS_FINAL_SUCCESS_M7A: tuple[str, ...] = (
    "已达到最高积分 18000，记录时间",   # currency_wars.py:266
    "「货币战争」积分奖励尚未刷新",     # daily.py:131
)
HSR_CURRENCY_WARS_FINAL_SUCCESS_SRA: tuple[str, ...] = (
    "旷宇纷争任务全部完成",            # CosmicStrifeTask.py:65  ⚠️需配合 sra_overrides
    "达到终止状态：主界面",            # CurrencyWars.py:790
    "达到终止状态：游戏结束",          # CurrencyWars.py:790
)

HSR_ABYSS_FINAL_SUCCESS_M7A: tuple[str, ...] = (
    "混沌回忆未刷新",                  # basechallenge.py:64
    "虚构叙事未刷新",
    "末日幻影未刷新",
    "星数：3/3",                        # basechallenge.py:61
)
HSR_ABYSS_FINAL_FAILURE_M7A: tuple[str, ...] = (
    "战斗超时",                        # memoryofchaos.py:208 / purefiction.py:209 / apocalyptic.py:301
    "领取星琼失败",                    # memoryofchaos.py:230 / purefiction.py:231 / apocalyptic.py:331
    "前往挑战失败",                    # apocalyptic.py:143
    "选择buff失败",                    # apocalyptic.py:184
    "没有找到角色",                    # apocalyptic.py:215
)


def emit_process_output(
    log_callback: Callable[[str], None] | None,
    title: str,
    text: str,
) -> None:
    """把子进程输出转发给调度台日志回调。"""

    if log_callback is None or not text:
        return
    for line in text.splitlines():
        line = line.strip()
        if line:
            log_callback(f"{title}: {line}")


def can_read_stream_live(stream) -> bool:
    """判断 stdout/stderr 是否是可实时读取的异步流。"""

    if stream is None:
        return False
    return callable(getattr(stream, "readline", None))


def has_failure_output(*texts: str) -> bool:
    """判断外部脚本输出中是否包含明确的失败语义。"""

    full_text = "\n".join(str(text) for text in texts if text)
    has_noninteractive_eof = all(
        marker in full_text for marker in HSR_EOF_FAILURE_CONTEXT_MARKERS[:2]
    ) or (
        "EOF when reading a line" in full_text
        and any(marker in full_text for marker in HSR_EOF_FAILURE_CONTEXT_MARKERS[2:])
    )

    for text in texts:
        if not text:
            continue
        for line in str(text).splitlines():
            line = line.strip()
            if not line:
                continue
            if any(marker in line for marker in HSR_BENIGN_FAILURE_MARKERS):
                continue
            if (
                has_noninteractive_eof
                and any(marker in line for marker in HSR_EOF_FAILURE_LINE_MARKERS)
            ):
                continue
            if HSR_ENGLISH_FAILURE_RE.search(line):
                return True
            if any(marker in line for marker in HSR_CHINESE_FAILURE_MARKERS):
                return True
    return False


def has_screenshot_window_unavailable_output(text: str) -> bool:
    """判断外部脚本是否正在因游戏窗口不可截图而等待。"""

    line = str(text or "")
    return all(marker in line for marker in HSR_SCREENSHOT_WINDOW_UNAVAILABLE_MARKERS)


def result_text(result: object) -> str:
    """提取外部脚本 stdout/stderr 合并文本。"""

    if result is None:
        return ""
    output = str(getattr(result, "output", "") or "")
    error = str(getattr(result, "error", "") or "")
    return "\n".join(part for part in (output, error) if part)


def detect_echo_of_war_completion(result: object, script: str) -> tuple[bool, str]:
    """根据 M7A/SRA 输出判断本周历战余响是否已完成。"""

    text = result_text(result)
    if not text:
        return False, "外部脚本未返回可判断的历战余响日志"

    remaining_counts = [
        int(match.group(1)) for match in HSR_EOW_REMAINING_COUNT_RE.finditer(text)
    ]
    if remaining_counts and remaining_counts[-1] <= 0:
        return True, "外部脚本日志显示历战余响本周剩余次数为 0"

    reward_counts = [
        int(match.group(1)) for match in HSR_EOW_REWARD_COUNT_RE.finditer(text)
    ]
    if reward_counts:
        remaining = reward_counts[-1]
        if remaining <= 0:
            return True, "外部脚本日志显示历战余响本周已无可领取次数"

        m7a_attempts = _parse_max_int(HSR_EOW_M7A_START_RE, text)
        if (
            str(script).upper() == "M7A"
            and m7a_attempts is not None
            and m7a_attempts >= remaining
        ):
            # 审计 HSR-外部脚本日志语义审计.md §3.4：M7A 源码中未找到
            # 「副本任务完成」字面量，移除该前置条件；保留 attempts>=remaining
            # 作为 M7A 计划数匹配。
            return True, (
                f"M7A 日志显示本次执行 {m7a_attempts} 次，"
                f"已覆盖剩余 {remaining} 次历战余响"
            )
        return False, (
            f"外部脚本日志显示历战余响仍需 {remaining} 次，"
            "本次未确认全部完成"
        )

    if any(marker in text for marker in HSR_EOW_COMPLETE_MARKERS):
        return True, "外部脚本日志显示历战余响体力计划已完成"

    if any(marker in text for marker in HSR_EOW_INCOMPLETE_MARKERS):
        return False, "外部脚本日志显示历战余响未完成或体力不足"

    sra_attempts = _parse_max_int(HSR_EOW_SRA_PLAN_RE, text)
    if (
        str(script).upper() == "SRA"
        and sra_attempts is not None
        and sra_attempts >= HSR_ECHO_OF_WAR_WEEKLY_REWARD_LIMIT
        and "任务完成：历战余响" in text
    ):
        return True, f"SRA 日志显示历战余响已执行 {sra_attempts} 次"

    return False, "未从外部脚本日志确认历战余响已完成"


def _parse_max_int(pattern: re.Pattern[str], text: str) -> int | None:
    values = []
    for match in pattern.finditer(text):
        try:
            values.append(int(match.group(1)))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def detect_weekly_completion(
    result: object,
    script: str,
    module_key: str,
) -> tuple[bool, str]:
    """根据 M7A/SRA 输出判断周常（差分宇宙 / 货币战争）是否已完成。

    仅用于 on_success 回调前置判定：调用方在 ``result.success == True`` 时
    才会触发本函数，命中 final marker 才写完成态，**不会**触发重试。
    SRA 的 ``旷宇纷争任务全部完成`` 歧义由 ``module_key``（sra_overrides
    唯一决定）消除。
    """

    text = result_text(result)
    if not text:
        return False, "外部脚本未返回可判断的周常日志"

    upper_script = str(script).upper()
    if module_key == "DivergentUniverse":
        candidate_sets: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("M7A", HSR_DIVERGENT_FINAL_SUCCESS_M7A),
            ("SRA", HSR_DIVERGENT_FINAL_SUCCESS_SRA),
        )
    elif module_key == "CurrencyWars":
        candidate_sets = (
            ("M7A", HSR_CURRENCY_WARS_FINAL_SUCCESS_M7A),
            ("SRA", HSR_CURRENCY_WARS_FINAL_SUCCESS_SRA),
        )
    else:
        return False, f"模块 {module_key} 不是周常任务，不走周常完成态判定"

    matched = next(
        (
            (label, marker)
            for label, markers in candidate_sets
            for marker in markers
            if marker in text
        ),
        None,
    )
    if matched is None:
        return False, "未从外部脚本日志确认周常完成"

    label, marker = matched
    if upper_script != label:
        return False, (
            f"日志中出现 {label} 模块 final marker「{marker}」，"
            f"但本次调用方为 {upper_script}，拒绝跨脚本写完成态"
        )
    return True, f"{label} 日志命中周常完成 marker：{marker}"


def detect_daily_completion(
    result: object,
    script: str,
) -> tuple[bool, str]:
    """根据 M7A/SRA 输出判断日常领取模块是否已完成。

    当前仅定义检测函数骨架，**不**接入 ReceiveRewards on_success；
    后续如需接入，由 on_success 决定是否走本判定。
    """

    text = result_text(result)
    if not text:
        return False, "外部脚本未返回可判断的日常日志"

    upper_script = str(script).upper()
    candidate_sets: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("M7A", HSR_DAILY_FINAL_SUCCESS_M7A),
        ("SRA", HSR_DAILY_FINAL_SUCCESS_SRA),
    )

    matched = next(
        (
            (label, marker)
            for label, markers in candidate_sets
            for marker in markers
            if marker in text
        ),
        None,
    )
    if matched is None:
        return False, "未从外部脚本日志确认日常领取完成"

    label, marker = matched
    if upper_script != label:
        return False, (
            f"日志中出现 {label} 模块 final marker「{marker}」，"
            f"但本次调用方为 {upper_script}，拒绝跨脚本写完成态"
        )
    return True, f"{label} 日志命中日常完成 marker：{marker}"


def detect_abyss_completion(
    result: object,
    abyss_type: str | None = None,
) -> tuple[bool, str]:
    """根据 M7A 输出判断三深渊本次执行是否完成。

    ``abyss_type`` 形如 ``"ForgottenHall"`` / ``"PureFiction"`` / ``"Apocalyptic"``；
    不传时按三深渊整体 marker 判定（混沌回忆/虚构叙事/末日幻影任一命中即视为完成）。
    当前仅定义骨架，**不**接入三深渊 on_success。
    """

    text = result_text(result)
    if not text:
        return False, "外部脚本未返回可判断的三深渊日志"

    if any(marker in text for marker in HSR_ABYSS_FINAL_FAILURE_M7A):
        return False, "三深渊日志命中 final_failure marker，本次未完成"

    if not any(marker in text for marker in HSR_ABYSS_FINAL_SUCCESS_M7A):
        return False, "三深渊日志未命中满星/未刷新 final_success marker"

    return True, "三深渊日志命中 final_success marker（满星或未刷新）"
