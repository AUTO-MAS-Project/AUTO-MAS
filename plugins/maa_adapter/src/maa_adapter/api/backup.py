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
"""MAA 插件自有备份恢复接口，复用公共传输模型与文件恢复服务。"""

from auto_mas_core.host.models_schema import (
    ConfigBackupEnsureIn,
    ConfigBackupEnsureOut,
    ConfigBackupFileOut,
    ConfigBackupItemOut,
    ConfigBackupListOut,
    ConfigBackupPreviewOut,
    ConfigBackupRestoreIn,
    ConfigBackupRestoreOut,
)
from auto_mas_core.host.utils import get_logger
from auto_mas_core.host.utils import io as _utils_io
from fastapi import APIRouter, Body

from maa_adapter.native.restore import restore_backup, restore_service

router = APIRouter(prefix="/api/plugin/maa_adapter", tags=["MAA"])
logger = get_logger("MAA 配置恢复 API")


@router.get(
    "/backup/list",
    summary="列出配置备份（时间倒序；target 取值由专项定义，非法值返回 400）",
    response_model=ConfigBackupListOut,
    status_code=200,
)
async def maa_list_config_backups(
    scriptId: str, userId: str, target: str
) -> ConfigBackupListOut:
    """返回 ``items``（``time`` + 备份时点来源标注 ``base``，倒序）与当前
    来源 ``base``（仅三态池，供前端跨来源提示）；非法 target 返回 400。"""

    try:
        service = restore_service(scriptId, userId)
        data = {
            "items": await service.list(target),
            "base": await service.current_base(target),
        }
        return ConfigBackupListOut(
            code=200,
            status="success",
            message=f"共 {len(data['items'])} 份备份",
            base=data["base"],
            data=[ConfigBackupItemOut(**item) for item in data["items"]],
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置备份列表查询失败: {e}")
        return ConfigBackupListOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )


@router.post(
    "/backup/ensure",
    summary="按需归档目标池当前配置（指纹去重，无变化跳过；编辑界面进入/退出时机调用）",
    response_model=ConfigBackupEnsureOut,
    status_code=200,
)
async def maa_ensure_config_backup(
    script: ConfigBackupEnsureIn = Body(...),
) -> ConfigBackupEnsureOut:
    """target 为 MAA 定义的 mas 或 native。"""

    try:
        data = await restore_service(script.scriptId, script.userId).ensure(
            script.target
        )
        return ConfigBackupEnsureOut(
            code=200,
            status="success",
            message="",
            **data,
        )
    except _utils_io.ConfigCorruptedError as e:
        # 源配置损坏：message 用原文（含损坏位置）直达用户，前端编辑页会透传
        logger.opt(exception=True).warning(f"配置按需归档失败（源配置损坏）: {e}")
        return ConfigBackupEnsureOut(
            code=400,
            status="error",
            message=str(e),
            created=False,
            time="",
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置按需归档失败: {e}")
        return ConfigBackupEnsureOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            created=False,
            time="",
        )


@router.post(
    "/backup/restore",
    tags=["Delete"],
    summary="把指定备份恢复到目标位置（恢复前自动存底当前配置，误恢复可找回）",
    response_model=ConfigBackupRestoreOut,
    status_code=200,
)
async def maa_restore_config_backup(
    script: ConfigBackupRestoreIn = Body(...),
) -> ConfigBackupRestoreOut:
    """恢复语义由专项池定义：脚本原生池恢复到脚本本体，MAS 账号池恢复到
    账号配置并按需回填前端表单。备份来自其他配置来源（托管级/账号级）时
    由服务层把配置来源切回备份时点再恢复；提示由前端据备份列表与当前
    来源比对给出。"""

    try:
        data = await restore_backup(
            script.scriptId,
            script.userId,
            script.time,
            target=script.target,
            force=script.force,
        )
        return ConfigBackupRestoreOut(
            code=200,
            status="success",
            message=f"已恢复备份 {script.time}",
            target=data["target"],
        )
    except _utils_io.ConfigCorruptedError as e:
        # 源配置损坏：带损坏位置返回 409，前端弹二次确认后携带 force 重试
        logger.opt(exception=True).warning(f"配置备份恢复被拦截（源配置损坏）: {e}")
        return ConfigBackupRestoreOut(
            code=409,
            status="error",
            message=str(e),
            target=script.target,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置备份恢复失败: {e}")
        return ConfigBackupRestoreOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            target=script.target,
        )


@router.get(
    "/backup/preview",
    summary="读取指定备份的配置摘要（纯读不恢复，供「预览配置」快速展示）",
    response_model=ConfigBackupPreviewOut,
    status_code=200,
)
async def maa_get_config_backup_preview(
    scriptId: str, userId: str, time: str, target: str
) -> ConfigBackupPreviewOut:
    """data 载荷结构由专项定义（前端按 target 消费）；非法 target 返回 400。"""

    try:
        data = {
            "time": time,
            "target": target,
            "data": await restore_service(scriptId, userId).preview(target, time),
        }
        return ConfigBackupPreviewOut(
            code=200,
            status="success",
            message="",
            **data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置备份预览失败: {e}")
        return ConfigBackupPreviewOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            time=time,
            target=target,
            data={},
        )


@router.get(
    "/backup/file",
    summary="只读读取指定备份内一个文本文件（预览「查看原始文件」用，路径限归档内）",
    response_model=ConfigBackupFileOut,
    status_code=200,
)
async def maa_get_config_backup_file(
    scriptId: str, userId: str, time: str, target: str, path: str
) -> ConfigBackupFileOut:
    """路径越界/文件超限/池未实现查看能力均返回 400，message 说明原因。"""

    try:
        content = await restore_service(scriptId, userId).read_backup_file(
            target, time, path
        )
        data = {"time": time, "target": target, **content}
        return ConfigBackupFileOut(
            code=200,
            status="success",
            message="",
            **data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"配置备份文件读取失败: {e}")
        return ConfigBackupFileOut(
            code=400 if isinstance(e, (ValueError, KeyError, TypeError)) else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            time=time,
            target=target,
            path=path,
            size=0,
            content="",
        )
