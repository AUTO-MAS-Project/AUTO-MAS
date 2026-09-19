#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BetterGI「一条龙」分步执行报告解析。

从 BetterGI Serilog 日志逐条还原「一条龙」每一步做了什么、成没成功，供统计通知的分步报告。
本模块刻意只依赖 ``re``（纯解析、零业务依赖），以便测试能像 ``one_dragon.py`` 那样经
``importlib`` 按文件路径独立加载，绕开 ``app.task`` 包急切 import 触发的循环依赖。

日志结构（真实样本，Serilog 头行 ``[HH:mm:ss.fff] [INF] ...LoggerName`` 下方紧随消息行）：
    一条龙任务执行: 1/3           ← 步开始（头行携带时间戳）
    → "任务启动！"
    邮件："全部领取"              ← 任务名/进度描述；`→ "前往合成台" 开始` 同理
    [ERR] ...                     ← 步内可恢复异常（BGI 任务级异常会跳过步内子任务继续跑）
    → "任务结束"                 ← 步正常结束
    一条龙和配置组任务结束          ← 整条收尾（成败由 AutoProxy._one_dragon_sequence_done 判定）

⚠️ 进度行只有序号、BGI 也不打印本步的任务名，而步内第一条日志常常是传送/等待之类的
过程日志（``区域选择动画等待达到上限："至冬"``、``切换到区域："尘歌壶"``），
所以**任务名不能靠「取第一条日志行」猜**（2026-09-19 实机：分步表出现
「区域选择动画等待达到上限」当任务名）。权威来源是本次启动的那份一条龙配置，
调用方按 ``TaskOrder`` 传 ``task_names``（见 ``one_dragon.enabled_one_dragon_task_names``）；
读不到配置或长度对不上时，才退回日志行内推断（结果可能粗糙，但不会张冠李戴）。

整条是否完成不属于本模块职责；本模块只负责「按执行顺序列出每一步 + 经过与成败」。

