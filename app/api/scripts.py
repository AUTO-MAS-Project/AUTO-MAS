#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


import asyncio
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from app.core import Config
from app.models.config import BetterGIConfig as RuntimeBetterGIConfig
from app.models.config import HSRConfig as RuntimeHSRConfig
from app.models.config import MaaFWConfig as RuntimeMaaFWConfig
from app.models.config import OkNteConfig as RuntimeOkNteConfig
from app.models.schema import *
from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.preview import (
    build_interface_preview_data,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update import (
    MaaFWProjectUpdateError,
    discover_maafw_project_update,
    update_maafw_project_if_needed,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
    _public_package_source,
    detect_maafw_project_shell_hint,
)
from app.task.MaaFW.tools.embedded.update_credentials import (
    resolve_update_credentials,
)
from app.utils import get_logger
from app.utils.paths import SOURCE_ROOT
from app.utils.security import sanitize_log_message

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])
logger = get_logger("脚本管理 API")


def _hsr_script_config(script_id: str):
    """Resolve an HSR script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeHSRConfig):
        raise TypeError("脚本配置类型错误, 不是 HSR 类型")
    return script_config


def _bettergi_script_config(script_id: str):
    """Resolve a BetterGI script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeBetterGIConfig):
        raise TypeError("脚本配置类型错误, 不是 BetterGI 类型")
    return script_config


def _bettergi_user_id(script_config: RuntimeBetterGIConfig, user_id: str):
    """Validate that a BetterGI user exists before domain access."""

    try:
        script_config.UserData[uuid.UUID(user_id)]
    except KeyError:
        raise ValueError("用户不存在或无权访问该配置")


def _bettergi_user_config(script_config: RuntimeBetterGIConfig, user_id: str):
    """Resolve a BetterGI user config and reject unknown IDs before domain access."""

    user_config = script_config.UserData[uuid.UUID(user_id)]
    return user_config


def _read_combat_from_plan(
    script_config, user_id: str, group: str, source: str, data: dict
) -> dict:
    """把战斗组 Plan 里的设置反查回右栏键，合并进读取结果（回显）。"""
    from app.task.BetterGI.tools import one_dragon_plan

    target_group = _combat_target_group(source, group)
    mapping = one_dragon_plan.RIGHTBAR_TO_PLAN.get(
        one_dragon_plan.resolve_base_name(target_group)
    )
    if not mapping:
        return data
    user_config = _bettergi_user_config(script_config, user_id)
    plan_json = user_config.get("OneDragon", "Plan") or ""
    data.update(one_dragon_plan.extract_rightbar_from_plan(plan_json, target_group) or {})
    # 还原 weekly 嵌套结构为平铺右栏键（供前端周表回显）
    steps = one_dragon_plan.parse_one_dragon_plan(plan_json) if plan_json else []
    target = next((s for s in steps if s.get("name") == target_group), None)
    if target:
        data.update(
            one_dragon_plan.flatten_weekly_struct(
                target_group, target.get("settings") or {}
            )
        )
    # 「开启每日地脉花」未配置（Plan 无该键，如新用户）时默认开启：与种子模板的
    # 「每日耗尽模式」标准状态一致；用户选过每周模式则 Plan 已有显式 false，不受影响。
    if target_group == "自动地脉花":
        data.setdefault("leyLineDailyEnabled", True)
    return data


def _route_combat_to_plan(
    script_config,
    user_id: str,
    group: str,
    settings: dict,
    source: str,
) -> tuple[dict, "str | None"]:
    """战斗4项右栏设置：可映射字段翻译后写入 OneDragon.Plan（执行层参数源）。

    原生侧**保留全量字段**（双写）：执行层只接管「Plan 中有该组步骤且队列中启用」
    的战斗组，其余战斗组仍走原生一条龙 / 全局 config.json，必须能读到最新值；
    已被接管的组会从一条龙副本剔除，多写的原生值不会被消费。

    返回 ``(原生字段, 新 Plan JSON 或 None)``。非战斗组 / 无可映射键时返回
    ``(settings, None)``，调用方按原逻辑写原生存储即可。
    """
    from app.task.BetterGI.tools import one_dragon_plan

    target_group = _combat_target_group(source, group)
    mapping = one_dragon_plan.RIGHTBAR_TO_PLAN.get(
        one_dragon_plan.resolve_base_name(target_group)
    )
    if not mapping or not settings:
        return settings, None
    plan_settings = {k: v for k, v in settings.items() if k in mapping}
    extra = one_dragon_plan.extract_weekly_struct(target_group, settings)
    if not plan_settings and not extra:
        return settings, None
    user_config = _bettergi_user_config(script_config, user_id)
    plan_json = user_config.get("OneDragon", "Plan") or ""
    new_plan = one_dragon_plan.merge_rightbar_into_plan(
        plan_json, target_group, plan_settings, extra=extra or None
    )
    return settings, new_plan


def _combat_target_group(source: str, group: str) -> str:
    """确定右栏设置归属的战斗组（支持同一战斗组的多个独立实例）。

    优先采用前端传入的**实例组名**（形如 ``自动幽境危战-3``、``自动秘境-3``）：
    同一战斗组可配多个实例，各自独立保存/回显设置。未传组名（或组名不是内置
    战斗组）时按 source 固定映射（globalStygian→自动幽境危战、globalDomain→
    自动秘境），兼容不带 groupName 的调用方与旧数据。
    """
    from app.task.BetterGI.tools import one_dragon_plan

    if group and one_dragon_plan.resolve_base_name(group):
        return group
    return {"globalStygian": "自动幽境危战", "globalDomain": "自动秘境"}.get(source, group)


def _hsr_user_config(script_config: RuntimeHSRConfig, user_id: str):
    user_config = script_config.UserData[uuid.UUID(user_id)]
    return user_config


def _oknte_script_config(script_id: str) -> tuple[uuid.UUID, RuntimeOkNteConfig]:
    script_uid = uuid.UUID(script_id)
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, RuntimeOkNteConfig):
        raise ValueError("脚本配置类型错误, 不是 OK-NTE 类型")
    return script_uid, script_config


def _oknte_legacy_mas_config_dir(script_id: str) -> Path:
    script_uid, _ = _oknte_script_config(script_id)
    return Path.cwd() / "data" / str(script_uid) / "Default" / "ConfigFile"


def _oknte_mas_config_dir(script_id: str, user_id: str) -> Path:
    script_uid, _ = _oknte_script_config(script_id)
    user_uid = uuid.UUID(user_id)
    return Path.cwd() / "data" / str(script_uid) / str(user_uid) / "ConfigFile"


def _oknte_config_file_path(config_dir: Path, filename: str) -> Path:
    file_path = Path(filename)
    if file_path.name != filename or file_path.is_absolute() or ".." in file_path.parts:
        raise ValueError("配置文件名非法")
    return config_dir / filename


