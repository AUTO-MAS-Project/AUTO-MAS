#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MSS（MaaStellaSora / 星塔旅人）特调：运行前的「活动 → 日常 → 周常」队列装饰。

运行前在用户勾选的任务实例列表上做三件事，其余与通用 MaaFW 没有任何运行期差别：

1. 活动：队列里有「活动快速战斗」（entry ``活动快速战斗_入口``）时查一次活动排期
   （``app/tools/stella_official.py``，只认会开活动关的「版本活动」）。有进行中的活动
   就把它挪到悬赏试炼前面先打；确实没有活动就把它摘掉；取不到数据时按队列原样跑——
   真在活动期却摘掉，整轮就漏打了活动。
2. 日常：用户选了 MSS 计划表（``Info.PlanMode`` 不是 ``Fixed``）时，按当天槽位改写
   「悬赏试炼快速战斗」（entry ``战斗_入口``）的关卡、是否跳过难度选择与难度、是否消耗
   所有干劲与作战次数；队列里没有这个任务就补上。``Fixed`` 时一个选项都不动。
3. 周常：「新版爬塔」（entry ``星塔_入口_agent``）挪到队尾——爬塔不消耗干劲，上游爬塔
   偶发卡住，放最后不拖累前面的任务。每周只跑一次用 MaaFW 通用的「每周仅一次」。
4. 个人版的「灾变防线」（entry ``灾变防线_入口``，只在个人版项目里有）：一期只打得到一次，
   打没打过由 MAS 自己按「这一期开没开过」记账，见 ``_arrange_defense``。这一段只在设置页把
   个人版开关打开、且项目确实是个人版时生效，普通版 MSS 一行都不走。

按 entry 找任务、按 interface 里真实的选项名与 case 名写值（取自 MaaStellaSora v1.4.4 的
``resource/tasks/{activity,fight,climb_tower}.json``）；找不到就写一行用户日志跳过那一项。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    resolve_task_instance_name,
)

TYPE_KEY = "MSS"
ACTIVITY_ENTRY = "活动快速战斗_入口"
TRIBULATION_ENTRY = "战斗_入口"
CLIMB_ENTRY = "星塔_入口_agent"
## 个人版新增的灾变防线（一期只能打一次，见 _arrange_defense）
DEFENSE_ENTRY = "灾变防线_入口"
DEFENSE_ACTIVITY_NAME = "灾变防线"
## 一期里最多在几天编排过它而没跑成，超过就放弃这一期，等下期公告换了自动重来
DEFENSE_MAX_FAILED_DAYS = 3

## 悬赏试炼的五个选项（后两对是 switch 的 No 分支带出来的子选项，值与父选项平铺在一起）
OPTION_TRIBULATION_STAGE = "悬赏试炼关卡"
OPTION_SKIP_DIFFICULTY = "悬赏试炼跳过难度选择"
OPTION_DIFFICULTY = "选择悬赏试炼难度"
INPUT_DIFFICULTY = "难度"
OPTION_CONSUME_ALL = "悬赏试炼消耗所有干劲"
OPTION_FIGHT_TIMES = "自定义快速作战次数"
INPUT_FIGHT_TIMES = "次数"
SWITCH_ON = "Yes"
SWITCH_OFF = "No"

PLAN_MODE_FIXED = "Fixed"

## 项目唯一标识符前缀：官方版是 MaaStellaSora，衍生版在其后加后缀（个人版 MaaStellaSora-Personal）。
## github 仓库名按同一口径认。
_MSS_PROJECT_NAME = "maastellasora"


def task_name_for_entry(interface_model: MaaFWInterface, entry: str) -> str | None:
    """interface 里第一个 ``entry`` 等于给定值的任务名；找不到返回 None。"""

    for task in interface_model.task:
        if str(task.entry or "") == entry:
            return task.name
    return None


