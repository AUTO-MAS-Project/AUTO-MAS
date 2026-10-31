#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 节点日志采集参数（log_box 实例的喂参方）

ZZZ-OD 专项作为 log_box 的一个实例：本模块只提供参数（规则、后置处理器），
文本内核只匹配规则和执行处理器；读取、账号归属和交付由专项负责。

规则说明（对应 zzz-od 统一日志 .log/log.txt 的实际输出）：

- 应用级终态：``指令[ 应用名 ] 执行成功 / 执行失败``（operation.py 指令收尾
  行）。辅助指令（打开游戏/进入游戏/切换账号/返回大世界等）同样会落指令级
  收尾行，由后处理按应用目录名（app catalog）过滤，不为每条指令建规则。
- 跳过：执行应用组节点的「应用已完成 X」——zzz-od 按当日运行记录跳过已
  完成任务；「应用未启用 X」是用户主动关闭，不进报告。
- 账号（实例）段边界：一条龙启动与每次切换实例都会落「开始加载实例配置 N」，
  其后到下一个段边界之间的节点归属该实例；idx 到账号名的映射由调用方提供
  （原生来源=原生注册表快照，注入=绑定槽的用户名）。

规则产出中间标记，由 make_zzzod_resolve 后处理解析聚合：
  - "SEG: idx" = 段边界（切换当前账号）
  - "OK: 名称" / "OK: 名称|后缀" = 应用成功（后缀原样拼在节点后，如体力电量）
  - "FAIL: 名称|原因" / "FAIL: 名称" = 应用失败（带返回状态原因时经 `|` 拼接）
  - "SKIP: 名称" = 跳过
  - "⚠ 异常: 应用名（原因）" = 警告行：应用成功收尾，但其执行窗口内存在
    未被恢复、且原因命中白名单（_WARNING_FAIL_REASONS，fail-closed，仅注册的
    有价值异常才透出，如体力刷本计划被游戏拦截后仍按「返回大世界」成功结束）
    的辅助指令失败，紧跟对应应用节点行输出；判定仍取上游结果面。
    ⚠ 异常 是通用渲染层（Notify.report）认可的第四种状态前缀，
    汇总模式下按状态归组