def _maafw_script_config(script_id: str) -> RuntimeMaaFWConfig:
    """Resolve a MaaFW script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeMaaFWConfig):
        raise TypeError("脚本配置类型错误, 不是 MFW 类型")
    return script_config


# 这两种 CDK 状态不需要额外提示：ok 是正常，absent 在选 GitHub 源时本就无关。
_MAAFW_CDK_QUIET_STATUSES = frozenset({"ok", "absent"})
_maafw_update_logger = get_logger("MaaFW 项目更新")
_maafw_env_logger = get_logger("MFW 运行环境")


def _maafw_update_send_log(line: str) -> None:
    """更新实现的逐行日志回调；写日志前先打码，避免 CDK 等敏感值落盘。"""

    _maafw_update_logger.info(sanitize_log_message(str(line)))


def _maafw_update_extra_fields(result: Any) -> dict[str, Any]:
    """按核心包约定的属性名读取 CDK / 版本附加字段，缺字段一律 None。

    核心包返回对象（discovery 或 result）带 ``version_name`` / ``source`` /
    ``cdk_status`` / ``cdk_message`` / ``cdk_expired_time`` / ``skipped_reason``；
    此处用 ``getattr(..., None)`` 读取，核心包尚未补齐时也能返回。
    """

    def _text(name: str) -> str | None:
        value = getattr(result, name, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    expired_raw = getattr(result, "cdk_expired_time", None)
    expired_time: int | None
    if isinstance(expired_raw, bool) or expired_raw is None:
        expired_time = None
    else:
        try:
            expired_time = int(expired_raw)
        except (TypeError, ValueError):
            expired_time = None

    return {
        "versionName": _text("version_name"),
        "cdkStatus": _text("cdk_status"),
        "cdkMessage": _text("cdk_message"),
        "cdkExpiredTime": expired_time,
        "skippedReason": _text("skipped_reason"),
    }


def _maafw_update_message_with_cdk(message: str, extra: dict[str, Any]) -> str:
    """CDK 状态异常时把提示原文附到摘要里。

    仍按成功返回（HTTP 200）：CDK 有问题只是这次装不了，脚本本身照常能跑，
    用户看到原因后可以去续期或改用 GitHub 源。
    """

    status = extra.get("cdkStatus")
    cdk_message = extra.get("cdkMessage")
    if status and status not in _MAAFW_CDK_QUIET_STATUSES and cdk_message:
        return f"{message}（{cdk_message}）"
    return message


def _config_text(config: Any, group: str, name: str) -> str:
    """读取一个可能不存在的配置项并归一为去空白字符串。"""

    try:
        return str(config.get(group, name) or "").strip()
    except AttributeError:
        return ""


def _maafw_update_source_config(script_config: RuntimeMaaFWConfig) -> dict[str, str]:
    """组装 MaaFW 项目更新实现所需的 source_config。

    只包含用户可配置的三项：``package_source``（脚本级 ``Update.Source``，
    Mirror 酱 / GitHub）、``mirror_cdk``、``channel``。三项**都只看脚本级、
    不做全局兜底**，与 ``tools/embedded/update_credentials.py`` 用的是同一个
    解析函数，保证手动更新与运行时自动更新的行为一致。

    仓库、tag、资产文件名等 GitHub 参数不再由用户填写，由核心包从
    ``interface.json`` 与目录名自行推断。

    额外注入 ``project_shell_hint``：GitHub 发行版常按 UI 外壳分包
    （如 M9A 同版本同时发 ``*-MFAA.zip`` 与 ``*-MXU.zip``），选包实现
    在项目名/平台收窄后需要外壳家族才能消歧。本 API 直连
    ``discover_maafw_project_update``，而该函数**自身不做兜底识别**
    （兜底在 ``update_maafw_project_if_needed`` 里），故必须在此补上。
    """

    # 三项都只看脚本级，不做全局兜底（与 embedded 侧的 resolve_update_credentials
    # 一致）：全局那两项服务的是 MAS 自身的更新，语义不同。
    credentials = resolve_update_credentials(script_config)
    config = {
        "mirror_cdk": credentials.cdk,
        "channel": credentials.channel,
        "package_source": credentials.package_source,
    }
    project_path = _config_text(script_config, "Info", "Path")
    if project_path:
        shell_hint = detect_maafw_project_shell_hint(Path(project_path))
        if shell_hint:
            config["project_shell_hint"] = shell_hint
    return config


SCRIPT_BOOK = {
    "MaaConfig": MaaConfig,
    "SrcConfig": SrcConfig,
    "MaaEndConfig": MaaEndConfig,
    "M9AConfig": M9AConfig,
    "MaaFWConfig": MaaFWConfig,
    "GeneralConfig": GeneralConfig,
    "OkwwConfig": OkwwConfig,
    "OkNteConfig": OkNteConfig,
    "HSRConfig": HSRConfig,
    "BetterGIConfig": BetterGIConfig,
    "ZzzOdConfig": ZzzOdConfig,
    "BAAHConfig": BAAHConfig,
}
USER_BOOK = {
    "MaaConfig": MaaUserConfig,
    "SrcConfig": SrcUserConfig,
    "MaaEndConfig": MaaEndUserConfig,
    "M9AConfig": M9AUserConfig,
    "MaaFWConfig": MaaFWUserConfig,
    "GeneralConfig": GeneralUserConfig,
    "OkwwConfig": OkwwUserConfig,
    "OkNteConfig": OkNteUserConfig,
    "HSRConfig": HSRUserConfig,
    "BetterGIConfig": BetterGIUserConfig,
    "ZzzOdConfig": ZzzOdUserConfig,
    "BAAHConfig": BAAHUserConfig,
}


@router.post(
    "/add",
    tags=["Add"],
    summary="添加脚本",
    response_model=ScriptCreateOut,
    status_code=200,
)
async def add_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:

    try:
        uid, config = await Config.add_script(script.type, script.scriptId)
        data = SCRIPT_BOOK[type(config).__name__](**(await config.toDict()))
    except Exception as e:
        logger.opt(exception=True).warning(f"add_script失败: {type(e).__name__}: {e}")
        return ScriptCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            scriptId="",
            data=GeneralConfig(**{}),
        )
    return ScriptCreateOut(scriptId=str(uid), data=data)


@router.post(
    "/get",
    tags=["Get"],
    summary="查询脚本配置信息",
    response_model=ScriptGetOut,
    status_code=200,
)
async def get_script(script: ScriptGetIn = Body(...)) -> ScriptGetOut:

    try:
        index, data = await Config.get_script(script.scriptId)
        index = [ScriptIndexItem(**_) for _ in index]
        data = {
            uid: SCRIPT_BOOK[next((_.type for _ in index if _.uid == uid), "General")](
                **cfg
            )
            for uid, cfg in data.items()
        }
    except Exception as e:
        logger.opt(exception=True).warning(f"get_script失败: {type(e).__name__}: {e}")
        return ScriptGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return ScriptGetOut(index=index, data=data)


@router.post(
    "/update",
    tags=["Update"],
    summary="更新脚本配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_script(script: ScriptUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_script(
            script.scriptId, script.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"update_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除脚本",
    response_model=OutBase,
    status_code=200,
)
async def delete_script(script: ScriptDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_script(script.scriptId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/order",
    tags=["Update"],
    summary="重新排序脚本",
    response_model=OutBase,
    status_code=200,
)
async def reorder_script(script: ScriptReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_script(script.indexList)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"reorder_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/import/web",
    tags=["Update"],
    summary="从网络加载脚本配置",
    response_model=OutBase,
    status_code=200,
)
async def import_script_from_web(script: ScriptUrlIn = Body(...)) -> OutBase:

    try:
        await Config.import_script_from_web(script.scriptId, script.url)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_script_from_web失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/Upload/web",
    tags=["Action"],
    summary="上传脚本配置到网络",
    response_model=OutBase,
    status_code=200,
)
async def upload_script_to_web(script: ScriptUploadIn = Body(...)) -> OutBase:

    try:
        await Config.upload_script_to_web(
            script.scriptId, script.config_name, script.author, script.description
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"upload_script_to_web失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/config/import",
    tags=["Action"],
    summary="从脚本目录导入配置文件",
    response_model=OutBase,
    status_code=200,
)
async def import_script_config_file(
    config: ScriptConfigImportIn = Body(...),
) -> OutBase:

    try:
        await Config.import_script_config_file(config.scriptId, config.userId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_script_config_file失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase(message="脚本配置文件已导入")


@router.post(
    "/maaend/options",
    tags=["Get"],
    summary="获取 MaaEnd 动态选项",
    response_model=MaaEndOptionsOut,
    status_code=200,
)
async def get_maaend_options(options: ScriptDeleteIn = Body(...)) -> MaaEndOptionsOut:
    try:
        data = await Config.get_maaend_options(options.scriptId)
        return MaaEndOptionsOut(
            controllers=[ComboBoxItem(**item) for item in data["controllers"]],
            controllerTypes=data["controllerTypes"],
            essenceLocations=[
                ComboBoxItem(**item) for item in data["essenceLocations"]
            ],
            essenceMenus=[
                ComboBoxItem(**item) for item in data.get("essenceMenus", [])
            ],
            essenceTargetWeaponGroups=[
                MaaEndEssenceTargetGroup(
                    value=item["value"],
                    label=item["label"],
                    options=[ComboBoxItem(**option) for option in item["options"]],
                )
                for item in data.get("essenceTargetWeaponGroups", [])
            ],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_maaend_options失败: {type(e).__name__}: {e}"
        )
        return MaaEndOptionsOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            controllers=[],
            controllerTypes={},
            essenceLocations=[],
            essenceMenus=[],
            essenceTargetWeaponGroups=[],
        )


@router.post(
    "/user/get",
    tags=["Get"],
    summary="查询用户",
    response_model=UserGetOut,
    status_code=200,
)
async def get_user(user: UserGetIn = Body(...)) -> UserGetOut:

    try:
        index, data = await Config.get_user(user.scriptId, user.userId)
        index = [UserIndexItem(**_) for _ in index]
        data = {
            uid: USER_BOOK[
                type(Config.ScriptConfig[uuid.UUID(user.scriptId)]).__name__
            ](**cfg)
            for uid, cfg in data.items()
        }
    except Exception as e:
        logger.opt(exception=True).warning(f"get_user失败: {type(e).__name__}: {e}")
        return UserGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return UserGetOut(index=index, data=data)


@router.post(
    "/user/add",
    tags=["Add"],
    summary="添加用户",
    response_model=UserCreateOut,
    status_code=200,
)
async def add_user(user: UserInBase = Body(...)) -> UserCreateOut:

    try:
        uid, config = await Config.add_user(user.scriptId)
        data = USER_BOOK[type(Config.ScriptConfig[uuid.UUID(user.scriptId)]).__name__](
            **(await config.toDict())
        )
    except FileNotFoundError as e:
        return UserCreateOut(
            code=409,
            status="error",
            message=str(e),
            userId="",
            data=GeneralUserConfig(**{}),
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_user失败: {type(e).__name__}: {e}")
        return UserCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            userId="",
            data=GeneralUserConfig(**{}),
        )
    return UserCreateOut(userId=str(uid), data=data)


@router.post(
    "/user/update",
    tags=["Update"],
    summary="更新用户配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_user(user: UserUpdateIn = Body(...)) -> OutBase:
    data = user.data.model_dump(exclude_unset=True)

    # 队列是唯一真相源：落盘 OneDragon.Queue 时，清理 Plan 中不再被引用的战斗实例
    # （前端删除队列行只改 Queue，Plan 对应实例会残留成孤儿）。仅当 patch 含 Queue 时触发，
    # 避免其它字段保存误伤；被关闭（enabled=false）但仍在队列的行其实例保留。
    od = data.get("OneDragon") if isinstance(data, dict) else None
    if isinstance(od, dict) and "Queue" in od:
        try:
            from app.task.BetterGI.tools import one_dragon_plan

            script_cfg = Config.ScriptConfig[uuid.UUID(user.scriptId)]
            uc = script_cfg.UserData[uuid.UUID(user.userId)]
            plan = uc.get("OneDragon", "Plan") or ""
            groups = uc.get("OneDragon", "Groups") or []
            new_plan = one_dragon_plan.prune_plan_to_queue(plan, od["Queue"], groups)
            if new_plan != plan:
                od["Plan"] = new_plan
        except Exception as e:  # pragma: no cover - 兜底：同步失败不应阻断保存
            import logging

            logging.getLogger(__name__).warning(
                "队列变更同步清理 Plan 孤儿实例失败（已忽略）: %s", e
            )

    try:
        await Config.update_user(user.scriptId, user.userId, data)
    except Exception as e:
        logger.opt(exception=True).warning(f"update_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/delete",
    tags=["Delete"],
    summary="删除用户",
    response_model=OutBase,
    status_code=200,
)
async def delete_user(user: UserDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_user(user.scriptId, user.userId)
    except Exception as e:
        logger.opt(exception=True).warning(f"delete_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/order",
    tags=["Update"],
    summary="重新排序用户",
    response_model=OutBase,
    status_code=200,
)
async def reorder_user(user: UserReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_user(user.scriptId, user.indexList)
    except Exception as e:
        logger.opt(exception=True).warning(f"reorder_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/infrastructure",
    tags=["Update"],
    summary="导入基建配置文件",
    response_model=OutBase,
    status_code=200,
)
async def import_infrastructure(user: UserSetIn = Body(...)) -> OutBase:

    try:
        await Config.set_infrastructure(user.scriptId, user.userId, user.jsonFile)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_infrastructure失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/combox/infrastructure",
    tags=["Get"],
    summary="用户自定义基建排班可选项",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_user_combox_infrastructure(user: UserDeleteIn = Body(...)) -> ComboBoxOut:

    try:
        raw_data = await Config.get_user_combox_infrastructure(
            user.scriptId, user.userId
        )
        data = [ComboBoxItem(**item) for item in raw_data] if raw_data else []
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_user_combox_infrastructure失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/maa/depot/items",
    tags=["Get"],
    summary="MAA 库存保持物品可选项",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_depot_items(script: ScriptDeleteIn = Body(...)) -> ComboBoxOut:

    try:
        raw_data = await Config.get_maa_depot_items(script.scriptId)
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_maa_depot_items失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/maa/depot/stage/candidates",
    tags=["Get"],
    summary="MAA 库存保持关卡候选（掉落指定材料，按单件期望理智升序，label 为 xx 理智/件）",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_depot_stage_candidates(
    script: ScriptDeleteIn = Body(...), itemId: str = Body(...)
) -> ComboBoxOut:

    try:
        raw_data = await Config.get_maa_depot_stage_candidates(script.scriptId, itemId)
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/maa/depot/inventory",
    tags=["Get"],
    summary="MAA 仓库库存（label=数量字符串，value=物品ID）",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_maa_depot_inventory(script: ScriptDeleteIn = Body(...)) -> ComboBoxOut:

    try:
        raw_data = await Config.get_maa_depot_inventory(script.scriptId)
        data = [ComboBoxItem(**item) for item in raw_data]
    except Exception as e:
        return ComboBoxOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", data=[]
        )
    return ComboBoxOut(data=data)


@router.post(
    "/webhook/get",
    tags=["Get"],
    summary="查询 webhook 配置",
    response_model=WebhookGetOut,
    status_code=200,
)
async def get_webhook(webhook: WebhookGetIn = Body(...)) -> WebhookGetOut:

    try:
        index, data = await Config.get_webhook(
            webhook.scriptId, webhook.userId, webhook.webhookId
        )
        index = [WebhookIndexItem(**_) for _ in index]
        data = {uid: Webhook(**cfg) for uid, cfg in data.items()}
    except Exception as e:
        logger.opt(exception=True).warning(f"get_webhook失败: {type(e).__name__}: {e}")
        return WebhookGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return WebhookGetOut(index=index, data=data)


@router.post(
    "/webhook/add",
    tags=["Add"],
    summary="添加webhook项",
    response_model=WebhookCreateOut,
    status_code=200,
)
async def add_webhook(webhook: WebhookInBase = Body(...)) -> WebhookCreateOut:

    try:
        uid, config = await Config.add_webhook(webhook.scriptId, webhook.userId)
        data = Webhook(**(await config.toDict()))
    except Exception as e:
        logger.opt(exception=True).warning(f"add_webhook失败: {type(e).__name__}: {e}")
        return WebhookCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            webhookId="",
            data=Webhook(**{}),
        )
    return WebhookCreateOut(webhookId=str(uid), data=data)


@router.post(
    "/webhook/update",
    tags=["Update"],
    summary="更新webhook项",
    response_model=OutBase,
    status_code=200,
)
async def update_webhook(webhook: WebhookUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_webhook(
            webhook.scriptId,
            webhook.userId,
            webhook.webhookId,
            webhook.data.model_dump(exclude_unset=True),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"update_webhook失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/delete",
    tags=["Delete"],
    summary="删除webhook项",
    response_model=OutBase,
    status_code=200,
)
async def delete_webhook(webhook: WebhookDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_webhook(webhook.scriptId, webhook.userId, webhook.webhookId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_webhook失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/maafw/preview",
    tags=["MaaFW"],
    summary="预览 MFW interface",
    response_model=MaaFWInterfacePreviewOut,
    status_code=200,
)
async def preview_maafw_interface(
    payload: MaaFWInterfacePreviewIn = Body(...),
) -> MaaFWInterfacePreviewOut:
    """读取 MaaFW 项目 interface，并返回 controller/resource/task 摘要。"""

    try:
        root_path = Path(payload.path).resolve()
        interface = await asyncio.to_thread(load_interface_model_cached, root_path)
        preview = await asyncio.to_thread(
            build_interface_preview_data,
            root_path,
            interface,
        )
        data = MaaFWInterfacePreviewData.model_validate(preview.model_dump(mode="json"))
    except MaaFWInterfaceLoadError as exc:
        return MaaFWInterfacePreviewOut(
            code=400,
            status="error",
            message=str(exc),
            data=None,
        )
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"preview_maafw_interface失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWInterfacePreviewOut(
            code=500,
            status="error",
            message=f"MFW interface 预览失败: {exc}",
            data=None,
        )

    return MaaFWInterfacePreviewOut(
        message=f"已读取 MFW 项目 {data.project.name}，共 {len(data.tasks)} 个任务",
        data=data,
    )


@router.post(
    "/maafw/update",
    tags=["MaaFW"],
    summary="检查或执行 MFW 项目更新",
    response_model=MaaFWProjectUpdateOut,
    status_code=200,
)
async def update_maafw_project(
    payload: MaaFWProjectUpdateIn = Body(...),
) -> MaaFWProjectUpdateOut:
    """按脚本 ``Update.*`` 配置检查或应用 MaaFW 项目目录更新。

    ``action=check`` 只读取 interface 版本与更新源元数据，返回是否有新版本；
    ``action=apply`` 触发下载并原地应用更新包。失败时返回明确 ``message``。
    """

    try:
        script_config = _maafw_script_config(payload.scriptId)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWProjectUpdateOut(
            code=400, status="error", message=f"MFW 脚本无效: {exc}"
        )

    project_value = str(script_config.get("Info", "Path") or "").strip()
    if not project_value:
        return MaaFWProjectUpdateOut(
            code=400, status="error", message="请先设置 MFW 项目路径"
        )
    root_path = Path(project_value).resolve()
    if not root_path.is_dir():
        return MaaFWProjectUpdateOut(
            code=400,
            status="error",
            message="MFW 项目路径不是有效目录，请检查 Info.Path",
        )

    try:
        interface = await asyncio.to_thread(load_interface_model_cached, root_path)
    except MaaFWInterfaceLoadError as exc:
        return MaaFWProjectUpdateOut(
            code=400, status="error", message=f"MFW interface 读取失败: {exc}"
        )
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"update_maafw_project失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWProjectUpdateOut(
            code=500, status="error", message=f"MFW interface 读取失败: {exc}"
        )

    current_version = str(interface.version or "")
    source_config = _maafw_update_source_config(script_config)
    proxy = Config.proxy
    # CDK 值绝不进日志：只记录「有没有」。
    _maafw_update_logger.info(
        f"MFW 项目更新({payload.action}): script={payload.scriptId} "
        f"channel={source_config['channel']} "
        f"cdk={'已配置' if source_config['mirror_cdk'] else '未配置'}"
    )

    if payload.action == "check":
        try:
            discovery = await discover_maafw_project_update(
                interface,
                current_version=current_version,
                source_config=source_config,
                proxy=proxy,
                send_log=_maafw_update_send_log,
                # 只问有没有新版本：带 CDK 去换下载地址会扣一次今日额度，
                # 而用户可能只是随手点了下「检查更新」。真更新时再取。
                version_only=True,
            )
        except MaaFWProjectUpdateError as exc:
            return MaaFWProjectUpdateOut(
                code=400, status="error", message=f"MFW 更新检查失败: {exc}"
            )
        except Exception as exc:
            logger.opt(exception=True).warning(
                f"update_maafw_project失败: {type(exc).__name__}: {exc}"
            )
            return MaaFWProjectUpdateOut(
                code=500, status="error", message=f"MFW 更新检查失败: {exc}"
            )

        if discovery is None:
            return MaaFWProjectUpdateOut(
                message=f"MFW 项目已是最新版本: {current_version or '未知'}",
                data=MaaFWProjectUpdateData(
                    checked=True, currentVersion=current_version
                ),
            )

        extra = _maafw_update_extra_fields(discovery)
        candidate = getattr(discovery, "candidate", None)
        # discovery.source 是版本元数据来源（恒为 Mirror 酱）；响应里的 source
        # 要回答「会从哪里下载」：优先候选包来源，其次核心包的 package_source。
        # 一律用对外名（mirrorchyan / github）：candidate.source 是核心包的内部
        # 名（github_release），直接回给前端会让「下载来源」显示成 github_release。
        candidate_source = _public_package_source(
            (getattr(candidate, "source", None) if candidate is not None else None)
            or getattr(discovery, "package_source", None)
            or getattr(discovery, "source", None)
        )
        installable = bool(getattr(discovery, "installable", False))
        latest_version = getattr(discovery, "version", None) or extra["versionName"]
        extra["versionName"] = extra["versionName"] or latest_version
        message = (
            f"发现 MFW 项目新版本: {current_version or '未知'} -> {latest_version}"
        )
        unavailable_reason = getattr(discovery, "unavailable_reason", "")
        if not installable and unavailable_reason:
            message = f"{message}（暂无可安装更新包: {unavailable_reason}）"
        return MaaFWProjectUpdateOut(
            message=_maafw_update_message_with_cdk(message, extra),
            data=MaaFWProjectUpdateData(
                checked=True,
                updateAvailable=True,
                installable=installable,
                currentVersion=current_version,
                latestVersion=latest_version,
                source=candidate_source,
                **extra,
            ),
        )

    try:
        # 仓库、tag、资产名等 GitHub 参数不再传入：核心包从 interface.json 与
        # 目录名自行推断。**source_config 必须传**：它带着用户选定的下载源，
        # 漏了就会退回缺省的 GitHub——check 说走 Mirror 酱、apply 却从 GitHub
        # 下载，正是本次设计要禁掉的静默换源。
        result = await update_maafw_project_if_needed(
            root_path,
            interface,
            mirror_cdk=source_config["mirror_cdk"],
            channel=source_config["channel"],
            source_config=source_config,
            proxy=proxy,
            send_log=_maafw_update_send_log,
        )
    except MaaFWProjectUpdateError as exc:
        return MaaFWProjectUpdateOut(
            code=400, status="error", message=f"MFW 项目更新失败: {exc}"
        )
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"update_maafw_project失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWProjectUpdateOut(
            code=500, status="error", message=f"MFW 项目更新失败: {exc}"
        )

    extra = _maafw_update_extra_fields(result)
    message = str(getattr(result, "message", "") or "") or "MFW 项目更新完成"
    return MaaFWProjectUpdateOut(
        message=_maafw_update_message_with_cdk(message, extra),
        data=MaaFWProjectUpdateData(
            checked=bool(getattr(result, "checked", True)),
            updated=bool(getattr(result, "updated", False)),
            updateAvailable=bool(getattr(result, "update_available", False)),
            installable=bool(getattr(result, "installable", False)),
            currentVersion=(
                getattr(result, "current_version", None)
                or getattr(result, "previous_version", None)
                or current_version
            ),
            latestVersion=getattr(result, "latest_version", None)
            or extra["versionName"],
            source=getattr(result, "source", None),
            **extra,
        ),
    )


def _maafw_agent_env_prepare_data(
    root_path: Path,
    result: Mapping[str, Any],
    logs: list[str],
    *,
    cached: bool,
) -> MaaFWAgentEnvPrepareData:
    """把 ``prepare_project_environment()`` 的结果摊平成响应体。

    缓存命中与实际准备两条路共用，免得两边的字段各写一份、慢慢长歪。
    """

    runtime = result.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    agent_payload = result.get("agents")
    agent_payload = agent_payload if isinstance(agent_payload, Mapping) else {}
    raw_plans = agent_payload.get("plans")
    raw_plans = raw_plans if isinstance(raw_plans, list) else []

    agents = [
        MaaFWAgentEnvInfo(
            childExec=str(plan.get("childExec") or ""),
            executable=str(plan.get("executable") or ""),
            runtimeKind=plan.get("runtimeKind"),
            isolatedVenvPath=plan.get("isolatedVenvPath"),
            fallbackReason=plan.get("fallbackReason"),
        )
        for plan in raw_plans
        if isinstance(plan, Mapping)
    ]

    return MaaFWAgentEnvPrepareData(
        path=str(root_path),
        agentCount=len(agents),
        agents=agents,
        logs=logs,
        runtimeId=runtime.get("runtimeId"),
        poolId=runtime.get("poolId"),
        pythonExecutable=runtime.get("pythonExecutable"),
        venvPath=runtime.get("venvPath"),
        maafwVersion=runtime.get("maafwVersion"),
        cached=cached,
        preparedAt=result.get("preparedAt"),
    )


@router.post(
    "/maafw/agent-env/prepare",
    tags=["MaaFW"],
    summary="预备 MFW 运行环境",
    response_model=MaaFWAgentEnvPrepareOut,
    status_code=200,
)
async def prepare_maafw_agent_env(
    payload: MaaFWAgentEnvPrepareIn = Body(...),
) -> MaaFWAgentEnvPrepareOut:
    """按项目 interface 预备 Runner 运行时与各 agent 的 Python 环境。

    在项目引导里读到 interface 之后调用，把首次运行才会付出的下载与建环境
    成本提前到配置阶段。与 ``/maafw/update`` 一样是同步端点：整个准备过程
    在请求内完成，首次冷启动可能耗时数分钟。

    编辑页每打开一次就会调一次，所以先比一遍项目输入指纹：项目没更新过、上次
    准备的环境也还在盘上，就直接还回上次的结果，不再取锁起进程。用户手动重试
    时前端带 ``force``，跳过这层缓存。
    """

    # 这些模块会拉起 runtime_pool 与 agent_env，放在函数内延迟导入，
    # 避免所有 API 请求都为它们付出导入成本。
    from app.core.ws import protocol as ws_protocol
    from app.core.ws.publisher import Publisher
    from app.task.MaaFW.tools.core.automas_maafw_runner.service import (
        MaaFWRunnerService,
        project_environment_fingerprint,
    )
    from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
        MaaFWRuntimePoolService,
    )
    from app.task.MaaFW.tools.embedded.env_cache import (
        load_prepared_environment,
        store_prepared_environment,
    )
    from app.task.MaaFW.tools.embedded.project_path import (
        release_project_path,
        try_reserve_project_path,
    )
    from app.task.MaaFW.tools.embedded.runtime_route import (
        runtime_pool_route_from_service,
    )

    logs: list[str] = []
    # 准备过程可能持续数分钟（首次要下载 MaaFramework），全程把阶段、百分比
    # 与新增日志行推给前端。progress_id 留空时只落日志、不推送。
    progress_id = str(payload.scriptId or "").strip()
    loop = asyncio.get_running_loop()

    def publish_progress(event: dict) -> None:
        if not progress_id:
            return
        data = WSMaaFWEnvPrepareProgressData(
            stage=str(event.get("stage") or ""),
            status=str(event.get("status") or "running"),
            message=str(event.get("message") or ""),
            percent=event.get("percent"),
            log=event.get("log"),
        )
        # 准备跑在工作线程里，回调要跨回事件循环才能发 WS
        asyncio.run_coroutine_threadsafe(
            Publisher.send(
                id=progress_id,
                type=ws_protocol.MAAFW_ENV_PREPARE_PROGRESS,
                data=data,
            ),
            loop,
        )

    def append_log(line: str) -> None:
        logs.append(line)
        publish_progress(
            {
                "stage": "log",
                "status": "running",
                "message": line,
                "log": line,
            }
        )

    project_value = str(payload.path or "").strip()
    if not project_value:
        return MaaFWAgentEnvPrepareOut(
            code=400, status="error", message="请先设置 MFW 项目路径"
        )
    root_path = Path(project_value).resolve()
    if not root_path.is_dir():
        return MaaFWAgentEnvPrepareOut(
            code=400,
            status="error",
            message="MFW 项目路径不是有效目录，请检查项目目录",
        )

    # 与运行、更新共用同一把项目锁：同一目录同时准备/运行会互相踩。
    reservation_key = await try_reserve_project_path(root_path)
    if reservation_key is None:
        return MaaFWAgentEnvPrepareOut(
            code=409,
            status="error",
            message="该 MFW 项目正在运行、更新或准备环境，请稍后重试",
            data=MaaFWAgentEnvPrepareData(path=str(root_path), logs=logs),
        )

    try:
        # 指纹哈希的是 interface / requirements / uv.lock 这些「脚本更新了没」
        # 的输入，所以项目一更新缓存自然失效。放在拿到项目锁之后：此刻没人在
        # 更新这个目录，算出来的指纹不会是半个更新中间态。
        fingerprint = await asyncio.to_thread(
            project_environment_fingerprint, root_path
        )
        if not payload.force:
            cached_result = await asyncio.to_thread(
                load_prepared_environment, root_path, fingerprint
            )
            if cached_result is not None:
                prepared_at = str(cached_result.get("preparedAt") or "")
                append_log(
                    "项目文件自上次准备以来没有变化，沿用已就绪的运行环境"
                    + (f"（上次准备于 {prepared_at}）" if prepared_at else "")
                )
                # 命中时不推 ready 进度：没有进度可言，而那条 WS 与本次响应
                # 抢着写同一行提示，谁后到谁说了算——推了反而会把响应里带
                # MaaFramework 版本号的那句盖成一句干巴巴的「已就绪」。
                return MaaFWAgentEnvPrepareOut(
                    message="MFW 运行环境已就绪",
                    data=_maafw_agent_env_prepare_data(
                        root_path, cached_result, logs, cached=True
                    ),
                )

        try:
            interface = await asyncio.to_thread(load_interface_model_cached, root_path)
        except MaaFWInterfaceLoadError as exc:
            return MaaFWAgentEnvPrepareOut(
                code=400,
                status="error",
                message=f"MFW interface 读取失败: {exc}",
                data=MaaFWAgentEnvPrepareData(path=str(root_path), logs=logs),
            )

        route = await asyncio.to_thread(
            lambda: runtime_pool_route_from_service(MaaFWRuntimePoolService())
        )
        try:
            result = await asyncio.to_thread(
                MaaFWRunnerService().prepare_project_environment,
                root_path,
                interface,
                runtime_pool_root=route.root,
                runtime_pool_id=route.pool_id,
                # worker 子进程跑在隔离 venv 里，代码要靠 PYTHONPATH 找到本仓；
                # 受监督时 cwd 是 <app-root>，源码在 <app-root>/repo/，只能用源码根
                import_paths=[SOURCE_ROOT],
                send_log=append_log,
                progress=publish_progress,
            )
        except Exception as exc:
            # 失败原因此前只活在响应体与 WS 事件里，两边都不落盘：用户报障时
            # app.log 里一行都没有，只能对着界面截图猜。准备过程的逐行日志
            # （pip 的 stderr 就在里面）一并记下来，别再丢。
            _maafw_env_logger.error(f"MFW 运行环境准备失败: {exc}")
            if logs:
                detail = "\n".join(sanitize_log_message(str(line)) for line in logs)
                _maafw_env_logger.error(f"MFW 运行环境准备日志:\n{detail}")
            publish_progress(
                {
                    "stage": "failed",
                    "status": "failed",
                    "message": f"MFW 运行环境准备失败: {exc}",
                }
            )
            return MaaFWAgentEnvPrepareOut(
                code=500,
                status="error",
                message=f"MFW 运行环境准备失败: {exc}",
                data=MaaFWAgentEnvPrepareData(path=str(root_path), logs=logs),
            )
        # 用准备流程自己回报的指纹：它在准备前后各算了一次，确认这期间项目文件
        # 没被动过；本地这份只在它没回报时兜底。
        # 写在项目锁内：写完才放行下一个准备/更新请求，免得它读到半份缓存。
        await asyncio.to_thread(
            store_prepared_environment,
            root_path,
            str(result.get("projectFingerprint") or "") or fingerprint,
            result,
        )
    finally:
        await release_project_path(reservation_key)

    publish_progress(
        {
            "stage": "ready",
            "status": "success",
            "message": "MFW 运行环境已就绪",
            "percent": 100.0,
        }
    )
    return MaaFWAgentEnvPrepareOut(
        message="MFW 运行环境已就绪",
        data=_maafw_agent_env_prepare_data(root_path, result, logs, cached=False),
    )


@router.post(
    "/m9a/tasks/available",
    tags=["M9A"],
    summary="获取 M9A 可用任务列表（排除 standalone 任务）",
    status_code=200,
)
async def get_m9a_available_tasks(script_id: str):
    """
    获取 M9A 可用任务列表（排除 standalone 任务）

    前端调用此接口获取可选择的任务列表，
    用于展示在用户编辑界面的任务选择区域。

    Args:
        script_id: M9A 脚本 ID

    Returns:
        dict: 包含任务列表的响应
    """
    from pathlib import Path

    from app.task.M9A.task_loader import M9ATaskLoader

    try:
        script_config = Config.ScriptConfig[uuid.UUID(script_id)]
        m9a_path = Path(script_config.get("Info", "Path"))
        loader = await asyncio.to_thread(M9ATaskLoader.get_cached, m9a_path)

        # 获取可用任务，并添加完整定义（包括 option 和 _option_definitions）
        available_tasks = loader.get_available_tasks()
        result_tasks = []

        for task in available_tasks:
            full_def = loader.get_full_definition(task["name"])
            if full_def:
                result_tasks.append(full_def)

        return {
            "code": 200,
            "status": "success",
            "message": f"共 {len(result_tasks)} 个可用任务",
            "data": result_tasks,
        }
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_m9a_available_tasks失败: {type(e).__name__}: {e}"
        )
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
            "data": [],
        }


@router.get(
    "/hsr/stage-options",
    tags=["HSR"],
    summary="获取 HSR 体力副本动态选项",
    response_model=HSRStageOptionsOut,
    status_code=200,
)
async def get_hsr_stage_options_api(
    scriptId: str | None = None,
    engine: Literal["M7A", "SRA"] = "M7A",
    userId: str | None = None,
    slot: Literal["main", "eow"] = "main",
) -> HSRStageOptionsOut:
    """返回 M7A/SRA 原生副本字段。

    ``userId`` 仅用于校验用户归属；``slot`` 是兼容参数，动态选项当前
    按引擎统一返回，不按 slot 生成不同结果。
    """

    try:
        if not scriptId:
            return HSRStageOptionsOut(
                code=400,
                status="error",
                message="缺少 scriptId",
            )

        script_config = _hsr_script_config(scriptId)
        if userId:
            _hsr_user_config(script_config, userId)
        from app.task.HSR.tools.api import build_stage_options

        data = HSRStageOptionsData(**build_stage_options(script_config, engine))
        option_count = sum(len(category.options) for category in data.categories)
        return HSRStageOptionsOut(
            message=f"共 {option_count} 个 HSR 体力副本选项",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_hsr_stage_options_api失败: {type(e).__name__}: {e}"
        )
        return HSRStageOptionsOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/bettergi/strategies",
    tags=["BetterGI"],
    summary="获取 BetterGI 自动战斗策略选项",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_strategies_api(scriptId: str) -> ComboBoxOut:
    """返回 BetterGI 可用自动战斗策略：内置「根据队伍自动选择」+ ``{RootPath}/User/AutoFight/*.txt`` 文件名。"""

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        names = one_dragon.list_auto_boss_strategies(root)
        data = [ComboBoxItem(label=n, value=n) for n in names]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个自动战斗策略选项",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_strategies_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/one-dragon/custom-groups",
    tags=["BetterGI"],
    summary="获取 BetterGI 一条龙自定义配置组",
    response_model=BetterGICustomGroupsOut,
    status_code=200,
)
async def get_bettergi_custom_groups_api(
    scriptId: str, userId: str = "", configName: str = "", useMasConfig: bool = False
) -> BetterGICustomGroupsOut:
    """返回指定一条龙配置里的自定义配置组（非内置 8 组）及其启用状态，供前端表格自动加载。

    ``useMasConfig=True``（用户独立配置）时以 per-user 副本为权威源（固定「MAS独立配置」
    槽位名，副本缺失按内置模板），返回该用户将写入槽位的自定义组；``userId`` 必填。
    否则（非独立模式直控）读取 BGI ``{configName}`` 实配的自定义组。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        if useMasConfig:
            if not userId:
                raise ValueError("用户独立配置下必须提供 userId")
            _bettergi_user_id(script_config, userId)
            items = one_dragon.list_user_custom_groups(
                root, scriptId, userId, one_dragon.launch_slot_name()
            )
        else:
            items = one_dragon.list_custom_groups(
                root, one_dragon.resolve_config_name(configName)
            )
        data = [BetterGICustomGroupOut(**item) for item in items]
        return BetterGICustomGroupsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个自定义配置组",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_custom_groups_api失败: {type(e).__name__}: {e}"
        )
        return BetterGICustomGroupsOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/one-dragon/configs",
    tags=["BetterGI"],
    summary="获取 BetterGI 一条龙配置名列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_one_dragon_configs_api(scriptId: str) -> ComboBoxOut:
    """返回 BetterGI 可选一条龙配置名：{RootPath}/User/OneDragon/*.json 文件名（默认配置置顶）。"""

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        names = one_dragon.list_one_dragon_configs(root)
        data = [ComboBoxItem(label=n, value=n) for n in names]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个一条龙配置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_one_dragon_configs_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/js-scripts",
    tags=["BetterGI"],
    summary="获取 BetterGI 可用自定义 JS 脚本列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_js_scripts_api(scriptId: str) -> ComboBoxOut:
    """返回 BetterGI 可执行自定义 JS 脚本候选。

    ``label`` 为 ``manifest.json`` 的中文显示名（目录名常为英文，如
    ``AAA-Artifacts-Bulk-Supply`` → 「AAA狗粮批发」）；``value`` 为脚本**目录名**
    （BetterGI 一条龙按目录名定位任务，落库与执行都用它）。
    供一条龙「添加配置组」弹窗作为候选（贴 JS 标签）选择。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        items = one_dragon.list_js_scripts(root)
        data = [ComboBoxItem(label=display, value=folder) for folder, display in items]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个自定义 JS 脚本",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_js_scripts_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/script-groups",
    tags=["BetterGI"],
    summary="获取 BetterGI 可用配置组列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_bettergi_script_groups_api(
    scriptId: str, userId: str = ""
) -> ComboBoxOut:
    """返回 BetterGI 配置组候选：BGI ``User/ScriptGroup/*.json`` 文件名；带 userId 时并集该用户 per-user 副本名。

    BetterGI 的「配置组」（GUI 中可加入一条龙的自定义任务组）以独立 json 保存于
    ``User/ScriptGroup``，文件名（不含 ``.json``）即组名，与一条龙 TaskDefinitions
    的引用名一致。每次调用实时扫描，供「添加配置组」弹窗「配置组」标签页展示。

    ``userId`` 非空时把该用户的 per-user ScriptGroup 副本名一并并入（副本是 MAS
    独立配置的权威内容源，复制自 JS/路径等来源的新组也只存在于副本目录，需要能被
    识别/展示为配置组）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        names = one_dragon.list_script_groups(root)
        if userId:
            _bettergi_user_id(script_config, userId)
            copy_names = one_dragon.list_user_script_group_names(scriptId, userId)
            merged: list[str] = []
            for name in (*copy_names, *names):
                if name and name not in merged:
                    merged.append(name)
            names = merged
        data = [ComboBoxItem(label=name, value=name) for name in names]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个配置组",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_groups_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/script-group/detail",
    tags=["BetterGI"],
    summary="获取 BetterGI 配置组 json 详情（per-user 副本优先）",
    response_model=BetterGIScriptGroupDetailOut,
    status_code=200,
)
async def get_bettergi_script_group_detail_api(
    scriptId: str, userId: str, name: str
) -> BetterGIScriptGroupDetailOut:
    """返回某用户的配置组 json（per-user 副本 → BGI 实配的种子顺序）。

    右栏「配置组」标签页选中 scriptgroup 时，据此列出其 json 内 ``projects`` 的
    每个项目；也供 JS/路径等单项目组展示（项目名=组名）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        _bettergi_user_id(script_config, userId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        data = one_dragon.read_user_script_group(root, scriptId, userId, name)
        if not data:
            return BetterGIScriptGroupDetailOut(
                code=404,
                status="error",
                message=f"配置组 {name} 不存在或内容为空",
                data={},
            )
        return BetterGIScriptGroupDetailOut(
            code=200,
            status="success",
            message=f"配置组 {name} 读取成功",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_group_detail_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIScriptGroupDetailOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )


@router.get(
    "/bettergi/script-settings-ui",
    tags=["BetterGI"],
    summary="获取 BetterGI 某 JsScript 脚本目录的 settings.json UI 定义",
    response_model=BetterGIScriptSettingsUiOut,
    status_code=200,
)
async def get_bettergi_script_settings_ui_api(
    scriptId: str, folder: str
) -> BetterGIScriptSettingsUiOut:
    """返回某脚本目录（User/JsScript/{folder}/）的 settings.json UI 定义数组。

    双击配置组内某项目（其 folderName 即脚本目录名）时，前端据此渲染设置弹窗表单。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        ui = one_dragon.list_script_settings_ui(root, folder)
        return BetterGIScriptSettingsUiOut(
            code=200,
            status="success",
            message=f"脚本 {folder} 共 {len(ui)} 个设置项",
            data=ui,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_settings_ui_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIScriptSettingsUiOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/bettergi/script-readme",
    tags=["BetterGI"],
    summary="获取 BetterGI 某 JsScript 脚本目录的 README 内容",
    response_model=BetterGIScriptReadmeOut,
    status_code=200,
)
async def get_bettergi_script_readme_api(
    scriptId: str, folder: str
) -> BetterGIScriptReadmeOut:
    """返回某脚本目录（User/JsScript/{folder}/）的 README 纯文本。

    双击配置组内某项目设置弹窗的「脚本说明」标签页展示。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        text = one_dragon.read_script_readme(root, folder)
        return BetterGIScriptReadmeOut(
            code=200,
            status="success",
            message="已读取脚本说明" if text else "该脚本无说明文件",
            data=text,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_readme_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIScriptReadmeOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data="",
        )


@router.get(
    "/bettergi/dirs",
    tags=["BetterGI"],
    summary="获取 BetterGI 常用目录（脚本仓库 / JsScript / AutoPathing）",
    response_model=BetterGIScriptDirsOut,
    status_code=200,
)
async def get_bettergi_script_dirs_api(scriptId: str) -> BetterGIScriptDirsOut:
    """返回 BetterGI 三个常用目录的绝对路径，供「添加配置组」弹窗的打开目录按钮使用。"""

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        dirs = one_dragon.resolve_script_dirs(root)
        return BetterGIScriptDirsOut(
            code=200,
            status="success",
            message="目录解析成功",
            repoDir=dirs.get("repo"),
            jsScriptDir=dirs.get("jsScript"),
            autoPathingDir=dirs.get("autoPathing"),
            oneDragonDir=dirs.get("oneDragon"),
            scriptGroupDir=dirs.get("scriptGroup"),
            exePath=dirs.get("exe"),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_script_dirs_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIScriptDirsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            repoDir=None,
            jsScriptDir=None,
            autoPathingDir=None,
            oneDragonDir=None,
            scriptGroupDir=None,
            exePath=None,
        )


@router.get(
    "/bettergi/auto-pathing-tree",
    tags=["BetterGI"],
    summary="获取 BetterGI 地图追踪目录树",
    response_model=BetterGIPathingTreeOut,
    status_code=200,
)
async def get_bettergi_auto_pathing_tree_api(scriptId: str) -> BetterGIPathingTreeOut:
    """返回 BetterGI 地图追踪目录树：{RootPath}/User/AutoPathing 的递归结构。

    节点：``{name, dirs, files}``，``files`` 为路径文件名（不含 ``.json``、含相对目录前缀），
    全局唯一。供「添加配置组」弹窗「地图追踪」标签页左树右表浏览。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        root_dir, tree = one_dragon.build_auto_pathing_tree(root)
        return BetterGIPathingTreeOut(
            code=200,
            status="success",
            message="地图追踪目录树加载成功",
            root=root_dir,
            dirs=[BetterGIPathingNode(**node) for node in tree],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_auto_pathing_tree_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIPathingTreeOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            root=None,
            dirs=[],
        )


@router.get(
    "/bettergi/one-dragon/settings",
    tags=["BetterGI"],
    summary="获取 BetterGI 一条龙设置项（右栏按任务分组展示）",
    response_model=BetterGIOneDragonSettingsOut,
    status_code=200,
)
async def get_bettergi_one_dragon_settings_api(
    scriptId: str, userId: str, configName: str = "", groupName: str = ""
) -> BetterGIOneDragonSettingsOut:
    """返回某用户一条龙配置的设置项（per-user 副本 → BGI 实配 → 内置模板的种子顺序）。

    供右栏按任务分组渲染并回显该任务在 BGI 一条龙里的可设置字段。
    ``groupName`` 为右栏当前编辑的内置组名，战斗 4 项 Plan 回显按其查映射，
    缺省/不匹配时跳过 Plan 回显。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        _bettergi_user_id(script_config, userId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        data = one_dragon.read_user_one_dragon_settings(
            root, scriptId, userId, configName
        )
        # 战斗4项：用 Plan 中的执行层参数回显右栏（原生副本已不再存这些字段）。
        # 第三参必须传 groupName（内置组名），传 configName 会导致 Plan 回显失效。
        data = _read_combat_from_plan(script_config, userId, groupName, "dragon", data)
        return BetterGIOneDragonSettingsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 项一条龙设置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_one_dragon_settings_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIOneDragonSettingsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )


@router.post(
    "/bettergi/one-dragon/settings",
    tags=["BetterGI"],
    summary="保存 BetterGI 一条龙设置项到 per-user 副本",
    response_model=OutBase,
    status_code=200,
)
async def save_bettergi_one_dragon_settings_api(
    req: BetterGIOneDragonSettingsIn = Body(...),
) -> OutBase:
    """把右栏编辑的设置项写回该用户一条龙配置副本（不触碰 BGI 同名实配）。"""

    try:
        script_config = _bettergi_script_config(req.scriptId)
        _bettergi_user_id(script_config, req.userId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        # 战斗4项：可映射字段仅写 Plan，不可映射字段（如每周秘境表）仍落原生副本。
        # 注意第三参是「右栏当前编辑的内置组名」（前端 groupName），绝不能传 configName——
        # RIGHTBAR_TO_PLAN 按组名（自动秘境/自动地脉花…）查映射，传配置名会导致
        # Plan 路由静默失效，周表/每日行等白名单外键（StrategyName/leyLineDailyEnabled/
        # team/country/LeyLineDefault* 等）全部丢弃。
        native_leftover, new_plan = _route_combat_to_plan(
            script_config, req.userId, req.groupName, req.settings, "dragon"
        )
        if new_plan is not None:
            user_config = _bettergi_user_config(script_config, req.userId)
            await user_config.set("OneDragon", "Plan", new_plan)
        if native_leftover:
            one_dragon.write_user_one_dragon_settings(
                root, req.scriptId, req.userId, req.configName, native_leftover
            )
        return OutBase(
            code=200,
            status="success",
            message=f"已保存 {len(req.settings)} 项一条龙设置",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_bettergi_one_dragon_settings_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/bettergi/one-dragon/plan/step-enabled",
    tags=["BetterGI"],
    summary="设置一条龙 Plan 某步骤的启用状态（按实例名，支持 基名-后缀）",
    response_model=OutBase,
    status_code=200,
)
async def set_one_dragon_plan_step_enabled(
    scriptId: str = Query(...),
    userId: str = Query(...),
    name: str = Query(...),
    enabled: bool = Query(True),
) -> OutBase:
    """按步骤名翻转 Plan 中某战斗实例的启用状态（同组多实例各自独立启停）。

    步骤名由行实例 uid 决定（形如 ``自动秘境`` / ``自动秘境-3``），与前端展示用的
    「后名」解耦，改名不会丢设置。仅写入执行层消费的 enabled 标记，不影响原生
    一条龙副本；运行时 build_combat_steps 按 step.enabled 决定是否纳入执行层。

    步骤不存在时（刚另存为/复制出来的新实例）先创建再设启用——否则开关只改前端、
    后端无步骤可写，刷新后回退。
    """
    from app.task.BetterGI.tools import one_dragon_plan

    try:
        script_config = _bettergi_script_config(scriptId)
        _bettergi_user_id(script_config, userId)
        user_config = _bettergi_user_config(script_config, userId)
        plan = one_dragon_plan.parse_one_dragon_plan(
            user_config.get("OneDragon", "Plan") or ""
        )
        target = next((s for s in plan if s.get("name") == name), None)
        if target is None:
            plan.append(
                {
                    "uid": uuid.uuid4().hex[:12],
                    "kind": "builtin",
                    "name": name,
                    "enabled": enabled,
                    "settings": {},
                }
            )
        else:
            target["enabled"] = enabled
        await user_config.set("OneDragon", "Plan", one_dragon_plan.plan_to_json(plan))
        return OutBase(
            code=200,
            status="success",
            message=f"已更新步骤 {name} 启用={enabled}",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_one_dragon_plan_step_enabled失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/bettergi/global-domain/settings",
    tags=["BetterGI"],
    summary="获取 BetterGI 全局 config.json 的秘境刷取配置段",
    response_model=BetterGIGlobalDomainSettingsOut,
    status_code=200,
)
async def get_bettergi_global_domain_settings_api(
    scriptId: str, userId: str = "", groupName: str = ""
) -> BetterGIGlobalDomainSettingsOut:
    """返回秘境刷取配置（领奖树脂/分解圣遗物/奖励识别）。

    ``userId`` 非空时以该用户 per-user 副本为权威源（副本缺失回退 BGI 全局实配），
    使独立配置下每个用户的秘境刷取设置互不影响；``userId`` 为空（直控模式）读
    BGI 全局 config.json（autoDomainConfig/autoArtifactSalvageConfig，camelCase）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        if userId:
            _bettergi_user_id(script_config, userId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        data = (
            one_dragon.read_user_global_domain_settings(root, scriptId, userId)
            if userId
            else one_dragon.read_global_domain_settings(root)
        )
        # 战斗4项（自动秘境）的可映射字段（领奖树脂/分解圣遗物/奖励识别等）在 Plan 中回显
        if userId:
            data = _read_combat_from_plan(script_config, userId, groupName, "globalDomain", data)
        return BetterGIGlobalDomainSettingsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 项秘境刷取配置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_global_domain_settings_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIGlobalDomainSettingsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )


@router.post(
    "/bettergi/global-domain/settings",
    tags=["BetterGI"],
    summary="保存 BetterGI 全局 config.json 的秘境刷取配置段",
    response_model=OutBase,
    status_code=200,
)
async def save_bettergi_global_domain_settings_api(
    req: BetterGIGlobalDomainSettingsIn = Body(...),
) -> OutBase:
    """把右栏秘境刷取配置写回 per-user 副本；userId 为空（直控模式）写 BGI 全局 config.json。"""

    try:
        script_config = _bettergi_script_config(req.scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        if req.userId:
            _bettergi_user_id(script_config, req.userId)
            # 战斗4项（自动秘境）可映射字段仅写 Plan；maxArtifactStar 等全局共享字段仍落副本
            native_leftover, new_plan = _route_combat_to_plan(
                script_config, req.userId, req.groupName, req.settings, "globalDomain"
            )
            if new_plan is not None:
                user_config = _bettergi_user_config(script_config, req.userId)
                await user_config.set("OneDragon", "Plan", new_plan)
            if native_leftover:
                one_dragon.write_user_global_domain_settings(
                    req.scriptId, req.userId, native_leftover
                )
        else:
            one_dragon.write_global_domain_settings(root, req.settings)
        return OutBase(
            code=200,
            status="success",
            message=f"已保存 {len(req.settings)} 项秘境刷取配置",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_bettergi_global_domain_settings_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/bettergi/global-stygian/settings",
    tags=["BetterGI"],
    summary="获取 BetterGI 全局 config.json 的自动幽境危战设置段",
    response_model=BetterGIGlobalStygianSettingsOut,
    status_code=200,
)
async def get_bettergi_global_stygian_settings_api(
    scriptId: str, userId: str = "", groupName: str = ""
) -> BetterGIGlobalStygianSettingsOut:
    """返回自动幽境危战设置（刷取战场/战斗队伍/战斗策略/次数与树脂）。

    ``userId`` 非空时以该用户 per-user 副本为权威源（副本缺失回退 BGI 全局实配），
    使独立配置下每个用户的幽境设置互不影响；``userId`` 为空（直控模式）读
    BGI 全局 config.json（autoStygianOnslaughtConfig 段，camelCase）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        if userId:
            _bettergi_user_id(script_config, userId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        data = (
            one_dragon.read_user_global_stygian_settings(root, scriptId, userId)
            if userId
            else one_dragon.read_global_stygian_settings(root)
        )
        # 战斗4项（自动幽境危战）全部字段在 Plan 中回显
        if userId:
            data = _read_combat_from_plan(script_config, userId, groupName, "globalStygian", data)
        return BetterGIGlobalStygianSettingsOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 项幽境危战设置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_bettergi_global_stygian_settings_api失败: {type(e).__name__}: {e}"
        )
        return BetterGIGlobalStygianSettingsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )


@router.post(
    "/bettergi/global-stygian/settings",
    tags=["BetterGI"],
    summary="保存 BetterGI 全局 config.json 的自动幽境危战设置段",
    response_model=OutBase,
    status_code=200,
)
async def save_bettergi_global_stygian_settings_api(
    req: BetterGIGlobalStygianSettingsIn = Body(...),
) -> OutBase:
    """把右栏自动幽境危战设置写回 per-user 副本；userId 为空（直控模式）写 BGI 全局 config.json。"""

    try:
        script_config = _bettergi_script_config(req.scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        if req.userId:
            _bettergi_user_id(script_config, req.userId)
            # 战斗4项（自动幽境危战）全部字段仅写 Plan，不再落全局副本
            native_leftover, new_plan = _route_combat_to_plan(
                script_config, req.userId, req.groupName, req.settings, "globalStygian"
            )
            if new_plan is not None:
                user_config = _bettergi_user_config(script_config, req.userId)
                await user_config.set("OneDragon", "Plan", new_plan)
            if native_leftover:
                one_dragon.write_user_global_stygian_settings(
                    req.scriptId, req.userId, native_leftover
                )
        else:
            one_dragon.write_global_stygian_settings(root, req.settings)
        return OutBase(
            code=200,
            status="success",
            message=f"已保存 {len(req.settings)} 项幽境危战设置",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_bettergi_global_stygian_settings_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/bettergi/domain-catalog",
    tags=["BetterGI"],
    summary="获取 BetterGI 每周秘境候选与每秘境三档奖励物",
    response_model=BetterGIDomainCatalogOut,
    status_code=200,
)
async def get_bettergi_domain_catalog_api(
    scriptId: str,
) -> BetterGIDomainCatalogOut:
    """返回 BetterGI 每周秘境可选秘境目录与分档奖励物。

    数据源：官方传送点 tp.json（GameTask/AutoTrackPath/Assets/tp.json）中
    Bless/Forgery/Mastery 三类 Domain 点（含奖励物）；tp.json 缺失或为空时返回空目录。
    供「每周秘境」表格的秘境/奖励下拉联动使用（奖励仍按 BGI 语义存 0~3 序号）。
    """

    try:
        script_config = _bettergi_script_config(scriptId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        source, items = one_dragon.scan_domain_catalog(root)
        data = [BetterGIDomainCatalogItem(**item) for item in items]
        return BetterGIDomainCatalogOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个秘境",
            data=data,
            source=source or None,
        )
    except Exception as e:
        return BetterGIDomainCatalogOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
            source=None,
        )


@router.post(
    "/bettergi/script-group/save",
    tags=["BetterGI"],
    summary="保存 BetterGI 配置组 json 到 per-user 副本",
    response_model=OutBase,
    status_code=200,
)
async def save_bettergi_script_group_api(
    req: BetterGIScriptGroupSaveIn = Body(...),
) -> OutBase:
    """把右栏编辑后的配置组 json（项目顺序 + 各项目 jsScriptSettingsObject）写回
    该用户的 per-user 副本（``data/{script}/{user}/ScriptGroup/{name}.json``）。

    不触碰 BetterGI 全局 ``User/ScriptGroup/{name}.json`` 同名实配。
    """

    try:
        script_config = _bettergi_script_config(req.scriptId)
        _bettergi_user_id(script_config, req.userId)
        root = Path(script_config.get("Info", "RootPath")).expanduser()
        from app.task.BetterGI.tools import one_dragon

        projects = (req.data or {}).get("projects")
        if not isinstance(projects, list):
            raise ValueError("projects 必须为数组（按执行顺序的项目列表）")
        out = one_dragon.write_user_script_group(
            root, req.scriptId, req.userId, req.name, req.data
        )
        return OutBase(
            code=200,
            status="success",
            message=f"已保存配置组 {req.name}（共 {len(projects)} 个项目）到用户配置",
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_bettergi_script_group_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/zzzod/instances",
    tags=["ZZZ-OD"],
    summary="获取 zzz-od 实例（账号）列表",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def get_zzzod_instances_api(scriptId: str) -> ZzzOdInstancesOut:
    """返回 zzz-od 实例列表（供「快速导入」选择来源实例）。"""

    try:
        data = [
            ZzzOdInstanceOut(**item) for item in Config.get_zzzod_instances(scriptId)
        ]
        return ZzzOdInstancesOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个实例",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_instances_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


def _zzzod_instances_response(instances: list[dict]) -> ZzzOdInstancesOut:
    """把服务层实例列表包装为统一响应（供直控实例管理各操作复用）。"""

    data = [ZzzOdInstanceOut(**item) for item in instances]
    return ZzzOdInstancesOut(
        code=200,
        status="success",
        message=f"共 {len(data)} 个实例",
        data=data,
    )


@router.post(
    "/zzzod/instances/add",
    tags=["ZZZ-OD"],
    summary="新建一条龙实例（直控实例管理）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def add_zzzod_instance_api(
    body: ZzzOdInstanceAddIn = Body(...),
) -> ZzzOdInstancesOut:
    """创建实例（最小空闲槽，避开原生与跨脚本 MAS 绑定槽），返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.add_zzzod_instance(body.scriptId, body.name)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"add_zzzod_instance_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/rename",
    tags=["ZZZ-OD"],
    summary="重命名一条龙实例（直控实例管理）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def rename_zzzod_instance_api(
    body: ZzzOdInstanceRenameIn = Body(...),
) -> ZzzOdInstancesOut:
    """只改注册表 name（实例目录不变），返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.rename_zzzod_instance(
                body.scriptId, body.instanceIdx, body.name
            )
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"rename_zzzod_instance_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/active-in-od",
    tags=["ZZZ-OD"],
    summary="切换实例是否参与「全部实例」运行（直控实例管理）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def set_zzzod_instance_active_in_od_api(
    body: ZzzOdInstanceFlagIn = Body(...),
) -> ZzzOdInstancesOut:
    """切换 active_in_od 标志位，返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.set_zzzod_instance_active_in_od(
                body.scriptId, body.instanceIdx, body.activeInOd
            )
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_zzzod_instance_active_in_od_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/set-active",
    tags=["ZZZ-OD"],
    summary="把所选实例设为当前活跃（直控「选择即运行」）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def set_zzzod_active_instance_api(
    body: ZzzOdInstanceActiveIn = Body(...),
) -> ZzzOdInstancesOut:
    """把目标实例设为注册表 active（其余清 False），返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.set_zzzod_instance_active(body.scriptId, body.instanceIdx)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_zzzod_active_instance_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/force-login",
    tags=["ZZZ-OD"],
    summary="切换实例「运行前切换账号」（直控实例管理；一条龙原生能力）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def set_zzzod_instance_force_login_api(
    body: ZzzOdInstanceForceLoginIn = Body(...),
) -> ZzzOdInstancesOut:
    """切换实例条目的 force_login_before_run（一条龙自己消费），返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.set_zzzod_instance_force_login(
                body.scriptId, body.instanceIdx, body.forceLogin
            )
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_zzzod_instance_force_login_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/zzzod/instances/run-mode",
    tags=["ZZZ-OD"],
    summary="设置运行实例（直控；one_dragon.yml 全局 instance_run）",
    response_model=OutBase,
    status_code=200,
)
async def set_zzzod_instance_run_mode_api(
    body: ZzzOdInstanceRunModeIn = Body(...),
) -> OutBase:
    """白名单校验后写回全局 instance_run（与直控页当前编辑哪个实例无关）。"""

    try:
        Config.set_zzzod_instance_run_mode(body.scriptId, body.instanceRun)
        return OutBase()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_zzzod_instance_run_mode_api失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/zzzod/instances/delete",
    tags=["ZZZ-OD"],
    summary="删除一条龙实例（直控实例管理；受 MAS 绑定槽保护）",
    response_model=ZzzOdInstancesOut,
    status_code=200,
)
async def delete_zzzod_instance_api(
    body: ZzzOdInstanceDeleteIn = Body(...),
) -> ZzzOdInstancesOut:
    """删除注册表条目与实例目录，返回更新后的实例列表。"""

    try:
        return _zzzod_instances_response(
            Config.delete_zzzod_instance(body.scriptId, body.instanceIdx)
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_zzzod_instance_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdInstancesOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/zzzod/teams",
    tags=["ZZZ-OD"],
    summary="获取预备编队列表（名称 + 绑定配队方案）",
    response_model=ZzzOdTeamsOut,
    status_code=200,
)
async def get_zzzod_teams_api(
    scriptId: str,
    userId: str,
    instanceIdx: int | None = None,
) -> ZzzOdTeamsOut:
    """读绑定槽（直控传 instanceIdx 读原生实例）的 team.yml（固定 20 个编队）。"""

    try:
        data = await Config.get_zzzod_teams(scriptId, userId, instance_idx=instanceIdx)
        return ZzzOdTeamsOut(
            code=200,
            status="success",
            message="操作成功",
            teams=[ZzzOdTeamItemOut(**t) for t in data["teams"]],
            autoBattle=data["autoBattle"],
            agentOptions=data["agentOptions"],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_teams_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdTeamsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            teams=[],
            autoBattle=[],
        )


@router.post(
    "/zzzod/teams/save",
    tags=["ZZZ-OD"],
    summary="整表保存预备编队（名称 + 绑定配队方案；成员按行保留）",
    response_model=ZzzOdTeamsSaveOut,
    status_code=200,
)
async def save_zzzod_teams_api(script: ZzzOdTeamsSaveIn = Body(...)) -> ZzzOdTeamsSaveOut:
    """直控传 instanceIdx 直接写原生实例，缺省写用户绑定槽。"""

    try:
        saved = await Config.save_zzzod_teams(
            script.scriptId,
            script.userId,
            script.teams,
            instance_idx=script.instanceIdx,
        )
        return ZzzOdTeamsSaveOut(
            code=200,
            status="success",
            message="编队已保存",
            teams=[
                ZzzOdTeamItemOut(
                    idx=i,
                    name=str(item.get("name") or ""),
                    autoBattle=str(item.get("auto_battle") or ""),
                    agents=[str(a) for a in item.get("agent_id_list") or []],
                )
                for i, item in enumerate(saved)
            ],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_zzzod_teams_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdTeamsSaveOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            teams=[],
        )


@router.get(
    "/zzzod/catalog",
    tags=["ZZZ-OD"],
    summary="获取一条龙任务目录",
    response_model=ZzzOdCatalogOut,
    status_code=200,
)
async def get_zzzod_catalog_api(scriptId: str) -> ZzzOdCatalogOut:
    """静态解析安装目录下的应用注册信息，供用户配置渲染任务卡片中文名。"""

    try:
        # 统一走 _zzzod_root 哨兵校验（空串在此解析成 cwd 的边界被封住）
        root = Config.get_zzzod_root(scriptId)
        from app.task.ZzzOd.tools import (
            get_task_app_fields,
            get_task_app_jump,
            list_app_catalog,
        )

        data = [
            ZzzOdCatalogItemOut(
                **item,
                configurable=get_task_app_fields(str(item["app_id"])) is not None,
                jump=get_task_app_jump(str(item["app_id"])),
            )
            for item in list_app_catalog(root)
        ]
        return ZzzOdCatalogOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 个任务",
            data=data,
        )
    except Exception as e:
        return ZzzOdCatalogOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.get(
    "/zzzod/app-config",
    tags=["ZZZ-OD"],
    summary="获取任务级配置（字段元数据 + 当前值）",
    response_model=ZzzOdAppConfigOut,
    status_code=200,
)
async def get_zzzod_app_config_api(
    scriptId: str,
    userId: str,
    appId: str,
    instanceIdx: int | None = None,
) -> ZzzOdAppConfigOut:
    """返回任务可配置字段、选项与当前值（直控传 instanceIdx 读原生实例，否则读绑定槽）。"""

    try:
        data = await Config.get_zzzod_app_config(
            scriptId, userId, appId, instance_idx=instanceIdx
        )
        return ZzzOdAppConfigOut(
            code=200,
            status="success",
            message="操作成功",
            appId=data["appId"],
            fields=[ZzzOdAppConfigFieldOut(**f) for f in data["fields"]],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_app_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdAppConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            appId=appId,
            fields=[],
        )


@router.get(
    "/zzzod/options",
    tags=["ZZZ-OD"],
    summary="获取任务计划的动态选项（副本级联树/配队方案/挑战配置）",
    response_model=ZzzOdTaskOptionsOut,
    status_code=200,
)
async def get_zzzod_task_options_api(scriptId: str, appId: str) -> ZzzOdTaskOptionsOut:
    """静态读取安装目录（compendium 数据 + 配置目录扫描），与一条龙原生 GUI 选项同源。"""

    try:
        data = await Config.get_zzzod_task_options(scriptId, appId)
        return ZzzOdTaskOptionsOut(
            code=200,
            status="success",
            message="操作成功",
            appId=data["appId"],
            trainCategories=data["trainCategories"],
            lostVoidMissions=data["lostVoidMissions"],
            autoBattle=data["autoBattle"],
            challenge=data["challenge"],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_task_options_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdTaskOptionsOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            appId=appId,
        )


@router.post(
    "/zzzod/app-config/save",
    tags=["ZZZ-OD"],
    summary="保存任务级配置（绑定槽；直控传 instanceIdx 直接写原生实例）",
    response_model=ZzzOdAppConfigOut,
    status_code=200,
)
async def save_zzzod_app_config_api(
    script: ZzzOdAppConfigSaveIn = Body(...),
) -> ZzzOdAppConfigOut:
    """字段白名单校验后写入 per-app YAML（缺省写用户绑定槽，直控写指定原生实例）。"""

    try:
        data = await Config.save_zzzod_app_config(
            script.scriptId,
            script.userId,
            script.appId,
            script.values,
            instance_idx=script.instanceIdx,
        )
        return ZzzOdAppConfigOut(
            code=200,
            status="success",
            message="配置已保存",
            appId=script.appId,
            fields=[
                ZzzOdAppConfigFieldOut(
                    field=str(k), title=str(k), value=str(v), options=[]
                )
                for k, v in data.items()
            ],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_zzzod_app_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdAppConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            appId=script.appId,
            fields=[],
        )


@router.get(
    "/zzzod/native-config",
    tags=["ZZZ-OD"],
    summary="获取实例原生配置（直控页面表单数据）",
    response_model=ZzzOdNativeConfigOut,
    status_code=200,
)
async def get_zzzod_native_config_api(
    scriptId: str, instanceIdx: int
) -> ZzzOdNativeConfigOut:
    """读取所选实例 game_account.yml 与 _group.yml（含默认值合并与任务目录并入）。"""

    try:
        data = await Config.get_zzzod_native_config(scriptId, instanceIdx)
        return ZzzOdNativeConfigOut(
            code=200,
            status="success",
            message="操作成功",
            instanceIdx=data["instanceIdx"],
            instanceName=data["instanceName"],
            account=[ZzzOdNativeAccountField(**f) for f in data["account"]],
            tasks=[ZzzOdNativeTaskOut(**t) for t in data["tasks"]],
            instanceRun=data["instanceRun"],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_native_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdNativeConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instanceIdx=instanceIdx,
            instanceName="",
            account=[],
            tasks=[],
            instanceRun="仅运行当前",
        )


@router.post(
    "/zzzod/native-config/save",
    tags=["ZZZ-OD"],
    summary="保存实例原生配置（直控模式直接写回一条龙原始 YAML）",
    response_model=ZzzOdNativeConfigOut,
    status_code=200,
)
async def save_zzzod_native_config_api(
    script: ZzzOdNativeConfigIn = Body(...),
) -> ZzzOdNativeConfigOut:
    """白名单过滤后写回所选实例 game_account.yml、_group.yml 与 instance_run，随后回读最新数据。"""

    try:
        await Config.save_zzzod_native_config(
            script.scriptId,
            script.instanceIdx,
            script.account,
            [t.model_dump() for t in script.tasks]
            if script.tasks is not None
            else None,
            script.instanceRun,
        )
        data = await Config.get_zzzod_native_config(
            script.scriptId, script.instanceIdx
        )
        return ZzzOdNativeConfigOut(
            code=200,
            status="success",
            message="配置已保存到一条龙原生配置",
            instanceIdx=data["instanceIdx"],
            instanceName=data["instanceName"],
            account=[ZzzOdNativeAccountField(**f) for f in data["account"]],
            tasks=[ZzzOdNativeTaskOut(**t) for t in data["tasks"]],
            instanceRun=data["instanceRun"],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"save_zzzod_native_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdNativeConfigOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instanceIdx=script.instanceIdx,
            instanceName="",
            account=[],
            tasks=[],
            instanceRun="仅运行当前",
        )


@router.get(
    "/zzzod/launchers",
    tags=["ZZZ-OD"],
    summary="获取一条龙两种启动器的安装情况与默认项",
    response_model=ZzzOdLauncherOut,
    status_code=200,
)
async def get_zzzod_launchers_api(scriptId: str) -> ZzzOdLauncherOut:
    """渲染「启动器」下拉用（直控/用户两态通用）：未安装的启动器选项禁用变灰。"""

    try:
        data = Config.get_zzzod_launchers(scriptId)
        return ZzzOdLauncherOut(code=200, status="success", message="", **data)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_zzzod_launchers_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdLauncherOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            original_available=False,
            integrated_available=False,
        )


@router.post(
    "/zzzod/import",
    tags=["ZZZ-OD"],
    summary="基于一条龙已有实例快速生成当前用户配置（覆盖前自动归档当前配置）",
    response_model=ZzzOdImportOut,
    status_code=200,
)
async def import_zzzod_config_api(
    script: ZzzOdImportIn = Body(...),
) -> ZzzOdImportOut:
    """把来源实例的账号信息与已启用任务编排写入本用户；覆盖前强制归档当前 MAS 槽配置，
    导入前状态可在「配置恢复」中找回。"""

    try:
        data = await Config.import_zzzod_config(
            script.scriptId, script.userId, script.instanceIdx
        )
        return ZzzOdImportOut(
            code=200,
            status="success",
            message="已基于所选实例生成用户配置",
            **data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_zzzod_config_api失败: {type(e).__name__}: {e}"
        )
        return ZzzOdImportOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            instanceIdx=-1,
            instanceName="",
            importedAccountCount=0,
            importedTaskCount=0,
            slot=-1,
        )


@router.get(
    "/hsr/capabilities",
    tags=["HSR"],
    summary="获取内置 HSR 能力快照",
    response_model=HSRCapabilitiesOut,
    status_code=200,
)
async def get_hsr_capabilities_api(scriptId: str | None = None) -> HSRCapabilitiesOut:
    """返回内置 HSR 的能力快照，不暴露原生编辑器会话。"""

    try:
        if not scriptId:
            return HSRCapabilitiesOut(code=400, status="error", message="缺少 scriptId")
        script_config = _hsr_script_config(scriptId)
        from app.task.HSR.tools.api import build_capabilities

        # 走线程：里面要起一次 SRA-cli.exe --version 读版本号，正常 0.09 秒，
        # 但异常构建或杀毒扫描时能卡到超时，直接调会连 WebSocket 一起冻住。
        data = HSRCapabilitiesData(
            **await asyncio.to_thread(build_capabilities, script_config)
        )
        return HSRCapabilitiesOut(data=data)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_hsr_capabilities_api失败: {type(e).__name__}: {e}"
        )
        return HSRCapabilitiesOut(
            code=400
            if isinstance(
                e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError)
            )
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/hsr/update",
    tags=["HSR"],
    summary="检查或执行 HSR 外部脚本更新",
    response_model=HSRUpdateOut,
    status_code=200,
)
async def post_hsr_update_api(data: HSRUpdateIn) -> HSRUpdateOut:
    """手动检查或安装 M7A / SRA 的更新。

    自动更新只在任务正常跑完后触发（``Update.AutoUpdateMode = AfterRun``），
    这个接口是唯一不必等一轮任务就能更新的入口。
    """

    try:
        script_config = _hsr_script_config(data.scriptId)
        from app.task.HSR.tools.native_control import resolve_script_path
        from app.task.HSR.tools.update import (
            check_engine_update,
            update_engine_if_needed,
        )

        root = resolve_script_path(script_config, data.engine)
        if not root:
            return HSRUpdateOut(
                code=400, status="error", message=f"未配置 {data.engine} 路径"
            )

        source = str(script_config.get("Update", f"{data.engine}Source") or "")
        channel = str(script_config.get("Update", "Channel") or "stable")
        cdk = str(script_config.get("Update", "MirrorChyanCDK") or "")

        if data.action == "check":
            result = await check_engine_update(
                data.engine,
                Path(root),
                source=source,
                channel=channel,
                cdk=cdk,
                proxy=Config.proxy,
            )
            return HSRUpdateOut(
                data=HSRUpdateData(
                    engine=data.engine,
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
                resolve_external_lock_paths(script_config, (data.engine,)),
                wait=False,
            )
        except HSRExternalPathBusyError as e:
            return HSRUpdateOut(code=409, status="error", message=str(e))

        try:
            outcome = await update_engine_if_needed(
                data.engine,
                Path(root),
                source=source,
                channel=channel,
                cdk=cdk,
                proxy=Config.proxy,
                download_dir=Path.cwd() / "data" / "hsr_update",
            )
        finally:
            lease.release()

        return HSRUpdateOut(
            data=HSRUpdateData(
                engine=data.engine,
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
        return HSRUpdateOut(
            code=400
            if isinstance(
                e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError)
            )
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/hsr/managed-config",
    tags=["HSR"],
    summary="获取 HSR 托管配置字段",
    response_model=HSRManagedConfigOut,
    status_code=200,
)
async def get_hsr_managed_config_api(
    scriptId: str | None = None, userId: str | None = None
) -> HSRManagedConfigOut:
    """返回原生动态托管字段；用户 ID 只负责归属校验。"""

    try:
        if not scriptId:
            return HSRManagedConfigOut(
                code=400, status="error", message="缺少 scriptId"
            )
        script_config = _hsr_script_config(scriptId)
        user_config = None
        if userId:
            user_config = _hsr_user_config(script_config, userId)
        from app.task.HSR.tools.api import build_managed_config

        data = HSRManagedConfigData(**build_managed_config(script_config, user_config))
        return HSRManagedConfigOut(data=data)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_hsr_managed_config_api失败: {type(e).__name__}: {e}"
        )
        return HSRManagedConfigOut(
            code=400
            if isinstance(
                e, (FileNotFoundError, OSError, RuntimeError, ValueError, KeyError)
            )
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/hsr/sra-profiles",
    tags=["HSR"],
    summary="获取 HSR 可选的 SRA 配置档案",
    response_model=HSRSRAProfilesOut,
    status_code=200,
)
async def get_hsr_sra_profiles_api(scriptId: str | None = None) -> HSRSRAProfilesOut:
    """列出 ``%APPDATA%/SRA/configs`` 下的配置档案，并标出脚本当前生效的那份。"""

    try:
        if not scriptId:
            return HSRSRAProfilesOut(code=400, status="error", message="缺少 scriptId")
        script_config = _hsr_script_config(scriptId)
        from app.task.HSR.tools.api import build_sra_profiles

        data = HSRSRAProfilesData(**build_sra_profiles(script_config))
        return HSRSRAProfilesOut(
            message=f"共 {len(data.profiles)} 份 SRA 配置档案",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_hsr_sra_profiles_api失败: {type(e).__name__}: {e}"
        )
        return HSRSRAProfilesOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/hsr/direct-config/import",
    tags=["HSR"],
    summary="导入 HSR 原生配置快照",
    response_model=HSRDirectConfigImportOut,
    status_code=200,
)
async def import_hsr_direct_config_api(
    request: HSRDirectConfigImportIn = Body(...),
) -> HSRDirectConfigImportOut:
    from app.task.HSR.tools.api import import_direct_config
    from app.task.HSR.tools.external_locks import HSRExternalPathBusyError

    try:
        script_config = _hsr_script_config(request.scriptId)
        # 先校验用户归属，再让 provider 读取原生文件，避免无效请求触碰用户配置。
        _hsr_user_config(script_config, request.userId)

        result = await import_direct_config(
            script_config,
            request.engine,
            script_id=request.scriptId,
            user_id=request.userId,
            update_user=Config.update_user,
        )
        return HSRDirectConfigImportOut(
            message=f"{request.engine} 原生配置已导入",
            data=HSRDirectConfigImportData(**result),
        )
    except HSRExternalPathBusyError as e:
        return HSRDirectConfigImportOut(
            code=409, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, RuntimeError) as e:
        return HSRDirectConfigImportOut(
            code=400, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    except OSError as e:
        return HSRDirectConfigImportOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/hsr/direct-config/clear",
    tags=["HSR"],
    summary="清除 HSR 用户的直控配置快照",
    response_model=HSRDirectConfigImportOut,
    status_code=200,
)
async def clear_hsr_direct_config_api(
    request: HSRDirectConfigImportIn = Body(...),
) -> HSRDirectConfigImportOut:
    """清掉该用户导入的快照，直控回到直接使用脚本当前原生配置。"""

    from app.task.HSR.tools.api import clear_direct_config

    try:
        script_config = _hsr_script_config(request.scriptId)
        _hsr_user_config(script_config, request.userId)

        result = await clear_direct_config(
            script_config,
            request.engine,
            script_id=request.scriptId,
            user_id=request.userId,
            update_user=Config.update_user,
        )
        return HSRDirectConfigImportOut(
            message=f"{request.engine} 已改回使用脚本当前配置",
            data=HSRDirectConfigImportData(**result),
        )
    except (KeyError, TypeError, ValueError) as e:
        return HSRDirectConfigImportOut(
            code=400, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    except OSError as e:
        return HSRDirectConfigImportOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/oknte/configs/list",
    tags=["OKNTE"],
    summary="获取 OK-NTE 配置文件列表及 schema",
    status_code=200,
)
async def get_oknte_configs_list(script_id: str, user_id: str):
    """
    获取 OK-NTE 配置文件列表及 schema 定义。
    读写用户配置目录（data/{script_id}/{user_id}/ConfigFile/），
    若为空则自动从 ok-nte configs 目录初始化默认配置。

    Args:
        script_id: OK-NTE 脚本 ID
        user_id: 用户 ID

    Returns:
        dict: 包含配置文件列表和 schema 的响应
    """
    try:
        import json
        import shutil

        from app.task.OkNte.config_schema import (
            build_fields_for_config,
            ensure_oknte_daily_routine_configs,
            get_all_config_info,
            load_oknte_option_labels,
        )

        _, script_config = _oknte_script_config(script_id)

        # 从 ok-nte 安装目录加载翻译 → option_labels
        root_path = script_config.get("Info", "RootPath")
        option_labels = load_oknte_option_labels(root_path) if root_path else {}

        # 用户配置目录；旧版 Default 目录仅作为升级后的初始化来源。
        mas_config_dir = _oknte_mas_config_dir(script_id, user_id)

        # ok-nte 源配置目录（用于自动初始化）
        legacy_config_dir = _oknte_legacy_mas_config_dir(script_id)
        oknte_configs_dir = (
            legacy_config_dir
            if legacy_config_dir.is_dir() and any(legacy_config_dir.iterdir())
            else None
        )
        if oknte_configs_dir is None:
            raw_config_path = script_config.get("Script", "ConfigPath")
            oknte_configs_dir = Path(raw_config_path) if raw_config_path else None
        if not oknte_configs_dir or not oknte_configs_dir.exists():
            if root_path:
                root = Path(root_path)
                packaged_dir = root / "data" / "apps" / "ok-nte" / "working" / "configs"
                source_dir = root / "configs"
                oknte_configs_dir = (
                    packaged_dir if packaged_dir.is_dir() else source_dir
                )

        # 自动初始化：用户目录为空时从旧版共享目录或 ok-nte configs 复制默认配置
        need_init = not mas_config_dir.exists() or not any(mas_config_dir.iterdir())
        if need_init and oknte_configs_dir and oknte_configs_dir.is_dir():
            mas_config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(oknte_configs_dir, mas_config_dir, dirs_exist_ok=True)
        mas_config_dir.mkdir(parents=True, exist_ok=True)
        ensure_oknte_daily_routine_configs(mas_config_dir)

        configs_info = get_all_config_info()

        # 读取 per-user JSON 配置，通过 build_fields_for_config 构建字段列表
        result = []
        for info in configs_info:
            filename = info["filename"]
            filepath = _oknte_config_file_path(mas_config_dir, filename)
            current_data: dict[str, Any] = {}
            parse_error = False
            if filepath.exists():
                try:
                    current_data = json.loads(filepath.read_text(encoding="utf-8"))
                except Exception as e:
                    # 解析失败按空数据构建字段, 但要让前端知道这份配置没读出来
                    parse_error = True
                    logger.warning(
                        f"OkNte 配置解析失败: {filepath}: {type(e).__name__}: {e}"
                    )

            fields = build_fields_for_config(filename, current_data, option_labels)

            result.append(
                {
                    **info,
                    "fields": fields,
                    "currentData": current_data,
                    "parseError": parse_error,
                }
            )

        return {
            "code": 200,
            "status": "success",
            "message": f"共 {len(result)} 个配置文件",
            "data": result,
            "optionLabels": option_labels,
            "configPath": str(mas_config_dir) if mas_config_dir else None,
        }
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_oknte_configs_list失败: {type(e).__name__}: {e}"
        )
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
            "data": [],
        }


@router.post(
    "/oknte/configs/batch-update",
    tags=["OKNTE"],
    summary="批量更新 OK-NTE 配置文件",
    status_code=200,
)
async def batch_update_oknte_configs(
    script_id: str = Body(...),
    user_id: str = Body(...),
    configs: dict = Body(...),
):
    """
    批量更新 OK-NTE 配置文件

    Args:
        script_id: OK-NTE 脚本 ID
        user_id: 用户 ID
        configs: { filename: data } 格式的配置数据

    Returns:
        dict: 操作结果
    """
    try:
        from app.task.OkNte.config_schema import update_oknte_config_data

        # 写入用户配置目录
        mas_config_dir = _oknte_mas_config_dir(script_id, user_id)
        mas_config_dir.mkdir(parents=True, exist_ok=True)

        updated_files = []
        for filename, data in configs.items():
            filepath = _oknte_config_file_path(mas_config_dir, filename)
            update_oknte_config_data(filepath, data)
            updated_files.append(filename)

        return {
            "code": 200,
            "status": "success",
            "message": f"已更新 {len(updated_files)} 个配置文件",
            "data": updated_files,
        }
    except Exception as e:
        logger.opt(exception=True).warning(
            f"batch_update_oknte_configs失败: {type(e).__name__}: {e}"
        )
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
        }


@router.get(
    "/backup/list",
    tags=["Backup"],
    summary="列出配置备份（时间倒序；target 取值由专项定义，非法值返回 400）",
    response_model=ConfigBackupListOut,
    status_code=200,
)
async def list_config_backups_api(
    scriptId: str, userId: str, target: str
) -> ConfigBackupListOut:
    """运行/会话下发前与编辑界面进出会自动归档，内容无变化跳过。"""

    try:
        data = await Config.list_config_backups(scriptId, userId, target)
        return ConfigBackupListOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 份备份",
            data=[ConfigBackupItemOut(**item) for item in data],
        )
    except Exception as e:
        return ConfigBackupListOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/backup/ensure",
    tags=["Backup"],
    summary="按需归档目标池当前配置（指纹去重，无变化跳过；编辑界面进入/退出时机调用）",
    response_model=ConfigBackupEnsureOut,
    status_code=200,
)
async def ensure_config_backup_api(
    script: ConfigBackupEnsureIn = Body(...),
) -> ConfigBackupEnsureOut:
    """target 取值由专项池定义（如 zzz-od 的 mas/onedragon、ok-nte 的 mas/native）。"""

    try:
        data = await Config.ensure_config_backup(
            script.scriptId, script.userId, target=script.target
        )
        return ConfigBackupEnsureOut(
            code=200,
            status="success",
            message="",
            **data,
        )
    except Exception as e:
        return ConfigBackupEnsureOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            created=False,
            time="",
        )


@router.post(
    "/backup/restore",
    tags=["Backup"],
    summary="把指定备份恢复到目标位置（恢复前自动存底当前配置，误恢复可找回）",
    response_model=ConfigBackupRestoreOut,
    status_code=200,
)
async def restore_config_backup_api(
    script: ConfigBackupRestoreIn = Body(...),
) -> ConfigBackupRestoreOut:
    """恢复语义由专项池定义：脚本原生池恢复到脚本本体，MAS 用户池恢复到
    用户配置并按需回填前端表单。"""

    try:
        data = await Config.restore_config_backup(
            script.scriptId, script.userId, script.time, target=script.target
        )
        return ConfigBackupRestoreOut(
            code=200,
            status="success",
            message=f"已恢复备份 {script.time}",
            target=data["target"],
        )
    except Exception as e:
        return ConfigBackupRestoreOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            target=script.target,
        )


@router.get(
    "/backup/preview",
    tags=["Backup"],
    summary="读取指定备份的配置摘要（纯读不恢复，供「预览配置」快速展示）",
    response_model=ConfigBackupPreviewOut,
    status_code=200,
)
async def get_config_backup_preview_api(
    scriptId: str, userId: str, time: str, target: str
) -> ConfigBackupPreviewOut:
    """data 载荷结构由专项定义（前端按 target 消费）；非法 target 返回 400。"""

    try:
        data = await Config.get_config_backup_preview(
            scriptId, userId, time, target=target
        )
        return ConfigBackupPreviewOut(
            code=200,
            status="success",
            message="",
            **data,
        )
    except Exception as e:
        return ConfigBackupPreviewOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            time=time,
            target=target,
            data={},
        )


_MAAFW_IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}
"""允许外发的图片后缀。

白名单而非黑名单：``/maafw/asset`` 的 root 由请求方给定，等于把「读任意目录下的
文件」的能力暴露出去了，只能靠「必须在 root 内」+「必须是图片」两道闸门把它收窄
成「读项目内的图片」。放开成任意后缀就变成了任意文件读取。
"""


def _maafw_asset_file_path(root: str, asset_path: str) -> Path:
    """把 (项目根, 项目内相对路径) 解析成一个可安全外发的图片绝对路径。"""

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError("MFW 项目目录不存在")

    normalized_asset_path = asset_path.replace("\\", "/").strip()
    relative_path = Path(normalized_asset_path)
    if (
        not normalized_asset_path
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise ValueError("MFW 资源路径非法")

    file_path = (root_path / relative_path).resolve()
    # 逐段比对而不是比字符串前缀：符号链接与 ..（上面已挡）之外，
    # 大小写与短路径名的差异也会让前缀比较判错。
    if root_path not in file_path.parents:
        raise ValueError("MFW 资源路径越界")
    if file_path.suffix.casefold() not in _MAAFW_IMAGE_SUFFIXES:
        raise ValueError("仅支持 MFW 图片资源")
    if not file_path.is_file():
        raise FileNotFoundError("MFW 图片资源不存在")
    return file_path


@router.get(
    "/maafw/asset",
    tags=["MaaFW"],
    summary="读取 MFW 项目内的图片资源",
    response_class=FileResponse,
)
async def get_maafw_asset(
    root: str = Query(..., description="MFW 项目根目录"),
    path: str = Query(..., description="项目根目录内的相对图片路径"),
) -> FileResponse:
    """把 MFW 项目目录内的图片按需读给前端。

    任务说明（interface 的 ``doc`` / ``description``）是 markdown，里面的图片写的是
    **项目内相对路径**，浏览器没法直接读本地文件，必须由后端转一手。

    前端侧对应 ``buildMaaFWAssetUrl``：它已经拦掉了绝对路径、UNC、上跳与远程 URL，
    但那只是省一次往返，安全边界在这里 —— 请求可以绕过前端直接打过来。
    """

    try:
        file_path = _maafw_asset_file_path(root, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(file_path)