def github_repo_name(github: str) -> str:
    """``github`` 里的仓库名；给不出 ``owner/repo`` 这种两段路径时返回空串。

    认这些写法：``https://github.com/owner/repo``、``https://github.com/owner/repo.git``、
    ``git@github.com:owner/repo.git``、``owner/repo``。
    只给一段的（如 ``https://github.com/MaaStellaSora`` 这种组织主页）返回空串——
    它不是一个仓库，按仓库名认领会把整个组织名下的项目都算进来。
    """

    cleaned = github.strip()
    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
    cleaned = cleaned.replace(":", "/")
    cleaned = cleaned.strip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    parts = [part for part in cleaned.split("/") if part]
    if parts and ("." in parts[0] or "@" in parts[0]):
        ## 首段是主机名（github.com / git@github.com），去掉后剩下的才是路径
        parts = parts[1:]
    if len(parts) < 2:
        return ""
    return parts[-1]


def _is_mss_project_key(value: str) -> bool:
    """项目标识符是否属于 MSS：等于 ``MaaStellaSora``，或以 ``MaaStellaSora-`` 开头。

    后缀必须是连字符分隔的——``MaaStellaSora-Personal`` ✓、``MaaStellaSoraX`` ✗，
    免得把碰巧同前缀的无关项目认成衍生版。``github`` 与 ``name`` 走同一口径。
    """

    normalized = value.strip().casefold()
    return normalized == _MSS_PROJECT_NAME or normalized.startswith(
        f"{_MSS_PROJECT_NAME}-"
    )


def is_mss_project(interface_model: MaaFWInterface | dict[str, Any]) -> bool:
    """官方版与其衍生版（个人版）都认领，三条判据任一命中即可：

    - ``mirrorchyan_rid == SSAH``：官方版在 MirrorChyan 的分发标识；
    - ``github`` 仓库名（``owner/repo`` 里的 repo）命中同一口径：官方
      ``MaaStellaSora/MaaStellaSora``、个人版 ``beichen24a1/MaaStellaSora-Personal`` 都命中；
    - ``name``（PI 的项目唯一标识符）命中同一口径。

    后两条共用 ``_is_mss_project_key``：**等于 ``MaaStellaSora`` 或以 ``MaaStellaSora-`` 开头**。
    只给 ``https://github.com/MaaStellaSora`` 这种组织主页时仓库名取不到，不会认领。

    认领只决定**脚本类型**（都用 ``MSSConfig`` 与同一套运行期装饰）；更新谱系仍按
    ``mirrorchyan_rid`` / ``github`` / ``name`` 各自分开，衍生版不会被官方版的更新包覆盖。
    """

    if isinstance(interface_model, dict):
        rid = interface_model.get("mirrorchyan_rid")
        github = interface_model.get("github")
        name = interface_model.get("name")
    else:
        rid = getattr(interface_model, "mirrorchyan_rid", None)
        github = getattr(interface_model, "github", None)
        name = getattr(interface_model, "name", None)
    if str(rid or "").strip().casefold() == "ssah":
        return True
    if _is_mss_project_key(github_repo_name(str(github or ""))):
        return True
    return _is_mss_project_key(str(name or ""))


def activity_running() -> bool | None:
    """当前有没有进行中的版本活动：有 True、确实没有 False、取不到数据 None。

    钩子在建运行计划的工作线程里被调，那里没有事件循环，自己起一个跑完就收；
    万一在事件循环线程里被调，拿不到结果，按「说不准」处理。
    """

    from app.tools.stella_official import has_running_official_activity

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(has_running_official_activity())
    return None


def defense_period() -> str | None:
    """当前这一期「灾变防线」的开始时刻；取不到返回 None。

    常驻活动随版本轮换，每期重发一篇同名公告，官网那一篇的开始时刻就是「期」的标识——
    上游更新不严格按月来，自然月做不了这件事。调用口径与 :func:`activity_running`
    一样：建计划在工作线程里跑，自己起一个事件循环收结果。
    """

    from app.tools.stella_official import permanent_activity_window

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(permanent_activity_window(DEFENSE_ACTIVITY_NAME))
    return None


