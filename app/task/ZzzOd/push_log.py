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
日志获取、规则匹配、后置处理与推送全部由 log_box 完成。

规则说明（对应 zzz-od 统一日志 .log/log.txt 的实际输出）：

- 应用级终态：``指令[ 应用名 ] 执行成功 / 执行失败``（operation.py 指令收尾
  行）。辅助指令（打开游戏/进入游戏/切换账号/返回大世界等）同样会落指令级
  收尾行，由后处理按应用目录名（app catalog）过滤，不为每条指令建规则。
- 跳过：执行应用组节点的「应用已完成 X」——zzz-od 按当日运行记录跳过已
  完成任务；「应用未启用 X」是用户主动关闭，不进报告。
- 账号（实例）段边界：一条龙启动与每次切换实例都会落「开始加载实例配置 N」，
  其后到下一个段边界之间的节点归属该实例；idx 到账号名的映射由调用方提供
  （直控=原生注册表快照，注入=绑定槽的用户名）。

规则产出中间标记，由 make_zzzod_resolve 后处理解析聚合：
  - "SEG: idx" = 段边界（切换当前账号）
  - "OK: 名称" / "OK: 名称|后缀" = 应用成功（后缀原样拼在节点后，如体力电量）
  - "FAIL: 名称|原因" / "FAIL: 名称" = 应用失败（带返回状态原因时经 `|` 拼接）
  - "SKIP: 名称" = 跳过
多账号（≥2 个实例段）时节点行加「【账号名】」前缀（报告渲染按前缀区分账号
归属，见 app/tools/push_log.py）；单账号不加前缀，与通用「状态: 节点」渲染
一致。同一账号同一应用取最后一次出现的终态（MAS 重试轮以最后一轮为准），
顺序按首次出现排列。
"""

import re

from app.log_box.logtype import LogType

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

# 「【账号名】」前缀（多账号节点行），AutoProxy 的 sink 也用它做路由拆分
ACCOUNT_PREFIX_RE = re.compile(r"^【(.+?)】(.*)$")

_KIND_STATUS = {"OK": "✅ 成功", "FAIL": "❌ 失败", "SKIP": "⏭ 跳过"}
_KIND_RE = re.compile(r"^(OK|FAIL|SKIP):(.*)$")

# 「通知」应用失败 = 上游汇总信号（本轮存在失败任务时它把自己标失败），
# 消息本身已发出（fire-and-forget），真实失败由对应节点行体现，剔除避免误导
_SUMMARY_FAIL_APP_NAMES = frozenset({"通知"})


def make_zzzod_resolve(app_names: set[str], idx_names: dict[int, str]):
    """构造 log_box 后置处理器（节点终态聚合 + 账号归属）。

    输入/输出均为 ``(log_type, text, ts)`` 元组（与 log_box 后置处理器契约
    一致）。

    Args:
        app_names: 应用目录的应用名集合（一条龙 app 本体已被 catalog 排除），
            用于过滤指令级成功/失败行中的辅助指令。
        idx_names: 实例 idx → 账号名映射（直控=原生注册表；注入=绑定槽用户名）。
    """

    def resolve(
        results: list[tuple[str, str, float]],
    ) -> list[tuple[str, str, float]]:
        order: list[tuple[str | None, str]] = []
        states: dict[tuple[str | None, str], tuple[str, str | None, float]] = {}
        battery: dict[str | None, tuple[int, float]] = {}
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
                continue
            if kind == "FAIL" and node in _SUMMARY_FAIL_APP_NAMES:
                # 「通知」失败是上游的「本轮存在失败」汇总信号，非发送失败
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
            if key in states:
                order.remove(key)  # 移至末尾：保留最后一次出现顺序
            order.append(key)
            # 取最后一次出现的终态：MAS 重试轮里 zzz-od 会按运行记录跳过
            # 已完成任务，最后一轮的状态才代表本次任务的最终结果
            states[key] = (_KIND_STATUS[kind], extra, ts)

        multi = len(seg_names) > 1
        output: list[tuple[str, str, float]] = []
        for account, node in order:
            status, extra, ts = states[(account, node)]
            if extra is None:
                line = f"{status}: {node}"
            else:
                # extra 为返回状态原因（仅 FAIL）
                line = f"{status}: {node}（{extra}）"
            if multi and account:
                line = f"【{account}】{line}"
            output.append((LogType.NORMAL, line, ts))
        # 剩余体力独立成行（对齐 ok-nte 的「⚡ 剩余体力」），追加在各账号
        # 节点之后；汇总渲染时普通行位于状态聚合行之后，恰好收尾用户块
        for account, (value, ts) in battery.items():
            line = f"🔋 剩余体力: {value}"
            if multi and account:
                line = f"【{account}】{line}"
            output.append((LogType.NORMAL, line, ts))
        return output

    return resolve
