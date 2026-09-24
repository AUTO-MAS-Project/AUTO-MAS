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

"""HSR 端点背后的业务：``app/api/scripts.py`` 里的 ``/hsr/*`` 端点只做
取参数 → 调这里的一个函数 → ``XxxOut(**reply.out_fields())``。

依赖方向只能是 ``app.api`` → 这里，不得反向导入 ``app.api``。各函数里对
``app.task.HSR.tools.*`` 的导入保持在 ``try`` 里惰性进行：导入失败与业务异常
一样由同一个 ``except`` 兜住，与业务还写在端点里时一致。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.config import HSRConfig as RuntimeHSRConfig
from app.models.schema import (
    HSRCapabilitiesData,
    HSRCloudLoginData,
    HSRManagedConfigData,
    HSRSRAProfilesData,
    HSRStageOptionsData,
    HSRUpdateData,
)
from app.utils import get_logger

# 这些日志原先由 API 层记录，模块名沿用「脚本管理 API」：搬家不改日志上的模块名。
logger = get_logger("脚本管理 API")


@dataclass(frozen=True, slots=True)
class HSRApiReply:
    """专项函数交回端点的结果，端点只做 ``XxxOut(**reply.out_fields())``。

    ``code != 200`` 即失败，一律 ``status="error"``；``message`` / ``data`` 为 None 时
    不传，让响应模型用自己的缺省值——与业务还写在端点里时直接构造响应的写法逐字段一致。
    """

    code: int = 200
    message: str | None = None
    data: Any = None

    @classmethod
    def error(cls, code: int, message: str, data: Any = None) -> HSRApiReply:
        return cls(code=code, message=message, data=data)

    def out_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if self.code != 200:
            fields["code"] = self.code
            fields["status"] = "error"
        if self.message is not None:
            fields["message"] = self.message
        if self.data is not None:
            fields["data"] = self.data
        return fields


def hsr_script_config(script_id: str):
    """Resolve an HSR script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeHSRConfig):
        raise TypeError("脚本配置类型错误, 不是 HSR 类型")
    return script_config


def hsr_user_config(script_config: RuntimeHSRConfig, user_id: str):
    user_config = script_config.UserData[uuid.UUID(user_id)]
    return user_config


async def get_stage_options(
    script_id: str | None, engine: str, user_id: str | None
) -> HSRApiReply:
    """``/hsr/stage-options``：M7A/SRA 原生副本字段；``user_id`` 只做归属校验。"""

    try:
        if not script_id:
            return HSRApiReply.error(400, "缺少 scriptId")

        script_config = hsr_script_config(script_id)
        if user_id:
            hsr_user_config(script_config, user_id)
        from app.task.HSR.tools.api import build_stage_options

        data = HSRStageOptionsData(**build_stage_options(script_config, engine))
        option_count = sum(len(category.options) for category in data.categories)
        return HSRApiReply(
            message=f"共 {option_count} 个 HSR 体力副本选项",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_hsr_stage_options_api失败: {type(e).__name__}: {e}"
        )
        return HSRApiReply.error(
            400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            f"{type(e).__name__}: {str(e)}",
        )


async def get_capabilities(script_id: str | None) -> HSRApiReply:
    """``/hsr/capabilities``：内置 HSR 的能力快照。"""

    try:
        if not script_id:
            return HSRApiReply.error(400, "缺少 scriptId")
        script_config = hsr_script_config(script_id)
        from app.task.HSR.tools.api import build_capabilities

        # 走线程：里面要起一次 SRA-cli.exe --version 读版本号，正常 0.09 秒，
        # 但异常构建或杀毒扫描时能卡到超时，直接调会连 WebSocket 一起冻住。
        data = HSRCapabilitiesData(
            **await asyncio.to_thread(build_capabilities, script_config)
        )
        return HSRApiReply(data=data)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_hsr_capabilities_api失败: {type(e).__name__}: {e}"
        )
        return HSRApiReply.error(
            400
            if isinstance(
                e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError)
            )
            else 500,
            f"{type(e).__name__}: {str(e)}",
        )