另有执行层路径（``MASOneDragon/main.js`` 经 ``--startGroups`` 运行）不打原生进度行，改打
``MAS_STEP_*`` 标记，由本模块的 ``parse_execution_layer_report`` 还原成**同一结构**的步骤表，
两条路径共用同一套通知渲染（2026-09-15：执行层运行的通知此前完全没有流程表格）。
"""

import re

# 一条龙进度行的正则：「一条龙任务执行: X/N」（可带空格/斜杠）
_BGI_STEP_PROGRESS_RE = re.compile(r"一条龙任务执行:\s*(\d+)\s*/\s*(\d+)")
# 执行层步标记的公共前缀（main.js 打出，见 res/templates/BetterGI/MASOneDragon/main.js）
_MAS_STEP_PREFIX = "MAS_STEP_"
# Serilog 头行时间戳：「[HH:mm:ss(.fff)] ...」
_BGI_STEP_TIME_RE = re.compile(r"\[(\d{1,2}:\d{2}:\d{2}(?:\.\d{1,3})?)\]")
# 步内可恢复异常的信号（BGI TaskRunner 捕获后不 rethrow，一条龙继续跑下一条）。
# 真实 BGI Serilog 里级别写在头行的第二个括号（``[..] [ERR] [Primary:..]``），
# 消息/异常原因另起一行；``任务执行异常``/``执行失败`` 则直接出现在消息行。
_BGI_STEP_HEADER_ERR_HINTS = ("[ERR]", "[FTL]")
_BGI_STEP_ISSUE_HINTS = ("[ERR]", "任务执行异常", "执行失败")

# ── BGI 配置组内「项目」的执行行 ──────────────────────────────
# 队列里的自定义项（配置组 / 脚本 / 路径 / 录制）由 ``--startGroups`` 直连 BGI 配置组执行，
# 完全不经过 main.js，因此一个 MAS_STEP_* 也不打；只能从 BGI ScriptService 这对日志还原
# （2026-09-19 实机：这类条目在通知里整块缺失，分步表只剩执行层/原生两相）：
#   → 开始执行JS脚本: "读取当前树脂"              脚本项（js）
#   → 开始执行地图追踪任务: "01绀田村-刀镡.json"   路径项（pathing，一条路线一行）
#   → 开始执行键鼠脚本: "BetterGI_GCM_xxx.json"   录制项（keymouse）
#   → 脚本执行结束: "<名称>", 耗时: 0分17.743秒    三类共用的收尾行
# 配置组项（scriptgroup）没有自己的标记：它内部的项目照上面三种形态各自出行。
_BGI_PROJECT_BEGIN_RE = re.compile(
    r'^→\s*开始执行(?:JS脚本|地图追踪任务|键鼠脚本):\s*"(?P<name>[^"]+)"'
)
_BGI_PROJECT_END_RE = re.compile(r'^→\s*脚本执行结束:\s*"(?P<name>[^"]+)"')


def _clean_step_task(line: str) -> str:
    """把日志里的一步描述提炼成简短任务名。

    ``→ "前往合成台" 开始`` → ``前往合成台``；``邮件："全部领取"`` → ``邮件``；
    ``▶ "领取『每日委托』奖励" 未完成`` → ``领取『每日委托』奖励``。

    仅在拿不到配置里的任务名表时兜底使用（见 ``parse_one_dragon_report`` 的
    ``task_names``）：拿到的往往是步内第一条过程日志，未必是任务名。
    """
    s = line.strip()
    s = re.sub(r"^[→▶]\s*", "", s)
    s = s.replace('"', "").replace("“", "").replace("”", "")
    s = re.sub(r"\s*(?:开始|结束)\s*$", "", s)
    if "：" in s:
        s = s.split("：", 1)[0]
    elif ":" in s:
        s = s.split(":", 1)[0]
    return s.strip() or "未知任务"


def _align_task_names(
    steps: list[dict], task_names: list[str] | None
) -> list[str] | None:
    """把外部的任务名表与进度行序号对齐；对不上返回 None（由调用方退回日志推断）。

    只在「表长 == 进度行的总数」且每步的 ``total`` 与序号都在范围内时才采用：
    BGI 的 ``N`` 只计启用的一条龙任务，长度不符说明配置与本次运行对不上
    （例如运行期间改了配置），此时宁可用日志里推断的粗糙名字，也不给错位的名字。
    """
    if not task_names:
        return None
    total = int(steps[0].get("total") or 0)
    if total != len(task_names):
        return None
    for step in steps:
        index = int(step.get("index") or 0)
        if int(step.get("total") or 0) != total or not 1 <= index <= total:
            return None
    return task_names


def parse_one_dragon_report(
    log: str, task_names: list[str] | None = None
) -> list[dict] | None:
    """解析「一条龙」分步执行报告，按执行顺序返回步骤字典列表。

    每步字段：``index``/``total``（第几条/共几条）、``task``（任务名）、``start``/``end``
    （起止时间 HH:MM:SS）、``ok``（是否走完 ``→ "任务结束"``）、``issue_count``/``issue_text``
    （步内可恢复异常数目与首条原因摘要，无异常为空串）。
    本会话未跑一条龙（无 ``一条龙任务执行`` 行）时返回 None，调用方据此省略分步区块。

    Args:
        log: BGI 日志全文。
        task_names: 本次运行的一条龙任务名，按 ``TaskOrder`` 顺序（仅启用的内置任务，
            见 ``one_dragon.enabled_one_dragon_task_names``）。长度与进度行的 ``N``
            一致时按序号取用；缺省/不符时退回日志行内推断。
    """
    lines = log.splitlines()
    steps: list[dict] = []
    cur: dict | None = None
    last_time = ""
    pending_err = False  # 上一条头行级别为 [ERR]/[FTL]，紧随其后的消息行即异常原因

    def finalize() -> dict:
        assert cur is not None
        return {
            **cur,
            "issue_count": len(cur["issue"]),
            "issue_text": cur["issue"][0].strip() if cur["issue"] else "",
        }

    for raw in lines:
        m = _BGI_STEP_TIME_RE.match(raw)
        if m:
            last_time = m.group(1)
            # 头行级别槽带 [ERR]/[FTL] 且当前在某条一步内 → 下一条消息行即异常原因
            pending_err = cur is not None and any(
                h in raw for h in _BGI_STEP_HEADER_ERR_HINTS
            )
            continue
        line = raw.strip()
        if not line:
            continue

        if pending_err:
            # 该消息属于上一条 [ERR] 头行：记入问题，不参与任务名解析
            pending_err = False
            if cur is not None and "任务启动" not in line and "任务结束" not in line:
                cur["issue"].append(line)
            continue

        pm = _BGI_STEP_PROGRESS_RE.match(line)
        if pm:
            if cur is not None:  # 上一步异常中断（无「任务结束」）也先收尾再开新步
                cur["end"] = cur["end"] or last_time
                cur["ok"] = False
                steps.append(finalize())
            cur = {
                "index": int(pm.group(1)),
                "total": int(pm.group(2)),
                "task": "",
                "start": last_time,
                "end": "",
                "ok": True,
                "issue": [],
            }
            continue
        if cur is None:
            continue

        if line == '→ "任务结束"':
            # 走完「任务结束」即该步成功；步内 [ERR] 是 BGI 可恢复异常，只记为 issue，
            # 不把本可完成的一条龙某步误判失败（与 _one_dragon_sequence_done 语义一致）。
            cur["end"] = last_time
            cur["ok"] = True
            steps.append(finalize())
            cur = None
        elif "任务启动" in line:
            continue
        else:
            if not cur["task"]:
                cur["task"] = _clean_step_task(line)
            if any(h in line for h in _BGI_STEP_ISSUE_HINTS):
                cur["issue"].append(line)

    if cur is not None:  # 日志结束仍停留在某一步（未收尾）→ 该步未完成
        cur["end"] = cur["end"] or last_time
        cur["ok"] = False
        steps.append(finalize())

    if not steps:
        return None
    # 任务名优先取配置里的权威顺序表（进度行不带名字），对不上才用中途推断的结果
    aligned = _align_task_names(steps, task_names)
    # 移除解析过程使用的内部 issue 原始行，避免携带多余细节（已汇总为 issue_count/text）
    for s in steps:
        if aligned is not None:
            s["task"] = aligned[int(s["index"]) - 1]
        s.pop("issue", None)
    return steps


def parse_execution_layer_report(log: str) -> list[dict] | None:
    """解析执行层分步执行报告，字段与 ``parse_one_dragon_report`` 一致。

    一次 ``--startGroups`` 里有两种步，按日志出现顺序（= 实际执行顺序）合成同一张表：

    1. **main.js 自编排的战斗步**，标记布局（见 ``res/templates/BetterGI/MASOneDragon/main.js``）::

        MAS_STEP_BEGIN: <uid> <名称>               步开始
        MAS_STEP_DONE: <uid> <名称>                步正常结束
        MAS_STEP_FAIL: <uid> <名称> <原因>         运行期失败（该步跳过、继续后续步）
        MAS_STEP_RESIN_END: <uid> <名称> <原因>    树脂耗尽的预期停止（算正常收尾）
        MAS_STEP_MISSING_CONFIG: <uid> <名称> <原因> 必填项缺失，根本没进 BGI
        MAS_PLAN_DONE / MAS_PLAN_DONE_WITH_FAILURES <n> / MAS_PLAN_RESIN_END /
        MAS_PLAN_FAIL <原因>                       整条收尾（本函数不消费，成败由调用方判定）

    2. **直连 BGI 配置组的自定义项**（队列中的配置组 / 脚本 / 路径 / 录制），BGI 的项目级日志
       （见 ``_BGI_PROJECT_BEGIN_RE``）：每个项目一行，配置组项按其内部项目各自出行。

    MASOneDragon 执行层自身也是一个 BGI 项目（``→ 开始执行JS脚本: "MAS一条龙执行层"``），
    它的步已由 ``MAS_STEP_*`` 逐条列出，故「内部出现过 MAS 标记的项目」不再单独出一行总账。

    只列出执行层**真正处理过**的步（出现过 BEGIN 的、必填项缺失被拦下的、BGI 项目开始过的）：
    ``MAS_STEP_SKIP``/``SKIP_WEEKDAY``/``DAILY``/``UNKNOWN`` 要么由随后启动的原生一条龙承接、
    要么本次本就不跑，混进来会让「第几条/共几条」失真。

    本会话未走执行层（既无步标记也无 BGI 项目行）时返回 None，调用方据此省略分步区块。
    """
    lines = log.splitlines()
    steps: list[dict] = []
    cur: dict | None = None  # 当前打开的 MAS 步
    project: dict | None = None  # 当前打开的 BGI 项目步（自定义项）
    last_time = ""
    pending_err = False  # 上一条头行级别为 [ERR]/[FTL]，紧随其后的消息行即异常原因
    project_has_mas = False  # 当前 BGI 项目内部打了 MAS 标记 → 它就是执行层本体

    def finalize(ok: bool) -> None:
        assert cur is not None
        cur["end"] = cur["end"] or last_time
        cur["ok"] = bool(ok and cur["ok"])
        steps.append(
            {
                **cur,
                "issue_count": len(cur["issue"]),
                "issue_text": cur["issue"][0].strip() if cur["issue"] else "",
            }
        )

    def start(uid: str, name: str) -> None:
        nonlocal cur
        cur = {
            "index": len(steps) + 1,
            "total": 0,  # 收尾时统一回填（见末尾），此处占位
            "task": name or uid,
            "start": last_time,
            "end": "",
            "ok": True,
            "issue": [],
        }

    def close_project(ok: bool) -> None:
        """收尾当前 BGI 项目步。

        BGI 在项目失败时也会「伪造」收尾行照打 ``脚本执行结束``（路径任务失败即
        ``耗时: 0分0.000秒``，见 2026-09-10 实机），故成败不能只看收尾行：步内出现过
        ``[ERR]`` 的按失败处理，并把原因带进通知（否则失败的路线会显示成成功）。
        """
        nonlocal project
        if project is None:
            return
        if not project_has_mas:
            project["end"] = project["end"] or last_time
            project["ok"] = bool(ok and not project["issue"])
            steps.append(
                {
                    **project,
                    "issue_count": len(project["issue"]),
                    "issue_text": project["issue"][0].strip() if project["issue"] else "",
                    # 标记来源：调用方据此把自定义项失败计入「部分失败」（见 count_failed_custom_items）
                    "bgi_project": True,
                }
            )
        project = None

    for raw in lines:
        m = _BGI_STEP_TIME_RE.match(raw)
        if m:
            last_time = m.group(1)
            # 头行级别槽带 [ERR]/[FTL] 且在某个 BGI 项目内 → 下一条消息行即异常原因
            pending_err = project is not None and any(
                h in raw for h in _BGI_STEP_HEADER_ERR_HINTS
            )
            continue
        line = raw.strip()
        if not line:
            continue

        if pending_err:
            pending_err = False
            if project is not None:
                project["issue"].append(line)
            continue

        if line.startswith(_MAS_STEP_PREFIX):
            if project is not None:
                project_has_mas = True
            marker, _, rest = line.partition(":")
            parts = rest.strip().split(" ", 2)
            uid = parts[0].strip() if parts else ""
            name = parts[1].strip() if len(parts) > 1 else ""
            detail = parts[2].strip() if len(parts) > 2 else ""

            if marker == "MAS_STEP_BEGIN":
                if cur is not None:  # 上一步没等到 DONE 就被新步顶掉 → 记为未完成
                    finalize(False)
                start(uid, name)
            elif marker == "MAS_STEP_DONE":
                if cur is not None:
                    finalize(True)
                    cur = None
            elif marker == "MAS_STEP_FAIL":
                if cur is None:
                    start(uid, name)
                cur["issue"].append(detail or "执行失败")
                finalize(False)
                cur = None
            elif marker == "MAS_STEP_RESIN_END":
                # 树脂耗尽是开了「树脂耗尽模式」后的预期停止条件，按正常收尾处理（与 main.js 一致）
                if cur is None:
                    start(uid, name)
                cur["issue"].append(detail or "树脂耗尽，任务结束")
                finalize(True)
                cur = None
            elif marker == "MAS_STEP_MISSING_CONFIG":
                # 必填项缺失：该步根本没进 BGI（标记打在 BEGIN 之前），单独列一行说明原因
                start(uid, name)
                cur["issue"].append(detail or "缺少必填配置")
                finalize(False)
                cur = None
            continue

        pm = _BGI_PROJECT_BEGIN_RE.match(line)
        if pm:
            if project is not None:  # 上一个项目没等到收尾行就被顶掉 → 未完成
                close_project(False)
            project = {
                "task": pm.group("name"),
                "start": last_time,
                "end": "",
                "ok": True,
                "issue": [],
            }
            project_has_mas = False
            continue
        if _BGI_PROJECT_END_RE.match(line):
            close_project(True)
            continue

    if cur is not None:  # 整条结束仍停在某一步（如 MAS_PLAN_FAIL 中断）→ 该步未完成
        finalize(False)
    if project is not None:  # 自定义项还没走到收尾行（进程被杀/中断）→ 该步未完成
        close_project(False)

    if not steps:
        return None
    total = len(steps)
    for order, step in enumerate(steps, 1):
        step["index"] = order
        step["total"] = total
        step.pop("issue", None)
    return steps


def count_failed_custom_items(log: str) -> int:
    """统计直连 BGI 配置组的自定义项（配置组 / 脚本 / 路径 / 录制）里失败的项目数。

    执行层收尾要用它把这类失败一并算进「部分失败」：BGI 的判定是**组级**的，单个项目
    失败不会让配置组失败（照样走到「执行结束」），也不打 ``MAS_PLAN_DONE_WITH_FAILURES``，
    只认 MAS 的汇总标记会漏（2026-09-19 实机：脚本项失败仍报「成功」）。
    执行层本体（内部带 ``MAS_STEP_*`` 的项目）已被解析器剔除，不会与 MAS 步失败数重复计数。
    """
    return sum(
        1
        for step in parse_execution_layer_report(log) or []
        if step.get("bgi_project") and not step["ok"]
    )