def personal_mss_enabled() -> bool:
    """设置页那个个人版开关（``Function.IfPersonalMss``）有没有打开。"""

    from app.core.config import Config

    try:
        return bool(Config.get("Function", "IfPersonalMss"))
    except AttributeError:
        ## 配置对象里还没有这一项（旧配置遇上热更新）：当作没开，不动队列
        return False


class MSSFlavor:
    """满足 ``MaaFWFlavor`` 协议的 MSS 特调对象。"""

    type_key = TYPE_KEY

    def __init__(
        self,
        *,
        activity_probe: Callable[[], bool | None] = activity_running,
        defense_period_probe: Callable[[], str | None] = defense_period,
        personal_mss_probe: Callable[[], bool] = personal_mss_enabled,
    ) -> None:
        self._activity_probe = activity_probe
        self._defense_period_probe = defense_period_probe
        self._personal_mss_probe = personal_mss_probe

    def matches_project(self, interface_model: MaaFWInterface) -> bool:
        return is_mss_project(interface_model)

    def decorate_selection(
        self,
        interface_model: MaaFWInterface,
        task_ids: list[str],
        task_options: dict[str, Any],
        *,
        script_config: Any,
        user_config: Any,
        resource_name: str | None,
        send_log: Callable[[str], None] | None,
    ) -> tuple[list[str], dict[str, Any]]:
        del script_config, resource_name  # MSS 的装饰只看用户配置与活动排期

        def log(message: str) -> None:
            if send_log is not None:
                send_log(message)

        valid_names = {task.name for task in interface_model.task}

        def name_of(task_id: str) -> str:
            return resolve_task_instance_name(task_id, valid_names)

        ids = list(task_ids)
        options = dict(task_options)

        activity = task_name_for_entry(interface_model, ACTIVITY_ENTRY)
        tribulation = task_name_for_entry(interface_model, TRIBULATION_ENTRY)
        climb = task_name_for_entry(interface_model, CLIMB_ENTRY)
        ## 个人版才有这个任务；开关没开就当作没有，后面一次都不提它
        defense = (
            task_name_for_entry(interface_model, DEFENSE_ENTRY)
            if self._personal_mss_probe()
            else None
        )

        ## 一个任务都没勾、也没选计划表：手上没有任何可执行任务，交给引擎按原有语义报错。
        ## 选了计划表就不算空队列——下面 _apply_plan 会把悬赏试炼补上，和用户页那句
        ## 「队列里没有它时会自动加入」保持一致（这条以前被空队列提前返回挡住了）。
        ## 个人版开着且有灾变防线时同理：队列可以是空的，它自己会补进来。
        ## 顺序是「活动 → 日常 → 周常」：先补好悬赏试炼，活动才有锚点插在它前面；
        ## 爬塔与灾变防线最后归位。
        plan_key = _current_plan_key(user_config, log)
        if not ids and plan_key is None and defense is None:
            return list(ids), dict(options)

        if plan_key is not None:
            ids, options = _apply_plan(
                interface_model, ids, options, tribulation, plan_key, name_of, log
            )

        ## 「活动优先」开着时，队列里没加活动任务也补一个——但只有**确认在活动期**才补：
        ## 取不到活动数据时乱加会让这一轮多跑一个本来不该跑的任务。
        if (
            activity is not None
            and not any(name_of(i) == activity for i in ids)
            and _get(user_config, "Info", "IfActivityFirst") is not False
            and self._activity_probe() is True
        ):
            ids = _insert_before_climb(ids, activity, interface_model, name_of)
            moved = _move_before(ids, activity, tribulation, name_of)
            ids = moved
            log(f"[MSS] 活动进行中，已自动加入「{activity}」并排到最前")

        if activity is not None and any(name_of(i) == activity for i in ids):
            running = self._activity_probe()
            if running is False:
                remaining = [i for i in ids if name_of(i) != activity]
                if remaining:
                    ids = remaining
                    log(f"[MSS] 当前没有进行中的活动，本轮跳过「{activity}」")
                else:
                    ## 队列里只有活动任务：摘空后引擎会把这一轮判成「无法构建运行计划」的异常，
                    ## 比照活动数据取不到的处理，按队列原样执行。
                    log(
                        f"[MSS] 当前没有进行中的活动，但队列里只有「{activity}」，按队列原样执行"
                    )
            elif running is None:
                log(f"[MSS] 取不到星塔旅人活动数据，「{activity}」按队列原样执行")
            else:
                moved = _move_before(ids, activity, tribulation, name_of)
                if moved != ids:
                    ids = moved
                    log(f"[MSS] 活动进行中，「{activity}」已挪到「{tribulation}」之前")
                else:
                    log(f"[MSS] 活动进行中，「{activity}」按队列顺序执行")

        ## 个人版的灾变防线：一期只打得到一次，靠 MAS 自己记账，放在爬塔归位之前
        ## （它会插在爬塔前面，先归位再插位置才对得上）。
        if defense is not None:
            ids = _arrange_defense(
                ids,
                interface_model,
                user_config,
                defense,
                self._defense_period_probe,
                name_of,
                log,
            )

        if climb is not None and any(name_of(i) == climb for i in ids):
            reordered = [i for i in ids if name_of(i) != climb] + [
                i for i in ids if name_of(i) == climb
            ]
            if reordered != ids:
                ids = reordered
                log(f"[MSS] 「{climb}」已挪到队尾")

        return ids, options


