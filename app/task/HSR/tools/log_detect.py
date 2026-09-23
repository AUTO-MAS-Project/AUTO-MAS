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
HSR_EOW_REWARD_COUNT_RE = re.compile(r"历战余响本周可领取奖励次数[:：]\s*(\d+)\s*/\s*3")
# 现行 M7A / SRA 都不再打这句（M7A 走上一条「可领取奖励次数」），留作旧版兼容。
HSR_EOW_REMAINING_COUNT_RE = re.compile(
    r"本周[「\"]?历战余响[」\"；:：]?\s*剩余次数[:：]\s*(\d+)\s*/\s*3"
)
HSR_EOW_M7A_START_RE = re.compile(r"开始刷历战余响.*?每轮包含\s*(\d+)\s*次")
# 「将执行 N 次」只在 SRA 体力自动分配路径打印，手动副本任务没有这行；
# SRA v2.21.0 起历战余响自动检测也改走手动副本固定 3 连战，这行不再出现。
HSR_EOW_SRA_PLAN_RE = re.compile(r"任务\s+历战余响.*?将执行\s*(\d+)\s*次")
HSR_EOW_SRA_DONE_MARKER = "任务完成：历战余响"
# battle() 每个任务以「执行任务：」开场；没有计划行时靠它圈定历战余响战斗块。
HSR_EOW_SRA_START_MARKER = "执行任务：历战余响"
# wait_battle_end 60 分钟没等到战斗结束会先打这行 ERROR 再返回 -1；
# battle_start 对 -1 与正常结束同路处理，仍会走到「任务完成」。
HSR_EOW_SRA_BATTLE_TIMEOUT_MARKER = "等待战斗结束超时"
# SRA 打不过或点不中关卡时也会打印「任务完成」，只有战斗失败会单独留痕；
# 排除同样含该子串的「退出战斗失败」，那只是收尾点击没成功。
HSR_EOW_SRA_BATTLE_FAILED_RE = re.compile(r"(?<!退出)战斗失败")

# SRA 界面语言为英文时的失败文案（SRACore/localization/resource_en-us.json）：
# task.taskFailed / task.noSuchTask / config.fileNotFound。SRA-cli 的退出码
# 恒为 0，这几条漏掉就会把失败判成成功。
HSR_ENGLISH_FAILURE_RE = re.compile(
    r"(Traceback \(most recent call last\):|Failed to execute script|"
    r"Fatal error|SRAError\(|Exception:|"
    r"failed\. Stopping further execution|No such task|"
    r"Could not find config file)"
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
    # ---- SRA 货币战争 final_failure（参考 HSR-外部脚本日志语义审计.md 2.5；
    # 行号按 SRA 2.21.0 tasks/ 源码）----
    "[页面定位] 检测超时",  # currency_wars/CurrencyWars.py:186
    "等待挑战结束超时",  # currency_wars/CurrencyWars.py:763
    "货币战争开拓者名称为空",  # CosmicStrifeTask.py:38
    "旷宇纷争-货币战争任务失败",  # CosmicStrifeTask.py:69
    "旷宇纷争-货币战争刷开局任务失败",  # CosmicStrifeTask.py:56
    # ---- M7A 切换游戏界面失败（对应日志「发生错误 无法切换到指定游戏界面」）----
    "无法切换到指定游戏界面",
    # ---- SRA 前置失败：任务名不存在 / 配置文件读不到，走不到「停止进一步执行」
    # （SRACore/thread/task_process.py、SRACore/util/data_persister.py）----
    "没有此任务",
    "找不到文件",
    # ---- M7A 首次运行闸门：打这行后 exit(0)（main.py 的 first_run）----
    "首次使用请先打开图形界面",
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
# M7A 收尾的「按任意键继续」写在 utils/console.py：走到 pause_on_success 说明
# 任务正文已经跑完，之后再崩只是收尾输出失败。非交互启动下它必崩——早期是
# stdin 被关掉的 EOFError，非中文系统区域下则是中文写不进 ANSI 代码页 stdout
# 的 UnicodeEncodeError——判据因此锚在崩溃位置，而不是某一种异常类型。
HSR_CONSOLE_PAUSE_SUCCESS_MARKER = "pause_on_success"
HSR_NONINTERACTIVE_EOF_MARKER = "EOF when reading a line"
# pause_on_error 是正文失败后的兜底路径，它自己崩不能证明正文成功。
HSR_CONSOLE_PAUSE_ERROR_MARKERS: tuple[str, ...] = (
    "pause_on_error",
    "utils\\console.py",
    "utils/console.py",
)
HSR_EXIT_CRASH_LINE_MARKERS: tuple[str, ...] = (
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
# M7A 自己关掉游戏只有两条路（tasks/game/__init__.py 的启动重试循环）：等
# 6 分钟识不出任何界面，或者启动过程抛异常；两处都先打这行 ERROR 再
# stop_game()，随后 continue 自行重启游戏。「游戏终止：」是 stop_game 成功后
# 的 INFO，进程被 MAS 抢先杀掉时它多半来不及刷出，所以不能只认它。
HSR_M7A_SELF_GAME_STOP_MARKERS: tuple[str, ...] = (
    "获取当前界面超时",
    "尝试启动游戏时发生错误",
    "游戏终止：",
)
# M7A 冻结 exe 在非中文 ANSI 代码页（如 cp1252）下 stderr 走 backslashreplace，
# 中文全变成 \uXXXX；它自己改不了，只能在读取侧还原。
_BACKSLASH_U_RE = re.compile(
    r"\\u([dD][89abAB][0-9a-fA-F]{2})\\u([dD][c-fC-F][0-9a-fA-F]{2})"
    r"|\\u([0-9a-fA-F]{4})"
)
# 日志时间前缀，摘要里只留级别：M7A 用标准库 logging
# 「%(asctime)s | %(levelname)s | 」→「2026-09-12 02:14:35,242 | ERROR | 」；
# SRA 用 loguru「{time:HH:mm:ss} | {level:5} | 」→「02:14:35 | ERROR | 」。
_LOG_TIME_PREFIX_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2} )?\d{2}:\d{2}:\d{2}(?:[,.]\d{3})?\s*\|\s*"
)
_LOG_LEVEL_RE = re.compile(r"\|\s*(ERROR|CRITICAL)\s*\|")
HSR_FAILURE_SUMMARY_KEEP_MARKERS: tuple[str, ...] = (
    "错误截图已保存",
    "Traceback",
)