多账号（≥2 个实例段）时节点行加「【账号名】」前缀（报告渲染按前缀区分账号
归属，见 Notify.report）；单账号不加前缀，与通用「状态: 节点」渲染
一致。同一账号同一应用取最后一次非跳过终态（整体口径）：重试轮的「应用已
完成」跳过行不覆盖此前成功/失败，只给从未出现的应用补录跳过态；真实重跑
的应用随最后一次终态移至末尾。
"""

import re

from app.utils import LOG_TYPE_NORMAL, log_box

# 推送规则：(匹配正则, 提取表达式)；均为普通类型，节点级失败由文本「❌ 失败:」
# 体现（始终展示），推送时机由全局 SendTaskResultTime 控制。
# 顺序敏感（apply_patterns 首个命中即产出）：
#   - 体力刷本专属成功规则必须在通用成功规则之前（终态行自带刷本后的最终
#     「剩余电量 N」，通用规则先命中会把电量丢掉）；
#   - 带原因的失败规则必须在兜底失败规则之前（兜底规则命中带原因的行会把
#     原因丢掉）。
ZZZOD_PUSH_RULES: list[tuple[str, str]] = [
    # 实例段边界（idx 由后处理映射为账号名）
    (r"开始加载实例配置 (\d+)", r'"SEG:" + $((?:开始加载实例配置 )(\d+))'),
    # 体力刷本成功（返回状态自带刷本后的最终电量，resolve 据此在报告末尾
    # 追加「🔋 剩余体力」独立行；体力刷本为 zzz-od 电量应用的固定名）
    (
        r"指令\[ 体力刷本 \] 执行成功 返回状态 剩余电量 (\d+)",
        r'"OK:体力刷本|🔋" + $((?:返回状态 剩余电量 )(\d+))',
    ),
    # 应用级成功（辅助指令由后处理按应用目录名过滤）
    (r"指令\[ (.+?) \] 执行成功", r'"OK:" + $((?:指令\[ )(.+?)(?= \] 执行成功))'),
    # 应用级失败（带返回状态原因；匹配正则保证两个提取片段都命中，
    # 规避「一行内所有 $() 必须全命中」导致的原因缺失丢行问题）
    (
        r"指令\[ (.+?) \] 执行失败 返回状态 (.+)",
        r'"FAIL:" + $((?:指令\[ )(.+?)(?= \] 执行失败)) + "|" + $((?:返回状态 )(.+))',
    ),
    # 应用级失败（无返回状态时的兜底）
    (r"指令\[ (.+?) \] 执行失败", r'"FAIL:" + $((?:指令\[ )(.+?)(?= \] 执行失败))'),
    # 跳过（zzz-od 按当日运行记录跳过已完成任务）
    (r"应用已完成 (.+)$", r'"SKIP:" + $((?:应用已完成 )(.+))'),
]

# 「【账号名】」前缀（多账号节点行），交付扩展据此做路由拆分。
ACCOUNT_PREFIX_RE = re.compile(r"^【(.+?)】(.*)$")

_KIND_STATUS = {"OK": "✅ 成功", "FAIL": "❌ 失败", "SKIP": "⏭ 跳过"}
_KIND_RE = re.compile(r"^(OK|FAIL|SKIP):(.*)$")

# 「通知」应用失败 = 上游汇总信号（本轮存在失败任务时它把自己标失败），
# 消息本身已发出（fire-and-forget），真实失败由对应节点行体现，剔除避免误导
_SUMMARY_FAIL_APP_NAMES = frozenset({"通知"})

# ⚠ 警告白名单（2026-10 维护者决策：fail-closed）——上游大量「执行失败」
# 终态是有意跳过（电量不足/特训目标已达成/深度追猎路由）或会自行重试的噪音，
# 只有注册为有价值异常的原因才透出；按精确匹配，上游改文案后需同步更新
_WARNING_FAIL_REASONS = frozenset(
    {
        # 出战被游戏拦截（驱动盘库存已满），计划实际没跑、体力没消耗
        "驱动盘数量已达到可拥有上限",
    }
)


def make_zzzod_resolve(
    app_names: set[str], idx_names: dict[int, str]
) -> log_box.PostProcessor:
    """构造 log_box 后置处理器（节点终态聚合 + 账号归属 + 白名单吞失败警告）。

    输入/输出均为 ``(log_type, text, ts)`` 元组（与 log_box 后置处理器契约
    一致）。

    Args:
        app_names: 应用目录的应用名集合（一条龙 app 本体已被 catalog 排除），
            用于过滤指令级成功/失败行中的辅助指令。
        idx_names: 实例 idx → 账号名映射（原生来源=原生注册表；注入=绑定槽用户名）。
    """

    def resolve(
        results: list[tuple[str, str, float | None]],
    ) -> list[tuple[str, str, float | None]]:
        order: list[tuple[str | None, str]] = []
        states: dict[tuple[str | None, str], tuple[str, str | None, float | None]] = {}
        battery: dict[str | None, tuple[int, float | None]] = {}
        # 待归因窗口：账号 → 辅助指令名 → 最后一次失败原因。辅助指令失败先记入
        # 当前账号窗口，成功视为该指令已恢复；窗口由应用终态行/段边界结算
        pending_fails: dict[str | None, dict[str, str]] = {}
        # 应用节点 → ⚠ 警告文本（同 key 重现时整体替换，与 states 的最后
        # 一次终态口径一致）
        warnings: dict[tuple[str | None, str], list[str]] = {}
        seg_names: set[str] = set()
        current: str | None = None

        for _, text, ts in results:
            if text.startswith("SEG:"):
                try:
                    idx = int(text[4:])
                except ValueError:
                    continue
                current = idx_names.get(idx) or f"实例 {idx}"
                seg_names.add(current)
                # 段边界收束该账号崩溃残留的窗口，避免泄入新段
                pending_fails.pop(current, None)
                continue
            m = _KIND_RE.match(text)
            if m is None:
                continue
            kind, node = m.group(1), m.group(2)
            extra: str | None = None
            if "|" in node:
                node, extra = node.split("|", 1)
            if kind in ("OK", "FAIL") and node not in app_names:
                # 辅助指令（返回大世界/进入游戏/切换账号等）不是应用节点
                if kind == "FAIL":
                    pending_fails.setdefault(current, {})[node] = extra or ""
                else:
                    pending_fails.get(current, {}).pop(node, None)
                continue
            if kind == "FAIL" and node in _SUMMARY_FAIL_APP_NAMES:
                # 「通知」失败是上游的「本轮存在失败」汇总信号，非发送失败
                pending_fails.pop(current, None)
                continue
            if kind == "OK" and extra is not None and extra.startswith("🔋"):
                # 体力刷本的最终电量：节点行照常输出（不带后缀），电量记录
                # 下来在报告末尾追加独立行「🔋 剩余体力: N」（多账号按账号
                # 归属，同账号取最后一次刷本后的值）
                try:
                    battery[current] = (int(extra[len("🔋") :]), ts)
                except ValueError:
                    pass
                extra = None
            key = (current, node)
            if kind == "SKIP":
                # 跳过行不是执行终态，只是「本轮没跑、已完成」的证据：可能是
                # MAS 开跑前就已完成（恶名狩猎），也可能是本轮前序重试轮做成
                # 的（重试轮按运行记录跳过已完成任务）。已有终态的应用不被
                # 跳过行覆盖也不移位，只给从未出现的应用补录跳过态
                pending_fails.pop(current, None)
                if key not in states:
                    states[key] = (_KIND_STATUS["SKIP"], None, ts)
                    order.append(key)
                continue
            if key in states:
                order.remove(key)  # 移至末尾：保留最后一次非跳过终态的出现顺序
            order.append(key)
            # 取最后一次非跳过终态（整体口径）：重试轮的「应用已完成」不能
            # 覆盖此前成功/失败，只有真实重跑（如体力刷本）才更新状态
            states[key] = (_KIND_STATUS[kind], extra, ts)
            # 结算窗口：应用终态行收束本段（自上一应用终态行或段边界起）的
            # 待归因失败。上游流程图会把计划级失败吞成成功收尾（如体力刷本
            # 计划被拦截后仍按「返回大世界」成功结束），只有成功收尾才需要
            # 把白名单内的有价值失败以 ⚠ 透出；应用失败行自带原因，直接
            # 丢弃窗口
            window_fails = pending_fails.pop(current, {})
            warn_texts: list[str] = []
            if kind == "OK":
                # 指令层不展示，只按原因去重透出，格式与 ❌ 失败行同构
                reasons = dict.fromkeys(
                    reason
                    for reason in window_fails.values()
                    if reason in _WARNING_FAIL_REASONS
                )
                warn_texts = [f"⚠ 异常: {node}（{reason}）" for reason in reasons]
            warnings[key] = warn_texts

        multi = len(seg_names) > 1
        output: list[tuple[str, str, float | None]] = []
        for account, node in order:
            status, extra, ts = states[(account, node)]
            if extra is None:
                line = f"{status}: {node}"
            else:
                # extra 为返回状态原因（仅 FAIL）
                line = f"{status}: {node}（{extra}）"
            if multi and account:
                line = f"【{account}】{line}"
            output.append((LOG_TYPE_NORMAL, line, ts))
            for warn in warnings.get((account, node), ()):
                if multi and account:
                    warn = f"【{account}】{warn}"
                output.append((LOG_TYPE_NORMAL, warn, ts))
        # 剩余体力独立成行（对齐 ok-nte 的「⚡ 剩余体力」），追加在各账号
        # 节点之后；汇总渲染时普通行位于常规状态组之后、「⚠ 异常」组之前
        for account, (value, ts) in battery.items():
            line = f"🔋 剩余体力: {value}"
            if multi and account:
                line = f"【{account}】{line}"
            output.append((LOG_TYPE_NORMAL, line, ts))
        return output

    return resolve
