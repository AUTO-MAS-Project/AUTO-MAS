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

"""M9A 特调：MaaFW 引擎之上唯一的运行期专项逻辑，以及"这是不是 M9A 项目"的判据。

「启动游戏」（entry ``StartUp``）、「切换账号」（entry ``SwitchAccount``）、「关闭游戏」
（entry ``Close1999``）由 MAS 全权控制（规则见 ``managed.py``）。运行前先把勾选列表里这三类
全部剔掉，再按固定顺序补：启动放队首；脚本资源为官服、账号非空且没开「MAS 登录」时切号紧跟启动，
账号填进它唯一的 input 选项；关闭放队尾。用户排的顺序不影响这三项。队列里有多个有效切号的用户拒绝运行。

``Run.LoginMode`` 为 ``Mas`` 时（B 服登录由 MAS 完成，见 ``login.py``）：不再补「切换账号」，
``Info.Account`` 是 MAS 登录要选中的哔哩哔哩昵称；启动 / 关闭照常补，登录完成后 ``StartUp``
负责从标题页进游戏，随后跑用户任务。

按 entry 而不是按任务名找：任务名会随 M9A 的版本与语言变，entry 是它的 pipeline 入口，稳定。

另实现了引擎的三个可选钩子：``sanitize_task_snapshot``（写账号任务快照前按同一规则整理）、
``ensure_game_updated``（脚本开了游戏更新时，模拟器启动后比对官服客户端版本，落后就提示或
下载安装，``game_update.py``）与 ``retype_notice_lines``（按项目换成 / 换出 M9A 时通知里说明
启停与切号）；并给了引擎的五项可选声明：``abort_round_entries``（切号失败结束本轮）、
``nonfatal_entries``（关闭游戏失败不算失败）、
``skip_on_retry_entries``（完成过的重试不补跑）、``unselectable_entries``（五个小游戏不可选、
运行时跳过）、``no_default_fallback_inputs``（自定义兑换码没填不回落「占位」），契约都在 MaaFW ``tools/embedded/flavor.py`` 的模块说明里。除这些之外 M9A 与
通用 MaaFW 没有运行期差别。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.task.M9A.managed import (
    CLOSE_ENTRY,
    LOGIN_MODE_MAS,
    MANAGED_ENTRIES,
    OFFICIAL_RESOURCE_NAME,
    STARTUP_ENTRY,
    SWITCH_ACCOUNT_ENTRY,
    M9ASplitRequiredError,
    effective_switch_accounts,
    first_text_value,
    settle_snapshot,
    settle_user_info,
    split_message,
    supports_account_switch,
)
from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    resolve_task_instance_name,
)

if TYPE_CHECKING:
    from app.utils import game_update as _utils_game_update

TYPE_KEY = "M9A"

# 旧版 M9A 专项按名字记任务；名字随版本变过（「每日心相」→「每日心相（意志解析）」），
# 迁移时按 entry 反查。这张表只服务迁移与无 interface 降级，运行期不用。
LEGACY_ENTRY_ALIASES: dict[str, str] = {
    "每日心相（意志解析）": "Psychube",
    "每日心相": "Psychube",
    "自动深眠": "Limbo",
    "自动醒梦": "Lucidscape",
    "启动游戏": STARTUP_ENTRY,
    "关闭游戏": CLOSE_ENTRY,
    "切换账号": SWITCH_ACCOUNT_ENTRY,
}
# 没有 interface 可查时（迁移的降级路径）按 v4.9 的名字兜底。
FALLBACK_TASK_NAMES: dict[str, str] = {
    "Psychube": "每日心相（意志解析）",
    "Limbo": "自动深眠",
    "Lucidscape": "自动醒梦",
    STARTUP_ENTRY: "启动游戏",
    CLOSE_ENTRY: "关闭游戏",
    SWITCH_ACCOUNT_ENTRY: "切换账号",
}

_GITHUB_M9A_RE = re.compile(r"(^|[/:])MAA1999/M9A(\.git)?/?$", re.IGNORECASE)


def task_name_for_entry(interface_model: MaaFWInterface, entry: str) -> str | None:
    """interface 里第一个 ``entry`` 等于给定值的任务名；找不到返回 None。"""

    for task in interface_model.task:
        if str(task.entry or "") == entry:
            return task.name
    return None


def is_m9a_project(interface_model: MaaFWInterface | dict[str, Any]) -> bool:
    """三条判据任一命中：``mirrorchyan_rid == M9A``、``github`` 指向 MAA1999/M9A、``name == m9a``。"""

    if isinstance(interface_model, dict):
        rid = interface_model.get("mirrorchyan_rid")
        github = interface_model.get("github")
        name = interface_model.get("name")
    else:
        rid = getattr(interface_model, "mirrorchyan_rid", None)
        github = getattr(interface_model, "github", None)
        name = getattr(interface_model, "name", None)
    if str(rid or "").strip().casefold() == "m9a":
        return True
    if _GITHUB_M9A_RE.search(str(github or "").strip()):
        return True
    return str(name or "").strip().casefold() == "m9a"


class M9AFlavor:
    """满足 ``MaaFWFlavor`` 协议的 M9A 特调对象。"""

    type_key = TYPE_KEY
    # 切换账号失败或超时就结束本轮、照常重试：切号没成功，后面的任务会跑在错的账号上。
    # 不列 StartUp：它失败不代表游戏用不了（上游一直只声明切号），本轮照旧按普通失败继续。
    abort_round_entries = {SWITCH_ACCOUNT_ENTRY: "切换账号失败"}
    # 关闭游戏失败、超时只记一行，不算本轮失败：收尾时 MAS 会关闭模拟器，重跑一整轮没有意义
    nonfatal_entries = {CLOSE_ENTRY: "MAS 收尾时会关闭游戏/模拟器，不影响本轮结果"}
    # 本次运行里完成过的任务重试时不再补跑（v4.11.3 全部非受管任务）：重跑已领完、已刷完的
    # 只是白等几分钟。逐个写出而不是「除受管三项外全部」，M9A 以后新增的任务默认照旧补跑，
    # 确认重跑无意义再加进来。受管三项每次尝试都要重做，不列。
    skip_on_retry_entries = frozenset(
        {
            "Wilderness",
            "Awards",
            "Bank",
            "redeem_code",
            "Character",
            "Psychube",
            "switch_menu",
            "WarehouseInventory",
            "Limbo",
            "Lucidscape",
            "TheAlarm",
            "Colosseum",
            "UTTU",
            "SeriesOfDusks",
            "TheSyndromeOfSilence",
            "8bit",
            "CritterCrash",
            "MusesBoxStartParty",
            "PreStormProtocolStart",
            "CompleteInduction",
            "BalancedFarming",
            "Combat",
            "CombatActivity",
            "AutoPromotion",
            "SSReopen",
            "CharUpgrade",
        }
    )
    # 五个小游戏：M9A 资源里没有导航，要用户先手动停在对应页面才能跑，MAS 无人值守放进队列只会
    # 出错。账号页不让选，运行时剔掉（优先于上面的声明，skip_on_retry_entries 里留着无妨）。
    unselectable_entries = dict.fromkeys(
        (
            "8bit",
            "CritterCrash",
            "MusesBoxStartParty",
            "PreStormProtocolStart",
            "CompleteInduction",
        ),
        "需手动进入对应页面（M9A 没有自动导航）",
    )

    # 自定义兑换码没填时不回落 default：它的 default 是字面量「占位」，旧版迁移专门把预填的它清成
    # 空串（migration._clean_input_values）；交给 agent 的话，交不过去的码会中断整个兑换，后面
    # 真正的兑换码也不交。其余 input 的 default 是能跑的真值，照常回落
    no_default_fallback_inputs = frozenset({("自定义兑换码", "兑换码")})

    def matches_project(self, interface_model: MaaFWInterface) -> bool:
        return is_m9a_project(interface_model)

    def retype_notice_lines(self, *, entering: bool, has_users: bool) -> list[str]:
        """脚本按项目换成 / 换出 M9A 时系统通知里的说明（引擎的可选钩子）。"""

        if entering:
            lines = [
                "运行时会自动补上启动 / 关闭游戏；官服用户的「账号」用于自动切换账号"
            ]
            if has_users:
                lines.append("已有账号的「账号」栏如果原来只是备注，请改掉或清空")
            return lines
        return ["不再自动补启动 / 关闭游戏、不再自动切换账号"] if has_users else []

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
        def log(message: str) -> None:
            if send_log is not None:
                send_log(message)

        entry_of, account_of = _entry_and_account_readers(interface_model)
        login_mode = _login_mode(script_config)
        supported = supports_account_switch(resource_name, login_mode=login_mode)
        queued_accounts = effective_switch_accounts(
            task_ids, task_options, entry_of=entry_of, account_of=account_of
        )
        if supported and len(queued_accounts) >= 2:
            # 一个账号对应一个账号：MAS 没法替用户决定这一轮切到哪个号，整个账号不跑
            message = split_message(queued_accounts)
            log(f"[M9A] {message}")
            raise M9ASplitRequiredError(message)

        # 三类受管任务一律剔掉，下面按固定顺序补；它们的选项也不再下发
        ids = [
            task_id for task_id in task_ids if entry_of(task_id) not in MANAGED_ENTRIES
        ]
        options = {
            key: value
            for key, value in task_options.items()
            if entry_of(key) not in MANAGED_ENTRIES
        }
        if len(ids) != len(task_ids):
            log(
                "[M9A] 启动游戏、切换账号、关闭游戏由 MAS 控制，"
                "队列里的这几项已忽略并按固定顺序重新加入"
            )

        if not ids:
            # 除受管任务外一个都没勾：不补首尾，免得白白启动再关闭一次游戏；空队列交给引擎原有处理。
            return ids, options

        added: list[str] = []
        startup = None
        if not self.manages_game_startup(script_config):
            startup = task_name_for_entry(interface_model, STARTUP_ENTRY)
            if startup is None:
                log(
                    f"[M9A] interface 里没有 entry 为 {STARTUP_ENTRY} 的任务，未自动加入启动游戏"
                )
            else:
                ids.insert(0, startup)
                added.append(startup)

        # 队列里恰好一个有效切号时以它为准，与启动整理的结果一致（整理会把它收进「账号」）
        account = (
            queued_accounts[0]
            if len(queued_accounts) == 1
            else str(_get(user_config, "Info", "Account") or "").strip()
        )
        if account and supported:
            switch = task_name_for_entry(interface_model, SWITCH_ACCOUNT_ENTRY)
            if switch is None:
                log(
                    f"[M9A] interface 里没有 entry 为 {SWITCH_ACCOUNT_ENTRY} 的任务，"
                    "未自动加入切换账号"
                )
            else:
                # 紧跟在「启动游戏」后面；interface 里没有启动任务时放队首
                ids.insert(1 if startup is not None else 0, switch)
                added.append(switch)
                account_option = _account_option(interface_model, switch, account)
                if account_option is not None:
                    options[switch] = account_option
                else:
                    log("[M9A] 切换账号任务没有 input 类型的账号选项，账号未能填入")
        elif account:
            if login_mode == LOGIN_MODE_MAS:
                log(
                    "[M9A] 已开启 MAS 登录：Info.Account 是 MAS 登录要选中的账号昵称，"
                    "不再加入切换账号"
                )
            else:
                log(
                    f"[M9A] 资源不是{OFFICIAL_RESOURCE_NAME}，Info.Account 只作备注，不自动切换账号"
                )

        close = task_name_for_entry(interface_model, CLOSE_ENTRY)
        if close is None:
            log(
                f"[M9A] interface 里没有 entry 为 {CLOSE_ENTRY} 的任务，未自动加入关闭游戏"
            )
        else:
            ids.append(close)
            added.append(close)
        if added:
            log(f"[M9A] 已自动加入：{' / '.join(added)}")
        return ids, options

    def sanitize_task_snapshot(
        self,
        interface_model: MaaFWInterface,
        snapshot: dict[str, Any],
        *,
        script_config: Any,
        resource_name: str | None,
        user_info: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """引擎的可选钩子：写 ``Task.TaskSnapshot`` 前按 ``managed.py`` 的规则整理。

        返回（整理后的快照, 要写进 ``Info`` 的字段）。多个有效切号的保留态原样放行，
        备注只由启动整理写，这里不写（账号页上有常驻提示）。
        """

        entry_of, account_of = _entry_and_account_readers(interface_model)
        settlement = settle_snapshot(
            snapshot,
            entry_of=entry_of,
            account_of=account_of,
            supports_switch=supports_account_switch(
                resource_name, login_mode=_login_mode(script_config)
            ),
        )
        change = settle_user_info(
            settlement,
            account=str(user_info.get("Account") or ""),
            notes=str(user_info.get("Notes") or ""),
            note_split=False,
        )
        return (
            settlement.snapshot if settlement.changed else snapshot,
            change.updates(),
        )

    async def ensure_logged_in(
        self,
        *,
        script_config: Any,
        user_config: Any,
        resource_name: str | None,
        package_name: str | None,
        adb_path: str | None,
        adb_address: str,
        progress: Callable[[str], Awaitable[None]] | None,
        host_adb: Any = None,
    ) -> str:
        """引擎的可选运行前登录钩子：B 服登录由 MAS 完成，契约见 MaaFW 的 ``flavor.py``。"""

        # 按需导入：本包在导入期不拉起 OCR / 图像与 adb 相关模块（迁移也会导入 flavor）
        from .login import ensure_logged_in

        return await ensure_logged_in(
            script_config=script_config,
            user_config=user_config,
            resource_name=resource_name,
            package_name=package_name,
            adb_path=adb_path,
            adb_address=adb_address,
            progress=progress,
            host_adb=host_adb,
        )

    def manages_game_startup(self, script_config: Any) -> bool:
        return _login_mode(script_config) == LOGIN_MODE_MAS

    async def ensure_game_updated(
        self,
        *,
        script_config: Any,
        resource_name: str | None,
        package_name: str,
        adb_path: str | None,
        adb_address: str,
        if_auto_install: bool,
        progress: Callable[[str], Awaitable[None]] | None,
    ) -> _utils_game_update.GameUpdateResult:
        """引擎的可选游戏更新钩子：只查官服，契约见 MaaFW 的 ``flavor.py`` 模块说明。"""

        # 按需导入：本包在导入期不拉起网络与 adb 相关模块（迁移也会导入 flavor）
        from .game_update import ensure_game_updated

        del script_config  # 资源名由引擎按脚本配置解析后传入
        return await ensure_game_updated(
            adb_path=Path(adb_path) if adb_path else None,
            adb_address=adb_address,
            resource_name=resource_name,
            package_name=package_name,
            official_resource_name=OFFICIAL_RESOURCE_NAME,
            apk_dir=Path.cwd() / "data/GameApk",
            if_auto_install=if_auto_install,
            progress=progress,
        )


def _account_field(
    interface_model: MaaFWInterface, task_name: str
) -> tuple[str, str] | None:
    """切换账号任务上第一个 input 型选项与它的第一个输入字段：``(选项名, 字段名)``。"""

    task = next((item for item in interface_model.task if item.name == task_name), None)
    if task is None:
        return None
    option_book = interface_model.option or {}
    for option_name in task.option or []:
        option = option_book.get(option_name)
        if option is None or getattr(option, "type", None) != "input":
            continue
        inputs = getattr(option, "inputs", None) or []
        if not inputs:
            continue
        return option_name, getattr(inputs[0], "name", None) or "账号"
    return None


def _account_option(
    interface_model: MaaFWInterface, task_name: str, account: str
) -> dict[str, Any] | None:
    """切换账号任务的账号选项值：``{选项名: {第一个输入字段: 账号}}``。"""

    found = _account_field(interface_model, task_name)
    if found is None:
        return None
    option_name, field_name = found
    return {option_name: {field_name: account}}


def _entry_and_account_readers(
    interface_model: MaaFWInterface,
) -> tuple[Callable[[str], str], Callable[[str, Any], str]]:
    """按 interface 读实例 entry 与切号目标账号的两个函数（``managed.py`` 的规则要用）。"""

    task_by_name = {task.name: task for task in interface_model.task}
    field_cache: dict[str, tuple[str, str] | None] = {}

    def name_of(task_id: str) -> str:
        return resolve_task_instance_name(str(task_id), task_by_name)

    def entry_of(task_id: str) -> str:
        task = task_by_name.get(name_of(task_id))
        return str(task.entry or "") if task is not None else ""

    def account_of(task_id: str, options: Any) -> str:
        if not isinstance(options, dict):
            return ""
        name = name_of(task_id)
        if name not in field_cache:
            field_cache[name] = _account_field(interface_model, name)
        found = field_cache[name]
        if found is not None:
            value = options.get(found[0])
            if isinstance(value, dict):
                return str(value.get(found[1]) or "").strip()
            return first_text_value(value)
        return first_text_value(options)

    return entry_of, account_of


def _get(config: Any, group: str, name: str) -> Any:
    try:
        return getattr(getattr(config, group), name)
    except Exception:  # noqa: BLE001 - 假配置对象缺项时按空处理
        return None


def _login_mode(script_config: Any) -> str:
    """``Run.LoginMode``；假配置对象缺项时按项目自登录（``Project``）处理。"""

    return str(_get(script_config, "Run", "LoginMode") or "").strip()


FLAVOR = M9AFlavor()

__all__ = [
    "CLOSE_ENTRY",
    "FALLBACK_TASK_NAMES",
    "FLAVOR",
    "LEGACY_ENTRY_ALIASES",
    "M9AFlavor",
    "MANAGED_ENTRIES",
    "OFFICIAL_RESOURCE_NAME",
    "STARTUP_ENTRY",
    "SWITCH_ACCOUNT_ENTRY",
    "TYPE_KEY",
    "is_m9a_project",
    "task_name_for_entry",
]