def _move_before(
    ids: list[str],
    target: str,
    anchor: str | None,
    name_of: Callable[[str], str],
) -> list[str]:
    """把 ``target`` 的所有实例挪到 ``anchor`` 第一次出现之前；锚点不在队列里就不动。"""

    if anchor is None:
        return ids
    anchor_index = next((n for n, i in enumerate(ids) if name_of(i) == anchor), None)
    if anchor_index is None:
        return ids
    moving = [i for i in ids if name_of(i) == target]
    rest = [i for i in ids if name_of(i) != target]
    position = next(n for n, i in enumerate(rest) if name_of(i) == anchor)
    return [*rest[:position], *moving, *rest[position:]]


def _current_plan_key(
    user_config: Any, log: Callable[[str], None]
) -> dict[str, Any] | None:
    """用户引用的 MSS 计划表今天那一格；``Fixed`` 或取不到时返回 None（不改悬赏试炼）。"""

    mode = str(_get(user_config, "Info", "PlanMode") or PLAN_MODE_FIXED)
    if mode == PLAN_MODE_FIXED:
        return None
    try:
        plan = type(user_config).related_config["PlanConfig"][uuid.UUID(mode)]
        key = plan.get_current_key()
    except Exception as exc:  # noqa: BLE001 - 计划表被删或类型不对：按固定处理
        log(f"[MSS] 引用的计划表不可用，本轮不改悬赏试炼：{exc}")
        return None
    if not isinstance(key, dict) or not str(key.get("TribulationStage") or ""):
        return None
    return key


