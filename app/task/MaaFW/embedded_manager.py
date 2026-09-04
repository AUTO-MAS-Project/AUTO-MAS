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

"""MaaFW 内置运行任务管理器。

MAS 在自己的 worker 子进程内加载项目的 MaaFramework 直接驱动，不启动项目
自带的 UI 外壳；编排实现在 ``tools/embedded/runner_task.py``。这是
``task_manager`` 对 MaaFW 脚本的唯一分派目标。

``tools/embedded.runner_task`` 会经 runner 包 import ``maa``（导入即打开 DLL），
因此本模块**只在 check() 通过后才延迟导入它**，让不跑 MaaFW 的进程不承担
这个代价。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.task.MaaFW.tools.embedded.update_credentials import (
    AutoUpdateMode,
    MaaFWUpdateCredentials,
    describe_cdk,
    resolve_auto_update_mode,
    resolve_update_credentials,
)
from app.task.MaaFW.tools.notify import push_notification
from app.tools.game_sign_notify import (
    append_task_game_sign_summary,
    finalize_task_game_sign_notification,
)
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH
from app.utils.security import sanitize_log_message

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查，运行期不导入 maa
    from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask

logger = get_logger("MFW 内置运行")

# Store checkout 的 sidecar：存在即说明版本由 Project Store 管理（source hash
# 绑定），原地改文件会破坏这层绑定，第三层要求走「下载 → 导入新版本 → 切换」。
MANAGED_PROJECT_SIDECAR_NAME = ".auto_mas_maafw_project.json"
# CDK 距到期不足这些天时提醒用户续费
CDK_EXPIRY_WARNING_DAYS = 7

_UPDATE_SOURCE_ZH = {"mirrorchyan": "Mirror 酱", "github": "GitHub"}
# 核心包没给 cdk_message 时的兜底文案；正常情况下以核心包的原文为准
# 不再说「改用 GitHub」：下载源是用户选的，CDK 有问题时不会自动换源。
_CDK_STATUS_FALLBACK_ZH = {
    "expired": "Mirror 酱 CDK 已过期",
    "invalid": "Mirror 酱 CDK 无效",
    "quota": "Mirror 酱 CDK 今日下载次数已用尽",
    "mismatched": "Mirror 酱 CDK 类型与该资源不匹配",
    "blocked": "Mirror 酱 CDK 已被封禁",
}

NoticeLevel = Literal["info", "warning"]


def _result_field(result: Any, name: str, *fallbacks: str) -> Any:
    """按契约字段名读更新结果；dataclass 与 dict 都要能取到，缺字段当 None。

    允许给备选名，是为了兼容核心包里同义的旧字段（如 ``current_version`` 之于
    ``previous_version``），不是为了容忍字段缺失。
    """

    for key in (name, *fallbacks):
        value = getattr(result, key, None)
        if value is None and isinstance(result, Mapping):
            value = result.get(key)
        if value is not None:
            return value
    return None


def describe_update_result(
    result: Any, *, now: float | None = None
) -> list[tuple[NoticeLevel, str]]:
    """把核心包的更新结果翻成给用户看的几行话。

    只翻译，不判断要不要阻断——这一层从不阻断运行。返回 ``(级别, 文案)``，
    warning 只给 CDK 异常与即将到期，其余都是 info。
    """

    lines: list[tuple[NoticeLevel, str]] = []
    updated = bool(_result_field(result, "updated"))
    skipped_reason = _result_field(result, "skipped_reason")
    previous_version = _result_field(result, "previous_version", "current_version")
    version_name = _result_field(result, "version_name", "latest_version")
    source = _result_field(result, "source")
    message = _result_field(result, "message")

    if updated:
        source_zh = (
            _UPDATE_SOURCE_ZH.get(str(source).lower(), str(source))
            if source
            else "未知"
        )
        lines.append(
            (
                "info",
                f"MFW 项目已更新 {previous_version or '未知'} → "
                f"{version_name or '未知'}（来源：{source_zh}）",
            )
        )
    elif skipped_reason:
        lines.append(("info", f"MFW 项目更新已跳过：{skipped_reason}"))
    elif message:
        lines.append(("info", f"MFW 项目更新：{message}"))

    cdk_status = str(_result_field(result, "cdk_status") or "").strip().lower()
    cdk_message = str(_result_field(result, "cdk_message") or "").strip()
    if cdk_status and cdk_status not in ("ok", "absent"):
        lines.append(
            (
                "warning",
                cdk_message
                or _CDK_STATUS_FALLBACK_ZH.get(
                    cdk_status, f"Mirror 酱 CDK 状态异常（{cdk_status}）"
                ),
            )
        )
    elif cdk_message:
        lines.append(("info", cdk_message))

    expired_time = _result_field(result, "cdk_expired_time")
    if expired_time is not None:
        try:
            expired_at = float(expired_time)
        except (TypeError, ValueError):
            expired_at = None
        if expired_at is not None:
            current = time.time() if now is None else now
            days_left = (expired_at - current) / 86400
            if days_left <= CDK_EXPIRY_WARNING_DAYS:
                expired_date = (
                    datetime.fromtimestamp(expired_at).astimezone().strftime("%Y-%m-%d")
                )
                if days_left < 0:
                    lines.append(("warning", f"Mirror 酱 CDK 已于 {expired_date} 到期"))
                else:
                    lines.append(
                        (
                            "warning",
                            f"Mirror 酱 CDK 将于 {expired_date} 到期"
                            f"（剩余 {max(int(days_left), 0)} 天）",
                        )
                    )
    return lines


def describe_unusable_runtime(project_path: Path) -> str | None:
    """运行前自检：这个项目要用的运行池 runtime 还能用吗？

    只在池里已经存在这个项目会用到的那份 runtime 时才探一次（一个子进程，约
    100ms——解释器本来就要起）。没建过就不拦：那份环境会在运行时按需准备，失败
    自有它自己的报错路径。

    runtime 的选法与 ``prepare_runner_environment`` 一致：同一份依赖选择器加同一个
    引导解释器。只按 MaaFW 版本去池里挑不行——旧版本用便携包 embeddable Python
    建出的坏环境和修好后新建的好环境 MaaFW 版本相同，挑错了会把能跑的任务拦下。

    拦在 ``check()`` 而不是只靠编辑页的提示：队列与定时任务不经过编辑页，
    绕不过 check()；而且这里拦下来时模拟器和游戏都还没启动。
    """

    # 运行池会拉起 uv 与安装器，只在真要用时导入，别让每次 import 都付这份成本。
    from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
        build_runner_packages,
        resolve_project_maafw_requirement,
    )
    from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
        MaaFWRuntimePoolError,
        MaaFWRuntimePoolService,
    )
    from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.installer import (
        host_bootstrap_python_request,
    )

    try:
        requirement = resolve_project_maafw_requirement(project_path)
        if not requirement:
            return None
        packages = build_runner_packages(project_path, maafw_requirement=requirement)
        service = MaaFWRuntimePoolService()
        python_identity = None
        bootstrap_request = host_bootstrap_python_request()
        if bootstrap_request is not None:
            target = service.pool.resolve_python(bootstrap_request, allow_install=False)
            if target is None:
                # 托管解释器还没装，runtime 也就不可能存在。
                return None
            python_identity = target["identity"]
    except Exception:  # noqa: BLE001 - 自检失败不该反过来挡住运行
        return None

    try:
        # 找到 runtime 后 resolve() 会真的起一次解释器核对 ABI，起不来就是坏了。
        service.resolve(packages, python_identity=python_identity)
    except MaaFWRuntimePoolError as exc:  # 原文就是给用户看的
        return f"MFW 运行环境不可用：{exc}"
    except Exception:  # noqa: BLE001
        return None
    return None


class MaaFWEmbeddedManager(TaskExecuteBase):
    """MaaFW 内置运行（第二层）管理器。

    只负责把脚本配置、用户配置和模拟器实例装配好，运行编排全部交给
    ``MaaFWPluginAutoProxyTask``。
    """

    wait_for_finalizer_on_cancel = True

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result: str = "-"
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.script_config: MaaFWConfig | None = None
        self.user_config: MultipleConfig[MaaFWUserConfig] | None = None
        self.runnable_user_uids: list[uuid.UUID] = []
        self.emulator_manager: DeviceBase | None = None
        # 当前正在跑的那一位用户的 AutoProxy 任务；每个用户各建一个。
        self.inner_task: "MaaFWPluginAutoProxyTask | None" = None
        self._inner_finalized = True
        self._report_finalized = False
        # 项目更新的日志行（已带时间戳）；运行前更新的会并入第一位用户的日志。
        self.project_update_logs: list[str] = []
        self._auto_update_mode: AutoUpdateMode = "Off"
        # 只有 main_task 正常跑完全部用户才置位；取消/崩溃路径不跑运行后更新。
        self._users_completed = False

    async def check(self) -> str:
        """校验 embedded 运行的前置条件，返回 ``"Pass"`` 或用户可读的原因。"""

        if self.task_info.mode != "AutoProxy":
            return "MFW 内置运行当前仅支持自动代理模式"

        try:
            script_uid = uuid.UUID(self.script_info.script_id)
        except (ValueError, AttributeError, TypeError):
            return "MFW 脚本 ID 无效，请刷新后重试"

        try:
            script_config = Config.ScriptConfig[script_uid]
        except (KeyError, ValueError):
            return "MFW 脚本配置不存在，请刷新后重试"

        if not isinstance(script_config, MaaFWConfig):
            return "脚本配置类型错误，不是 MFW 脚本类型"
        self.script_config = script_config

        project_value = str(script_config.get("Info", "Path") or "").strip()
        if not project_value:
            return "请设置 MFW 项目路径"
        if not Path(project_value).resolve().is_dir():
            return "请设置包含 interface.json 的 MFW 项目目录"

        user_config: MultipleConfig[MaaFWUserConfig] = MultipleConfig([MaaFWUserConfig])
        await user_config.load(await script_config.UserData.toDict())
        self.user_config = user_config

        # 只跑「已启用且剩余天数未耗尽」的用户。
        self.runnable_user_uids = [
            uid
            for uid, cfg in user_config.data.items()
            if cfg.get("Info", "Status") and cfg.get("Info", "RemainedDay") != 0
        ]
        if not self.runnable_user_uids:
            return "MFW 没有可运行的用户，请在用户管理页添加并启用至少一个用户"

        self.emulator_manager = await self._resolve_emulator_manager(script_config)

        environment_problem = await asyncio.to_thread(
            describe_unusable_runtime, Path(project_value)
        )
        if environment_problem:
            return environment_problem

        return "Pass"

    @staticmethod
    async def _resolve_emulator_manager(
        script_config: MaaFWConfig,
    ) -> DeviceBase | None:
        """按脚本级模拟器配置取实例；未配置时返回 None。

        ADB controller 缺模拟器时由 runner_task 自己抛出可读错误，这里不预判
        controller 类型 —— 判定要读 interface，属于运行编排的职责。
        """

        emulator_id = str(script_config.get("Emulator", "Id") or "").strip()
        if not emulator_id or emulator_id == "-":
            return None

        from app.core import EmulatorManager

        try:
            return await EmulatorManager.get_emulator_instance(emulator_id)
        except Exception as exc:  # noqa: BLE001 - 缺模拟器不该拦住 Win32 项目
            logger.warning(f"MFW 内置运行取模拟器实例失败，将按无模拟器继续：{exc}")
            return None

    @staticmethod
    def _resolve_runtime_pool_route():
        """解析 Runtime Pool 路由（root + poolId）。

        插件形态下这一步由 `adapter.py` 查 `maafw.runtime_pool.v1` 服务契约后
        注入；树内没有服务注册表，直接实例化服务再走同一个解析函数。
        `_run_maafw` 缺这两个值会直接拒绝运行。
        """

        from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
            MaaFWRuntimePoolService,
        )
        from app.task.MaaFW.tools.embedded.runtime_route import (
            runtime_pool_route_from_service,
        )

        return runtime_pool_route_from_service(MaaFWRuntimePoolService())

    def _build_inner_task(self) -> "MaaFWPluginAutoProxyTask":
        # 延迟导入：runner_task 经 runner 包 import maa，导入即打开 DLL。
        from app.task.MaaFW.tools.embedded.runner_task import (
            MaaFWPluginAutoProxyTask,
        )

        assert self.script_config is not None
        assert self.user_config is not None
        task = MaaFWPluginAutoProxyTask(
            self.script_info,
            self.script_config,
            self.user_config.data,
            self.emulator_manager,
            # 运行前更新的日志只并入第一位用户；取走后列表清空，后续用户不重复。
            project_update_logs=self._take_project_update_logs(),
        )
        route = self._resolve_runtime_pool_route()
        task.maafw_runtime_pool_root = route.root
        task.maafw_runtime_pool_id = route.pool_id
        return task

    # ------------------------------------------------------------------
    # 项目自动更新
    # ------------------------------------------------------------------

    def _take_project_update_logs(self) -> list[str]:
        logs, self.project_update_logs = self.project_update_logs, []
        return logs

    def _append_update_log(self, message: str) -> None:
        """记一行更新日志：后端日志 + 脚本实时日志 + 待并入用户日志的缓冲。

        行格式与 ``runner_task._format_user_log_line`` 一致（那边 import maa，
        不能从这里引用），这样并入用户日志后看不出接缝。
        """

        logger.info(f"MFW 项目更新：{message}")
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
        for line in str(message).splitlines() or [""]:
            self.project_update_logs.append(f"[{timestamp}] {line}\n")
        self.script_info.log = "".join(self.project_update_logs[-80:])

    async def _notify_update(
        self, level: Literal["info", "warning", "error"], message: str
    ) -> None:
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level=level, message=message),
        )

    @staticmethod
    def _load_interface_model(project_path: Path, *, force_reload: bool = False):
        """读 interface（走核心包的内存/磁盘缓存）；``force_reload`` 用于更新后失效缓存。"""

        from app.task.MaaFW.tools.core.automas_maafw_interface import (
            load_interface_model_cached,
        )

        return load_interface_model_cached(project_path, force_reload=force_reload)

    async def _invoke_project_update(
        self, project_path: Path, credentials: MaaFWUpdateCredentials
    ) -> Any:
        """直接调核心包（不经 ``tools/project_updater.py`` 门面）。

        锁在 manager 层是空的（用户 inner task 才拿项目锁），让核心包自己拿，
        所以 ``project_lock_already_held=False``。
        """

        from app.task.MaaFW.tools.core.automas_maafw_project_update import (
            update_maafw_project_if_needed,
        )

        kwargs: dict[str, Any] = {
            "mirror_cdk": credentials.cdk,
            "channel": credentials.channel,
            # 下载源由用户显式选定，核心包不再自动分流。
            "source_config": {"package_source": credentials.package_source},
            "send_log": self._append_update_log,
            "project_lock_already_held": False,
        }
        # 核心包签名正在收敛：``interface_model`` 位置参数可能被拿掉（改为包内
        # 自己读）。按实际签名决定传不传，两种形态都能跑。
        kwargs["interface_model"] = await asyncio.to_thread(
            self._load_interface_model, project_path
        )
        # 与手动更新的 API 路径一致：用户配了代理，运行时更新也得走代理，
        # 否则受限网络下「手动能更、自动不能」。
        kwargs["proxy"] = Config.proxy
        return await update_maafw_project_if_needed(project_path, **kwargs)

    async def _run_project_update(self, phase: AutoUpdateMode) -> None:
        """按时机更新项目目录。整个脚本只跑一次，且在用户任务之外。

        **任何失败都只记日志 + 通知，不抛出、不改脚本/用户状态**：更新失败
        不该让本来能跑的代理任务跑不了。耗时也天然不计入 ``Run.RunTimeLimit``
        ——那个限时是 ``runner_task._run_maafw`` 用 ``asyncio.wait_for`` 套在
        单个用户的 MaaFW 运行上的，这里还没建（或已收尾）用户任务。
        """

        assert self.script_config is not None
        phase_zh = "运行前" if phase == "BeforeRun" else "运行后"
        project_path = Path(
            str(self.script_config.get("Info", "Path") or "")
        ).resolve()

        if (project_path / MANAGED_PROJECT_SIDECAR_NAME).is_file():
            self._append_update_log("受管项目由 Store 管理版本，跳过原地更新")
            return

        credentials = resolve_update_credentials(self.script_config)
        self._append_update_log(
            f"开始{phase_zh}检查 MFW 项目更新：下载源 {credentials.source}，"
            f"渠道 {credentials.channel}，Mirror 酱 CDK {describe_cdk(credentials)}"
        )

        try:
            result = await self._invoke_project_update(project_path, credentials)
        except Exception as exc:  # noqa: BLE001 - 更新失败不阻断运行
            reason = sanitize_log_message(str(exc)).strip() or type(exc).__name__
            logger.opt(exception=True).warning(
                f"MFW 项目{phase_zh}更新失败，任务继续：{reason}"
            )
            self._append_update_log(f"MFW 项目更新失败，任务继续：{reason}")
            await self._notify_update(
                "error", f"MFW 项目{phase_zh}更新失败，任务继续：{reason}"
            )
            return

        if bool(_result_field(result, "updated")):
            # interface.json 已经变了：不刷新缓存，本轮用户仍按旧版任务表跑。
            try:
                interface_model = await asyncio.to_thread(
                    self._load_interface_model, project_path, force_reload=True
                )
                self._append_update_log(
                    "interface 缓存已刷新，当前版本："
                    f"{getattr(interface_model, 'version', None) or '未知'}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(
                    f"MFW 项目更新后刷新 interface 缓存失败：{exc}"
                )
                self._append_update_log(f"刷新 interface 缓存失败：{exc}")

        lines = describe_update_result(result)
        for _, text in lines:
            self._append_update_log(text)
        # 「已是最新 / 跳过」只留在日志里；真的更新了或 CDK 有问题才弹通知，
        # 免得每次运行都弹一条没信息量的提示。
        has_warning = any(level == "warning" for level, _ in lines)
        if lines and (has_warning or bool(_result_field(result, "updated"))):
            await self._notify_update(
                "warning" if has_warning else "info",
                "；".join(text for _, text in lines),
            )

    async def main_task(self) -> None:
        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        # task_manager 只放了一个「暂未加载」占位项，真实用户列表由各 manager
        # 自己填（与 manager.py 的做法一致）。AutoProxy 任务按 current_index
        # 取当前用户，这一步不做后面必然取到占位项、拿它的随机 uid 去查
        # user_config 而 KeyError。
        assert self.user_config is not None
        assert self.script_config is not None
        self.script_info.user_list = [
            UserItem(
                user_id=str(uid),
                name=self.user_config[uid].get("Info", "Name"),
                status="等待",
            )
            for uid in self.runnable_user_uids
        ]
        self.script_info.status = "运行"
        logger.info(
            f"MFW 内置运行用户列表加载完成，已筛选用户数: "
            f"{len(self.script_info.user_list)}"
        )

        # 运行前更新：整个脚本一次，在第一位用户的 inner task 建起来之前。
        self._auto_update_mode = resolve_auto_update_mode(self.script_config)
        if self._auto_update_mode == "BeforeRun":
            await self._run_project_update("BeforeRun")

        # AutoProxy 的 main_task / final_task 都是**按用户**的（final_task 会
        # 结算该用户的代理次数、剩余天数并释放项目锁），因此每个用户各建一个。
        for index in range(len(self.runnable_user_uids)):
            self.script_info.current_index = index
            self.inner_task = self._build_inner_task()
            self._inner_finalized = False
            try:
                await self.inner_task.main_task()
            # 只截 Exception：CancelledError 属 BaseException，必须继续外抛，
            # 否则基类的取消路径与下面的收尾保证一起失效。
            except Exception as exc:  # noqa: BLE001
                await self.inner_task.on_crash(exc)
            finally:
                await self._finalize_inner_task()
        self._users_completed = True

    async def _finalize_inner_task(self) -> None:
        """收尾当前用户的 AutoProxy 任务；对同一个任务只做一次。"""

        if self.inner_task is None or self._inner_finalized:
            return
        self._inner_finalized = True
        try:
            await self.inner_task.final_task()
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 内置运行收尾异常：{exc}")

    async def final_task(self) -> None:
        # 正常路径下每个用户跑完就已收尾；这里只兜取消与异常路径的最后一位用户。
        await self._finalize_inner_task()
        for user in self.script_info.user_list:
            if user.status in ("等待", "运行"):
                user.status = "异常"

        # 脚本终态必须在这里落定：main_task 里只置过「运行」，不置终态的话
        # 任务结束后脚本行会一直停在「运行」（与第一层 manager.py 同一套口径）。
        error_users = [
            user for user in self.script_info.user_list if user.status == "异常"
        ]
        completed_users = [
            user for user in self.script_info.user_list if user.status == "完成"
        ]
        if self.check_result == "Pass" and not error_users:
            self.script_info.status = "完成"
        else:
            self.script_info.status = "异常"

        if self.check_result != "Pass":
            return
        if self._report_finalized:
            return
        self._report_finalized = True

        title = (
            f"{datetime.now().strftime('%m-%d')} | "
            f"{self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
        )
        task_result = append_task_game_sign_summary(
            self.task_info, self.script_info.result
        )
        has_game_sign_summary = task_result != self.script_info.result
        result = {
            "title": f"{TASK_MODE_ZH[self.task_info.mode]}任务报告",
            "script_name": self.script_info.name or "空白",
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": len(completed_users),
            "uncompleted_count": len(error_users),
            "result": task_result,
            "game_sign_summary": has_game_sign_summary,
        }
        try:
            push_result = await push_notification(
                mode="代理结果",
                title=title,
                message=result,
                task_info=self.task_info,
            )
            finalize_task_game_sign_notification(
                self.task_info, has_game_sign_summary, push_result
            )
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"推送 MFW 代理结果时出现异常: {exc}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"推送 MFW 代理结果时出现异常: {exc}"
                ),
            )

        # 运行后更新：所有用户都跑完（main_task 正常走到底）之后一次。放在
        # 代理结果推送之后，别让下载耽误报告；取消/崩溃路径不跑。
        if self._users_completed and self._auto_update_mode == "AfterRun":
            await self._run_project_update("AfterRun")

    async def on_crash(self, e: Exception) -> None:
        logger.exception(f"MFW 内置运行异常：{e}")
        if self.inner_task is not None and not self._inner_finalized:
            await self.inner_task.on_crash(e)
            return
        self.script_info.status = "异常"


__all__ = ["MaaFWEmbeddedManager"]