async def update_engine(script_id: str, engine: str, action: str) -> HSRApiReply:
    """``/hsr/update``：手动检查（``check``）或安装（``apply``）M7A / SRA 的更新。"""

    try:
        script_config = hsr_script_config(script_id)
        from app.task.HSR.task_mapping import engine_label
        from app.task.HSR.tools.native_control import resolve_script_path
        from app.task.HSR.tools.update import (
            check_engine_update,
            update_engine_if_needed,
        )

        root = resolve_script_path(script_config, engine)
        if not root:
            return HSRApiReply.error(400, f"未配置{engine_label(engine)}路径")

        source = str(script_config.get("Update", f"{engine}Source") or "")
        channel = str(script_config.get("Update", "Channel") or "stable")
        cdk = str(script_config.get("Update", "MirrorChyanCDK") or "")

        if action == "check":
            result = await check_engine_update(
                engine,
                Path(root),
                source=source,
                channel=channel,
                cdk=cdk,
                proxy=Config.proxy,
            )
            return HSRApiReply(
                data=HSRUpdateData(
                    engine=engine,
                    checked=True,
                    updated=False,
                    current_version=result.current_version,
                    latest_version=result.latest_version,
                    update_available=result.update_available,
                    installable=result.installable,
                    message=result.blocked_reason or "",
                )
            )

        # apply：目录锁必须以非阻塞方式拿，正在跑任务时立刻告诉用户，
        # 而不是把 HTTP 请求挂在那里等。
        from app.task.HSR.tools.external_locks import (
            HSRExternalPathBusyError,
            acquire_external_path_locks,
            resolve_external_lock_paths,
        )

        try:
            lease = await acquire_external_path_locks(
                resolve_external_lock_paths(script_config, (engine,)),
                wait=False,
            )
        except HSRExternalPathBusyError as e:
            return HSRApiReply.error(409, str(e))

        try:
            outcome = await update_engine_if_needed(
                engine,
                Path(root),
                source=source,
                channel=channel,
                cdk=cdk,
                proxy=Config.proxy,
                download_dir=Path.cwd() / "data" / "hsr_update",
            )
        finally:
            lease.release()

        return HSRApiReply(
            data=HSRUpdateData(
                engine=engine,
                checked=outcome.checked,
                updated=outcome.updated,
                current_version=outcome.current_version,
                latest_version=outcome.latest_version,
                update_available=outcome.update_available,
                installable=outcome.updated or not outcome.message,
                message=outcome.message,
            )
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"post_hsr_update_api失败: {type(e).__name__}: {e}"
        )
        return HSRApiReply.error(
            400
            if isinstance(
                e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError)
            )
            else 500,
            f"{type(e).__name__}: {str(e)}",
        )


async def cloud_login(script_id: str, user_id: str) -> HSRApiReply:
    """``/hsr/cloud-login``：为该用户登录云·星穹铁道；忙时 409，未确认登录 400。"""

    try:
        script_config = hsr_script_config(script_id)
        user_config = hsr_user_config(script_config, user_id)
        from app.task.HSR.tools.cloud_login import (
            HSRCloudLoginBusyError,
            run_cloud_login,
        )

        try:
            outcome = await run_cloud_login(
                script_config,
                script_id=script_id,
                user_id=user_id,
                user_name=str(user_config.get("Info", "Name") or user_id),
            )
        except HSRCloudLoginBusyError as e:
            return HSRApiReply.error(409, str(e))

        return HSRApiReply(
            code=200 if outcome.logged_in else 400,
            message=outcome.message,
            data=HSRCloudLoginData(
                logged_in=outcome.logged_in,
                last_login=outcome.last_login,
                message=outcome.message,
            ),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"post_hsr_cloud_login_api失败: {type(e).__name__}: {e}"
        )
        return HSRApiReply.error(
            400
            if isinstance(
                e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError)
            )
            else 500,
            str(e)
            if isinstance(e, (ValueError, RuntimeError))
            else (f"{type(e).__name__}: {str(e)}"),
        )


async def get_managed_config(script_id: str | None, user_id: str | None) -> HSRApiReply:
    """``/hsr/managed-config``：原生动态托管字段，按用户配置来源决定读哪份计划。"""

    try:
        if not script_id:
            return HSRApiReply.error(400, "缺少 scriptId")
        script_config = hsr_script_config(script_id)
        user_config = None
        if user_id:
            user_config = hsr_user_config(script_config, user_id)
        from app.task.HSR.tools.api import build_managed_config

        data = HSRManagedConfigData(**build_managed_config(script_config, user_config))
        return HSRApiReply(data=data)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_hsr_managed_config_api失败: {type(e).__name__}: {e}"
        )
        return HSRApiReply.error(
            400
            if isinstance(
                e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError)
            )
            else 500,
            f"{type(e).__name__}: {str(e)}",
        )


async def get_sra_profiles(script_id: str | None) -> HSRApiReply:
    """``/hsr/sra-profiles``：列出 SRA 配置档案并标出脚本当前生效的那份。"""

    try:
        if not script_id:
            return HSRApiReply.error(400, "缺少 scriptId")
        script_config = hsr_script_config(script_id)
        from app.task.HSR.tools.api import build_sra_profiles

        data = HSRSRAProfilesData(**build_sra_profiles(script_config))
        return HSRApiReply(
            message=f"共 {len(data.profiles)} 份 SRA 配置档案",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_hsr_sra_profiles_api失败: {type(e).__name__}: {e}"
        )
        return HSRApiReply.error(
            400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            f"{type(e).__name__}: {str(e)}",
        )
