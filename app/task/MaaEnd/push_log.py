#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""MaaEnd 推送日志采集参数（log_box 实例的喂参方）

MaaEnd 专项作为 log_box 的一个实例：本模块只提供参数（规则、后置处理器），
日志获取、规则匹配、后置处理与推送全部由 log_box 完成。

与其他专项 tail 脚本自身的日志文件不同，MaaEnd 的任务级进度行
（任务开始/任务完成/任务失败）只打印在 MaaEnd.exe 的 stdout，上游不落盘；
MAS 在 AutoProxy.final_task 已把 stdout 全文按阶段落盘为历史日志
（``Config.save_maaend_log``），本专项以这些历史日志为采集源
（``start_from_end=False`` 全文采集），不新增任何管道。

规则说明（对应 MaaEnd.exe stdout 实际输出，行首带 ``[时间戳] `` 前缀）：

- ``[时间戳] 任务开始: <任务名>``：开始标记。只有开始没有终态（进程中途
  退出/崩溃）表示任务未跑完，由 ``maaend_resolve`` 判为失败——与判态
  「未见完成而退出视为异常」一致；区别于 ok-ww「裸节点名默认成功」。
- ``[时间戳] 任务完成: <任务名>``：明确成功。
- ``[时间戳] 任务失败: <任务名>``：明确失败（含账号切换失败等）。
- 预任务（``__MXU_PRETASK__`` 等）走「正在执行预任务」行，不产出节点；
  MaaFW 框架镜像行（英文）天然不命中规则。
- 节点名中的 emoji 与装饰符号在 ``maaend_resolve`` 统一去除（状态标记
  ✅/❌ 是聚合渲染的功能性前缀，保留；重开原生图标见 ``_strip_emoji``）。
- 规则同时捕获行内时间戳，``maaend_resolve`` 解析为节点真实发生时刻——
  全文回扫的采集时刻与节点发生时刻无关，「逐条」推送模式的时间前缀依赖它。
- 匹配空白用 ``\\s*``，与判态侧 ``check_log`` 的容差同源，避免上游格式
  微调时节点详情与结果行静默分叉。