def _apply_plan(
    interface_model: MaaFWInterface,
    ids: list[str],
    options: dict[str, Any],
    tribulation: str | None,
    plan_key: dict[str, Any],
    name_of: Callable[[str], str],
    log: Callable[[str], None],
) -> tuple[list[str], dict[str, Any]]:
    """按计划表当天那一格改写悬赏试炼的选项；队列里没有这个任务就补在爬塔之前。"""

    if tribulation is None:
        log(f"[MSS] interface 里没有 entry 为 {TRIBULATION_ENTRY} 的任务，计划表未生效")
        return ids, options

    option_book = interface_model.option or {}
    stage = str(plan_key.get("TribulationStage"))
    stage_option = option_book.get(OPTION_TRIBULATION_STAGE)
    stage_cases = {case.name for case in (getattr(stage_option, "cases", None) or [])}
    if stage not in stage_cases:
        log(
            f"[MSS] 悬赏试炼没有「{stage}」这个关卡（项目可能改了名），计划表本轮未生效"
        )
        return ids, options

    targets = [i for i in ids if name_of(i) == tribulation]
    if not targets:
        targets = [tribulation]
        ids = _insert_before_climb(ids, tribulation, interface_model, name_of)
        log(f"[MSS] 计划表已选，自动加入「{tribulation}」")
    else:
        ## 队列里手动加了多个同任务实例时只改第一个：剩下的留给用户自己配，
        ## 这样「一个按计划表刷、一个固定刷别的关」还能共存
        targets = targets[:1]

    values: dict[str, Any] = {
        OPTION_TRIBULATION_STAGE: stage,
        OPTION_SKIP_DIFFICULTY: SWITCH_ON
        if plan_key.get("SkipDifficulty")
        else SWITCH_OFF,
        OPTION_DIFFICULTY: {INPUT_DIFFICULTY: str(plan_key.get("Difficulty") or 1)},
        OPTION_CONSUME_ALL: SWITCH_ON
        if plan_key.get("ConsumeAllEnergy")
        else SWITCH_OFF,
        OPTION_FIGHT_TIMES: {INPUT_FIGHT_TIMES: str(plan_key.get("FightTimes") or 1)},
    }
    missing = [name for name in values if name not in option_book]
    if missing:
        log(f"[MSS] interface 里缺少选项 {' / '.join(missing)}，这几项按队列原样")
    patch = {name: value for name, value in values.items() if name in option_book}
    for task_id in targets:
        options[task_id] = {**(options.get(task_id) or {}), **patch}
    log(f"[MSS] 按计划表设置悬赏试炼：{stage}")
    return ids, options


