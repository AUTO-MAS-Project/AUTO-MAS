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
"""脚本管理：配置备份恢复 路由与端点专用模型。"""

from typing import (
    List,
    Optional,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

from app.core import Config
from app.models.schema import (
    OutBase,
)
from app.utils import get_logger
from app.utils import io as _utils_io


class ConfigBackupItemOut(BaseModel):
    """配置备份条目"""

    time: str = Field(..., description="备份时间戳（目录名，如 20260910-104500）")
    base: Optional[str] = Field(
        default=None,
        description="备份时点的 base 来源（shared/independent/native）；无标注（旧版备份或未声明来源）为 null",
    )


class ConfigBackupListOut(OutBase):
    data: List[ConfigBackupItemOut] = Field(..., description="备份列表（时间倒序）")
    base: Optional[str] = Field(
        default=None,
        description="当前 base 来源（shared/independent/native）；无来源概念（非 base 专项）为 null",
    )


class ConfigBackupRestoreIn(BaseModel):
    """把指定备份恢复到目标位置（target 取值由专项池定义）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="目标用户ID")
    time: str = Field(..., description="备份时间戳")
    target: str = Field(
        ...,
        description="恢复目标（如 zzz-od 的 mas/onedragon、ok-nte 的 mas/native）；非法值返回 400",
    )
    force: bool = Field(
        default=False,
        description="源配置损坏时是否强制恢复（False 时返回 409 由前端二次确认，True 跳过损坏文件相关的保护步骤）",
    )


class ConfigBackupRestoreOut(OutBase):
    target: str = Field(..., description="实际执行的恢复目标")


class ConfigBackupEnsureIn(BaseModel):
    """按需归档目标池当前配置（编辑界面进入/退出时机，指纹去重）"""

    scriptId: str = Field(..., description="所属脚本ID")
    userId: str = Field(..., description="目标用户ID")
    target: str = Field(..., description="归档目标（取值由专项池定义）")


class ConfigBackupEnsureOut(OutBase):
    created: bool = Field(
        ..., description="本次是否新建了归档（False=指纹无变化跳过或无可归档内容）"
    )
    time: str = Field(..., description="最新备份时间戳（无任何备份为空串）")


class ConfigBackupPreviewOut(OutBase):
    """备份配置摘要（预览用，纯读不恢复；载荷结构由专项定义）"""

    time: str = Field(..., description="备份时间戳")
    target: str = Field(..., description="备份类别")
    data: dict = Field(
        ...,
        description="专项预览载荷（如 zzz-od 的 info/account/tasks/instances 或 ok-nte 的 files）",
    )


class ConfigBackupFileOut(OutBase):
    """备份内文本文件内容（只读；路径限归档内相对路径，防穿越）"""

    time: str = Field(..., description="备份时间戳")
    target: str = Field(..., description="备份类别")
    path: str = Field(..., description="归档内相对路径（如 M7A/config.yaml）")
    size: int = Field(..., description="文件字节数")
    content: str = Field(
        ...,
        description="文本内容（utf-8 兼容 BOM 读取，无法解码部分以替换符呈现；超出大小上限返回 400）",
    )


router = APIRouter()
logger = get_logger("脚本管理 API")


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
    """返回 ``items``（``time`` + 备份时点来源标注 ``base``，倒序）与当前
    来源 ``base``（仅三态池，供前端跨来源提示）；非法 target 返回 400。"""

    try:
        data = await Config.list_config_backups(scriptId, userId, target)
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
    tags=["Backup"],
    summary="把指定备份恢复到目标位置（恢复前自动存底当前配置，误恢复可找回）",
    response_model=ConfigBackupRestoreOut,
    status_code=200,
)
async def restore_config_backup_api(
    script: ConfigBackupRestoreIn = Body(...),
) -> ConfigBackupRestoreOut:
    """恢复语义由专项池定义：脚本原生池恢复到脚本本体，MAS 用户池恢复到
    用户配置并按需回填前端表单。备份来自其他配置来源（脚本级/用户级）时
    由服务层把配置来源切回备份时点再恢复；提示由前端据备份列表与当前
    来源比对给出。"""

    try:
        data = await Config.restore_config_backup(
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
    tags=["Backup"],
    summary="只读读取指定备份内一个文本文件（预览「查看原始文件」用，路径限归档内）",
    response_model=ConfigBackupFileOut,
    status_code=200,
)
async def get_config_backup_file_api(
    scriptId: str, userId: str, time: str, target: str, path: str
) -> ConfigBackupFileOut:
    """路径越界/文件超限/池未实现查看能力均返回 400，message 说明原因。"""

    try:
        data = await Config.get_config_backup_file(
            scriptId, userId, time, target=target, path=path
        )
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