# ---- 云·星穹铁道（三月七 module/game/cloud.py 与 tasks/game/__init__.py 原文，
# 见 docs/测试证据/HSR-云星铁调研-20260922/cloud-m7a.md §3）----
# 不可重试：补跑只会再等一遍登录 / 再排一遍队 / 再撞一次时长为 0。三月七自己
# 会在一次运行里重试 3 遍，所以只在模块已判失败时才按这些词归类；「进入云游戏
# 失败」之后第二遍成功的，模块本身就是成功，不归类。
HSR_CLOUD_NON_RETRYABLE_MARKERS: tuple[str, ...] = (
    "等待云游戏登录超时",  # cloud.py:508
    "云游戏剩余时长为 0，停止运行",  # cloud.py:1172/1189
    "排队超时",  # cloud.py:647
    "进入云游戏失败",  # tasks/game/__init__.py:189、cloud.py:1185
    "检测到付费时长耗尽弹窗",  # cloud.py:681
    "云游戏付费时长已耗尽",  # cloud.py:689（SystemExit 消息，走 stderr）
    "启动或连接浏览器失败",  # tasks/game/__init__.py:186、cloud.py:1104
    "浏览器启动失败",  # cloud.py:338/352/354/355；也覆盖 MAS 的「云浏览器启动失败」
)
# 需人工：不判失败，转调度台提示与用户通知。有窗口模式下三月七先打「未登录」，
# 再打「请在浏览器中完成登录操作，超时时间：N 分钟」后在窗口里等人。
HSR_CLOUD_LOGIN_REQUIRED_MARKER = "请在浏览器中完成登录操作，超时时间"
HSR_CLOUD_NOT_LOGGED_IN_MESSAGE = "未登录"
HSR_CLOUD_LOGIN_TIMEOUT_RE = re.compile(
    r"请在浏览器中完成登录操作，超时时间：(\d+) 分钟"
)
# 已登录的正向信号：据此记 Cloud.LastLogin。
HSR_CLOUD_LOGIN_SUCCESS_MARKERS: tuple[str, ...] = (
    "检测到登录成功",  # cloud.py:1138
    "进入云游戏成功",  # cloud.py:1169/1179
)
HSR_CLOUD_REMAINING_RE = re.compile(
    r"云游戏剩余时长：(\d+) 分钟（付费：(\d+) 分钟，免费：(\d+) 分钟）"
)  # cloud.py:1174
HSR_CLOUD_REMAINING_WARN_MINUTES = 60
_M7A_LOG_MESSAGE_RE = re.compile(
    r"\|\s*(?:DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\|\s*(.*)$"
)


def _m7a_log_message(line: str) -> str:
    """去掉三月七日志行的「时间 | 级别 | 」前缀，只留消息正文。"""

    match = _M7A_LOG_MESSAGE_RE.search(line)
    return (match.group(1) if match else line).strip()