def _arrange_defense(
    ids: list[str],
    interface_model: MaaFWInterface,
    user_config: Any,
    defense: str,
    period_probe: Callable[[], str | None],
    name_of: Callable[[str], str],
    log: Callable[[str], None],
) -> list[str]:
    """按「这一期打没打过」决定个人版灾变防线的去留。

    灾变防线一期只打得到一次，可它是常驻活动，游戏里没有「这期打过没有」这种状态可读：
    脚本在一期已经打完的号上会在纪录管理页挑到一张灰卡（那一页只有一张卡是可选的，
    其余全灰），点下去没反应，最后整条任务判失败。所以「打过」只能由 MAS 自己记。

    期的标识是官网那一篇灾变防线公告的开始时刻（``app/tools/stella_official.py``），
    上游更新不严格按月来，自然月做不了这件事。换期了整份记录作废，新一期从零开始。

    记账放在 ``Data.PersonalMssDefense``：

    - ``armed``：上一次建计划时把它编排进队列了，还欠一个结果；同时记下那一刻看到的
      ``LastProxyDate`` / ``ProxyTimes`` / ``LastProxyStatus``（``seen_*``）。
    - 再建计划时结算：这三个值只要有一个变了，就说明那一轮真的进了 ``run()``，
      这时才看状态——「成功」就是打完了（整轮成功意味着队列里每个任务都成功），
      「失败」就记一笔失败日，同一天只记一次；还在跑 / 被中止 / 状态说不清都不记。
    - 三个值一个都没变，就是那一轮压根没跑到 ``run()``：``check()`` 会在返回 Pass 之前
      因为「今日次数已满」「游戏维护」「控制方式没配好」「架构不符」之类提前退出，
      而 ``decorate_selection`` 是在那之前就调过的，此时 ``LastProxyStatus`` 还停在一个
      跟本轮无关的旧值上。什么都不算，下一轮照常再编排。
    - 失败日攒够 ``DEFENSE_MAX_FAILED_DAYS`` 天就放弃这一期，等下一期公告换了自动重来。
      一期只打一次，攒失败日是为了不让「这一期注定打不成」（比如用户已经在游戏里手打过）
      变成每轮都失败下去。

    队列里已经有它（用户自己勾的）也照记，否则用户手动勾的那次成功永远算不出「打过了」。
    记录写不进去就这一轮不编排：记不住就会每期每轮都发，而脚本在打过的号上必然失败，
    整轮陪葬；宁可漏打一轮。
    """

    period = period_probe()
    if period is None:
        log(f"[MSS] 取不到「{defense}」这一期的开始时间，本轮按队列原样执行")
        return ids

    record = _load_defense_record(user_config)
    if str(record.get("period") or "") != period:
        ## 换期了：上一期那份整个丢掉
        record = {"period": period, "done": False, "armed": False, "failed_days": []}

    settled = False
    if record.get("armed"):
        ## 不能只看 LastProxyStatus：这一轮可能压根没跑到 run()（见函数开头那段），
        ## 那样它停在一个跟本轮无关的旧「成功」上，照着结算会把这一期误判成打过了。
        ## 判据换成「建计划时看到的那三个值有没有变」——真跑过就一定会变：run() 一进门就
        ## _mark_run_started()，它必写 LastProxyStatus=运行中，跨天还会改 LastProxyDate
        ## 并把 ProxyTimes 清零；跑完 final_task 再写成功或失败。
        seen = (
            record.get("seen_date"),
            record.get("seen_times"),
            record.get("seen_status"),
        )
        if all(isinstance(value, str) for value in seen):
            now = (
                _as_text(_get(user_config, "Data", "LastProxyDate")),
                _as_text(_get(user_config, "Data", "ProxyTimes")),
                _as_text(_get(user_config, "Data", "LastProxyStatus")),
            )
            if now != seen:
                record["armed"] = False
                settled = True
                if now[2] == "成功":
                    record["done"] = True
                elif now[2] == "失败":
                    failed_days = [str(day) for day in record.get("failed_days") or []]
                    today = datetime.now().strftime("%Y-%m-%d")
                    if today not in failed_days:
                        failed_days.append(today)
                    record["failed_days"] = failed_days
            ## now == seen：这一轮没进过 run()，什么都不算，下一轮照常再编排

    present = any(name_of(task_id) == defense for task_id in ids)

    if record.get("done"):
        if settled:
            _commit_defense_record(user_config, record, defense, log)
        if present:
            remaining = [i for i in ids if name_of(i) != defense]
            if remaining:
                log(f"[MSS] 本期「{defense}」已完成，本轮跳过")
                return remaining
            log(f"[MSS] 本期「{defense}」已完成，但队列里只有它，按队列原样执行")
        return ids

    failed_days = [str(day) for day in record.get("failed_days") or []]
    if len(failed_days) >= DEFENSE_MAX_FAILED_DAYS:
        if settled:
            _commit_defense_record(user_config, record, defense, log)
        if present:
            remaining = [i for i in ids if name_of(i) != defense]
            if remaining:
                log(
                    f"[MSS] 本期「{defense}」已经 {len(failed_days)} 天没跑成，本轮不再编排，"
                    "等下一期公告换了会自动重来"
                )
                return remaining
        return ids

    injected = False
    if not present:
        ids = _insert_before_climb(ids, defense, interface_model, name_of)
        injected = True
    record["armed"] = True
    ## 记下此刻的运行状态，下一轮拿它比「这一轮到底跑没跑」（见上面的结算段）
    record["seen_date"] = _as_text(_get(user_config, "Data", "LastProxyDate"))
    record["seen_times"] = _as_text(_get(user_config, "Data", "ProxyTimes"))
    record["seen_status"] = _as_text(_get(user_config, "Data", "LastProxyStatus"))
    if _save_defense_record(user_config, record) is not None:
        ## 记不住就别发：脚本在一期已经打过的号上会卡在纪录管理页，整轮陪葬
        if injected:
            ids = [i for i in ids if name_of(i) != defense]
        log(f"[MSS] 「{defense}」的编排记录写入失败，本轮按队列原样执行")
        return ids
    if injected:
        log(f"[MSS] 本期的「{defense}」还没打，已加入队列")
    return ids