同一任务跨重试/跨阶段多次出现时以**最后一次出现**为准（MAS 判态的重试
收束语义：先前失败的任务重试成功即视为完成），顺序按最后一次出现排列。
已知限制：聚合按任务名、判态按任务 id——同名任务启用多实例且单轮内
「先失败后完成」时，节点详情显示成功而结果行按 id 判失败（展示层边角，
push_log 层无法感知 id，以结果行为准）。
"""

import re
from contextlib import suppress
from datetime import datetime

from app.log_box.logtype import LogType

# 推送规则：(匹配正则, 提取表达式)；均为普通类型，节点级失败由文本「❌ 失败:」
# 体现（始终展示），推送时机由全局 SendTaskResultTime 控制。
# 提取表达式产出「行内时间戳 + 换行 + 任务名」的中间形态（$() 多捕获组以
# 换行拼接），终态行再由 ``+`` 拼接状态字面量；maaend_resolve 据此还原节点
# 真实时刻。匹配正则与提取正则的空白容差保持一致（\\s*）。
MAAEND_PUSH_RULES: list[tuple[str, str]] = [
    # 开始标记：提取裸任务名，终态由 maaend_resolve 聚合
    (
        r"^\[([^\]]+)\]\s*任务开始:\s*(.+)",
        r"$((?:^\[)([^\]]+)(?:\]\s*任务开始:\s*)(.+))",
    ),
    # 明确成功
    (
        r"^\[([^\]]+)\]\s*任务完成:\s*(.+)",
        r'"✅ 成功: " + $((?:^\[)([^\]]+)(?:\]\s*任务完成:\s*)(.+))',
    ),
    # 明确失败（顺序无关：三个前缀互不为子串）
    (
        r"^\[([^\]]+)\]\s*任务失败:\s*(.+)",
        r'"❌ 失败: " + $((?:^\[)([^\]]+)(?:\]\s*任务失败:\s*)(.+))',
    ),
]

# 规则产出文本形态：<可选「状态: 」前缀><行内时间戳>\n<任务名>
_ENTRY_RE = re.compile(r"^(?:(✅ 成功|❌ 失败): )?(.*)\n(.*)$", re.DOTALL)
# 兜底：不含行内时间戳的旧式「状态: 节点」文本（如直接调用 resolve 的测试）
_STATUS_RE = re.compile(r"^(✅ 成功|❌ 失败): (.*)$")

# 行内时间戳格式（MaaEnd stdout 前缀，本机本地时间）
_LINE_TS_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


# ── 节点名 emoji 清理 ────────────────────────────────────────────────────────
# MaaEnd 任务名自带图标（🤝拜访好友、🎱基质刷取、❌关闭游戏（PC） 等），与推送
# 报告的状态标记（✅ 成功/❌ 失败）混排时视觉杂乱，且「❌关闭游戏」这类名字
# 易被误读为失败标记，采集侧统一去除节点名中的 emoji 与装饰符号。
# 未来若想保留原生任务名图标：注释掉 maaend_resolve 中的 _strip_emoji 调用
# 即可，规则与聚合逻辑不受影响。

# 覆盖：各 emoji 区段（符号/表情/传输/补充符号）、Dingbats 与杂项符号（❌✂⭐⏰）、
# 变体选择符与零宽连接符；不含 CJK 与全角标点，任务名正文不受影响。
_EMOJI_STRIP_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3]"
)


def _strip_emoji(name: str) -> str:
    """去除节点名中的 emoji 与装饰符号，并清理首尾空白。"""

    return _EMOJI_STRIP_RE.sub("", name).strip()


def _parse_line_ts(value: str, fallback: float) -> float:
    """把行内时间戳解析为节点发生时刻（本机本地时间）；失败回退采集时刻。"""

    with suppress(ValueError):
        return datetime.strptime(value, _LINE_TS_FORMAT).timestamp()
    return fallback


# 状态秩：开始占位 < 成功 < 失败（仅用于输出时区分开始占位；聚合本身按
# 最后一次出现为准，不按秩取最坏——与判态「重试成功即完成」保持一致）
_START_RANK = 0
_SUCCESS_RANK = 1
_FAIL_RANK = 2


def maaend_resolve(results: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    """后处理：按任务聚合最终状态，保持最后一次出现顺序

    输入/输出均为 ``(log_type, text, ts)`` 元组（与 log_box `_PostProcessor`
    契约一致），日志类型与采集时间戳随元组一并保留；ts 优先取规则捕获的
    行内时间戳（节点真实发生时刻），缺失时回退采集时刻。聚合语义：

    - 终态（✅/❌）与开始标记都按「最后一次出现」生效：重试轮的终态覆盖
      上一轮结果，与 AutoProxy 判态的 task_dict 收束一致；
    - 只有开始标记没有终态的任务（进程中途退出/崩溃）输出「❌ 失败:」；
    - 未匹配任何标记的结果文本不会出现（规则只产出上述三类标记）。
    """

    order: list[str] = []
    states: dict[str, tuple[int, str, float]] = {}
    for _, text, ts in results:
        m = _ENTRY_RE.fullmatch(text)
        if m is not None:
            status, raw_name = m.group(1), m.group(3)
            node_ts = _parse_line_ts(m.group(2), ts)
        else:
            sm = _STATUS_RE.match(text)
            if sm is not None:
                status, raw_name = sm.group(1), sm.group(2)
            else:
                status, raw_name = None, text
            node_ts = ts
        # 剥离后为空（纯 emoji/装饰符任务名）时回退原名，避免空名节点坍缩
        node = _strip_emoji(raw_name) or raw_name
        if status is None:
            rank, display = _START_RANK, ""
        else:
            rank = _FAIL_RANK if status == "❌ 失败" else _SUCCESS_RANK
            display = f"{status}: {node}"
        if node in states:
            order.remove(node)  # 移至末尾：保留最后一次出现顺序
        order.append(node)
        states[node] = (rank, display, node_ts)
    return [
        (
            LogType.NORMAL,
            states[node][1] if states[node][0] != _START_RANK else f"❌ 失败: {node}",
            states[node][2],
        )
        for node in order
    ]