def find_cloud_non_retryable_marker(*texts: str) -> str | None:
    """返回输出里第一条云·星穹铁道不可重试失败词；没有则 None。"""

    for text in texts:
        if not text:
            continue
        for marker in HSR_CLOUD_NON_RETRYABLE_MARKERS:
            if marker in text:
                return marker
    return None


def detect_cloud_login_required(line: str) -> tuple[bool, int | None]:
    """这一行是否是三月七在等人登录；返回 (是否需人工, 超时分钟数或 None)。"""

    match = HSR_CLOUD_LOGIN_TIMEOUT_RE.search(line)
    if match:
        return True, int(match.group(1))
    if HSR_CLOUD_LOGIN_REQUIRED_MARKER in line:
        return True, None
    if _m7a_log_message(line).endswith(HSR_CLOUD_NOT_LOGGED_IN_MESSAGE):
        return True, None
    return False, None


def is_cloud_login_success(line: str) -> bool:
    """这一行是否说明当前云浏览器已处于登录态。"""

    return any(marker in line for marker in HSR_CLOUD_LOGIN_SUCCESS_MARKERS)


def parse_cloud_remaining(line: str) -> tuple[int, int, int] | None:
    """解析「云游戏剩余时长：N 分钟（付费：P 分钟，免费：F 分钟）」。"""

    match = HSR_CLOUD_REMAINING_RE.search(line)
    if match is None:
        return None
    total, paid, free = (int(value) for value in match.groups())
    return total, paid, free


def unescape_backslash_u(text: str) -> str:
    """把 backslashreplace 产生的 ``\\uXXXX`` 还原成原字符。

    只处理紧跟四位十六进制的形式，代理对合并成一个字符，落单的代理项换成
    U+FFFD 以免后续写 UTF-8 日志时炸掉；不含 ``\\u`` 的文本原样返回。
    """

    if "\\u" not in text:
        return text

    def _replace(match: re.Match[str]) -> str:
        high, low, single = match.groups()
        if single is None:
            code = 0x10000 + ((int(high, 16) - 0xD800) << 10) + (int(low, 16) - 0xDC00)
            return chr(code)
        code = int(single, 16)
        if 0xD800 <= code <= 0xDFFF:
            return "�"
        return chr(code)

    return _BACKSLASH_U_RE.sub(_replace, text)


def select_failure_summary_lines(lines: list[str], limit: int = 8) -> list[str]:
    """从外部脚本输出里挑出最能说明失败原因的几行。

    M7A 失败前会连打十几条同样的 WARNING，真正的 ERROR 和错误截图路径排在
    最后；单纯截尾会让通知首行落在一条「按 ESC 后重试」的 WARNING 上。有
    ERROR 级别行时只保留它们和截图/回溯行，否则退回截尾。
    """

    picked = [
        line
        for line in lines
        if _LOG_LEVEL_RE.search(line)
        or any(marker in line for marker in HSR_FAILURE_SUMMARY_KEEP_MARKERS)
    ]
    if not any(_LOG_LEVEL_RE.search(line) for line in picked):
        picked = list(lines)
    picked = [_LOG_TIME_PREFIX_RE.sub("", line) for line in picked]
    if len(picked) > limit:
        picked = picked[-limit:]
    return picked


def find_m7a_self_game_stop(lines: list[str]) -> str | None:
    """返回 M7A 自行关闭游戏的那行输出；没有则返回 None。"""

    for line in reversed(lines):
        if any(marker in line for marker in HSR_M7A_SELF_GAME_STOP_MARKERS):
            return line
    return None


HSR_DIVERGENT_FINAL_SUCCESS_M7A: tuple[str, ...] = (
    "已达到最高积分 12000，记录时间",  # divergent_universe.py:120
    "已达到最高积分 14000，记录时间",
    "已达到最高积分 18000，记录时间",
    "检测到积分奖励已由邮件发放，跳过积分检查",  # divergent_universe.py:104
    "「差分宇宙」积分奖励尚未刷新",  # daily.py:149
)
# SRA 差分宇宙和货币战争共用同一个 CosmicStrifeTask，都会打出
# 「旷宇纷争任务全部完成」。两个集合中同时存在该 marker 是预期行为，
# 歧义由 detect_weekly_completion 的 module_key 消除：
# sra_overrides（task_mapping.py）确保同一轮只启用其中一个，
# 调用方传入的 module_key 决定查哪组 marker。
HSR_DIVERGENT_FINAL_SUCCESS_SRA: tuple[str | re.Pattern[str], ...] = (
    "Mission accomplished",  # DivergentUniverse.py:40
    # OCR 可能把「18000/18000」切断或混入噪声，SRA 自己也按 ^18000.*18000$ 判
    re.compile(r"当前积分奖励: 18000.*18000"),  # DivergentUniverse.py:231-232
    "旷宇纷争任务全部完成",  # CosmicStrifeTask.py:29 / :71  ⚠️需配合 sra_overrides
)