def _load_defense_record(user_config: Any) -> dict[str, Any]:
    """读 ``Data.PersonalMssDefense``；形状不对就当空记录。

    只认自己写出去的那几个键与类型。校验是必须的：``failed_days`` 万一被写成字符串，
    ``for day in ...`` 会逐字符遍历、字符数直接顶到放弃阈值，整个这一期就不打了。
    坏形状宁可当空——最多本期多打一次，失败日机制兜得住。
    """

    raw = _get(user_config, "Data", "PersonalMssDefense")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    if not isinstance(raw.get("period"), str) or not raw["period"]:
        return {}
    if not isinstance(raw.get("done"), bool) or not isinstance(raw.get("armed"), bool):
        return {}
    failed_days = raw.get("failed_days")
    if not isinstance(failed_days, list) or not all(
        isinstance(day, str) for day in failed_days
    ):
        return {}
    return dict(raw)


def _as_text(value: Any) -> str:
    """配置项可能给 None 或数字，比较两轮状态前统一成字符串。"""

    return "" if value is None else str(value)


def _save_defense_record(user_config: Any, record: dict[str, Any]) -> Exception | None:
    """写回 ``Data.PersonalMssDefense``；成功返回 None，失败返回那个异常。

    这里在工作线程里跑（``check()`` 经 ``asyncio.to_thread`` 建计划），没有事件循环可 await，
    自己起一个跑完就收。配置写盘失败只影响这一轮，不能让整份运行计划建不出来。
    """

    try:
        asyncio.run(
            user_config.set(
                "Data",
                "PersonalMssDefense",
                json.dumps(record, ensure_ascii=False),
            )
        )
    except Exception as exc:  # noqa: BLE001 - 配置锁了 / 写盘失败都退回「按队列原样」
        return exc
    return None


def _commit_defense_record(
    user_config: Any,
    record: dict[str, Any],
    defense: str,
    log: Callable[[str], None],
) -> None:
    """把结算结果（打完了 / 又失败一天）留住。

    写不进去也不改这一次的判断：``done`` 下一轮靠 ``LastProxyStatus`` 还能推出来，
    失败日会少记一次，都不影响「这一期只打一次」。
    """

    exc = _save_defense_record(user_config, record)
    if exc is not None:
        log(f"[MSS] 「{defense}」的编排记录没写进去，下一轮会重新算一遍：{exc}")


def _insert_before_climb(
    ids: list[str],
    task: str,
    interface_model: MaaFWInterface,
    name_of: Callable[[str], str],
) -> list[str]:
    """把 ``task`` 插在爬塔之前（爬塔是那个会被挪到队尾的任务）；没有爬塔就追加到末尾。"""

    climb = task_name_for_entry(interface_model, CLIMB_ENTRY)
    index = next(
        (n for n, i in enumerate(ids) if climb is not None and name_of(i) == climb),
        len(ids),
    )
    return [*ids[:index], task, *ids[index:]]


def _get(config: Any, group: str, name: str) -> Any:
    try:
        return config.get(group, name)
    except Exception:  # noqa: BLE001 - 假配置对象缺项时按空处理
        return None


FLAVOR = MSSFlavor()

__all__ = [
    "ACTIVITY_ENTRY",
    "CLIMB_ENTRY",
    "DEFENSE_ENTRY",
    "FLAVOR",
    "MSSFlavor",
    "TRIBULATION_ENTRY",
    "TYPE_KEY",
    "activity_running",
    "defense_period",
    "is_mss_project",
    "personal_mss_enabled",
    "task_name_for_entry",
]