HSR_CURRENCY_WARS_FINAL_SUCCESS_M7A: tuple[str, ...] = (
    "已达到最高积分 18000，记录时间",  # currency_wars.py:266
    "「货币战争」积分奖励尚未刷新",  # daily.py:131
)
HSR_CURRENCY_WARS_FINAL_SUCCESS_SRA: tuple[str, ...] = (
    "旷宇纷争任务全部完成",  # CosmicStrifeTask.py:65  ⚠️需配合 sra_overrides
    "达到终止状态：主界面",  # CurrencyWars.py:790
    "达到终止状态：游戏结束",  # CurrencyWars.py:790
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
    is_exit_pause_crash = HSR_CONSOLE_PAUSE_SUCCESS_MARKER in full_text or (
        HSR_NONINTERACTIVE_EOF_MARKER in full_text
        and any(marker in full_text for marker in HSR_CONSOLE_PAUSE_ERROR_MARKERS)
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
            if is_exit_pause_crash and any(
                marker in line for marker in HSR_EXIT_CRASH_LINE_MARKERS
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


def detect_echo_of_war_completion(
    result: object,
    script: str,
) -> tuple[bool, str]:
    """根据 M7A/SRA 输出判断本周历战余响是否已完成。

    Args:
        result: 外部脚本执行结果。
        script: 本次执行的引擎。
    """

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
            f"外部脚本日志显示历战余响仍需 {remaining} 次，本次未确认全部完成"
        )

    if any(marker in text for marker in HSR_EOW_COMPLETE_MARKERS):
        return True, "外部脚本日志显示历战余响体力计划已完成"

    # SRA 的完成判定先于通用未完成标记：历战余响战斗块没有失败痕迹即完成，
    # 块外其他体力任务的「体力不足」不能反过来否定它（它们共享同一管体力）。
    sra_attempts = _parse_max_int(HSR_EOW_SRA_PLAN_RE, text)
    if str(script).upper() == "SRA" and HSR_EOW_SRA_DONE_MARKER in text:
        if (
            sra_attempts is not None
            and sra_attempts >= HSR_ECHO_OF_WAR_WEEKLY_REWARD_LIMIT
        ):
            return True, f"SRA 日志显示历战余响已执行 {sra_attempts} 次"
        # 没有计划行才走战斗块兜底（v2.21.0+ 混跑与单独执行）；计划行还在的
        # 旧版保持按计划数判定，低体力只分配到部分次数的周不被误记完成。
        if sra_attempts is None and _sra_last_eow_battle_clean(text):
            return True, "SRA 日志显示历战余响战斗结束且无战斗失败，视为本周完成"

    if any(marker in text for marker in HSR_EOW_INCOMPLETE_MARKERS):
        return False, "外部脚本日志显示历战余响未完成或体力不足"

    return False, "未从外部脚本日志确认历战余响已完成"


def _parse_max_int(pattern: re.Pattern[str], text: str) -> int | None:
    values = []
    for match in pattern.finditer(text):
        try:
            values.append(int(match.group(1)))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def _sra_last_eow_battle_clean(text: str) -> bool:
    """判断最后一段历战余响战斗块内没有失败痕迹。

    SRA v2.21.0 起历战余响不再打印「将执行 N 次」计划行，改以
    「执行任务：历战余响」到最近一次「任务完成：历战余响」圈定战斗块；
    battle() 在战斗失败或等待战斗结束超时（-1）时同样会打印「任务完成」，
    所以块内出现「战斗失败」（不含「退出战斗失败」）或「等待战斗结束超时」
    都算没打完，块外的失败属于其他体力任务，不影响本判定。
    """

    done_pos = text.rfind(HSR_EOW_SRA_DONE_MARKER)
    if done_pos < 0:
        return False
    start_pos = text.rfind(HSR_EOW_SRA_START_MARKER, 0, done_pos)
    # 找不到开场行时从头算起：块只会偏大，方向是漏判而非误判。
    segment = text[start_pos:done_pos] if start_pos >= 0 else text[:done_pos]
    if HSR_EOW_SRA_BATTLE_TIMEOUT_MARKER in segment:
        return False
    return not HSR_EOW_SRA_BATTLE_FAILED_RE.search(segment)


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
        candidate_sets: tuple[tuple[str, tuple[str | re.Pattern[str], ...]], ...] = (
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
            (label, marker.pattern if isinstance(marker, re.Pattern) else marker)
            for label, markers in candidate_sets
            for marker in markers
            if (
                marker.search(text)
                if isinstance(marker, re.Pattern)
                else marker in text
            )
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
