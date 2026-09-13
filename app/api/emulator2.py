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

"""Emulator 2.0 接口。

路径的增与删**拆成两个接口**：按项目规范，MCP 靠 ``Delete`` 标签排除破坏性接口，
增删合一就没法分类。移除前另给一个只读的预览接口，供确认页列出受影响的脚本。
"""

from fastapi import APIRouter, Body

from app.models.schema import (
    Emulator2DevicesIn,
    Emulator2DevicesOut,
    Emulator2GuardCaptureOut,
    Emulator2InstanceCreateIn,
    Emulator2InstanceCreateOut,
    Emulator2InstanceDeleteIn,
    Emulator2InstanceDeleteOut,
    Emulator2InstanceDeletePreviewOut,
    Emulator2PathAddIn,
    Emulator2PathAddOut,
    Emulator2PathRemoveIn,
    Emulator2PathRemoveOut,
    Emulator2PathRemovePreviewOut,
    Emulator2SearchIn,
    Emulator2SearchOut,
    Emulator2SettingsApplyAllIn,
    Emulator2SettingsApplyAllOut,
    Emulator2SettingsApplyIn,
    Emulator2SettingsApplyOut,
    Emulator2StableModeIn,
    Emulator2StoreOpenIn,
    Emulator2StoreOpenOut,
)
from app.utils import get_logger
from app.utils.emulator2 import service

router = APIRouter(prefix="/api/emulator2", tags=["Emulator 2.0"])
logger = get_logger("Emulator 2.0 API")


def _error(error: BaseException | str) -> dict:
    """统一的失败响应。

    ``service.readable_error`` 负责把认得出的异常翻译成中文一句话——
    界面上不该出现 ``ValueError: badly formed hexadecimal UUID string``。
    """
    message = error if isinstance(error, str) else service.readable_error(error)
    return {"code": 500, "status": "error", "message": message}


@router.post(
    "/search",
    tags=["Get"],
    summary="搜索可加入 Emulator 2.0 的模拟器",
    response_model=Emulator2SearchOut,
    status_code=200,
)
async def search_emulators(
    payload: Emulator2SearchIn = Body(default=Emulator2SearchIn()),
) -> Emulator2SearchOut:
    """列出本机模拟器并逐条判定。不可添加的**也会列出**并给出原因枚举。"""
    try:
        items = await service.search(payload.emulatorId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"search_emulators失败: {type(e).__name__}: {e}"
        )
        return Emulator2SearchOut(**_error(e), emulators=[])
    return Emulator2SearchOut(emulators=[item.to_dict() for item in items])


@router.post(
    "/paths/add",
    tags=["Add"],
    summary="添加模拟器路径",
    response_model=Emulator2PathAddOut,
    status_code=200,
)
async def add_path(payload: Emulator2PathAddIn = Body(...)) -> Emulator2PathAddOut:
    """探测版本 → 落库 → 为该安装的实例分配设备号。

    版本不合要求时返回 ``ok=False`` 与原因枚举，而不是抛错。
    """
    try:
        result = await service.add_path(
            payload.emulatorId, payload.installPath, payload.alias
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_path失败: {type(e).__name__}: {e}")
        return Emulator2PathAddOut(**_error(e))
    return Emulator2PathAddOut(**result)


@router.post(
    "/paths/remove/preview",
    tags=["Get"],
    summary="预览移除模拟器路径的影响",
    response_model=Emulator2PathRemovePreviewOut,
    status_code=200,
)
async def preview_remove_path(
    payload: Emulator2PathRemoveIn = Body(...),
) -> Emulator2PathRemovePreviewOut:
    """只读。列出会失效的设备号与受影响的脚本，供确认页使用。"""
    try:
        result = await service.preview_remove_path(payload.emulatorId, payload.pathId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"preview_remove_path失败: {type(e).__name__}: {e}"
        )
        return Emulator2PathRemovePreviewOut(**_error(e))
    return Emulator2PathRemovePreviewOut(**result)


@router.post(
    "/paths/remove",
    tags=["Delete"],
    summary="移除模拟器路径",
    response_model=Emulator2PathRemoveOut,
    status_code=200,
)
async def remove_path(
    payload: Emulator2PathRemoveIn = Body(...),
) -> Emulator2PathRemoveOut:
    """移除一条路径。设备号**失效并保留**，不会再分配给其他设备。"""
    try:
        result = await service.remove_path(payload.emulatorId, payload.pathId)
    except Exception as e:
        logger.opt(exception=True).warning(f"remove_path失败: {type(e).__name__}: {e}")
        return Emulator2PathRemoveOut(**_error(e))
    return Emulator2PathRemoveOut(**result)


@router.post(
    "/devices",
    tags=["Get"],
    summary="查询合并后的设备列表",
    response_model=Emulator2DevicesOut,
    status_code=200,
)
async def list_devices(payload: Emulator2DevicesIn = Body(...)) -> Emulator2DevicesOut:
    """合并多条安装的实例。键是设备号，另附模拟器自己的实例索引。

    枚举失败的安装标 ``unavailable``——一次枚举失败不等于实例被删除，
    既不写墓碑也不影响下次恢复。``withSettings=false`` 只取状态，给轮询用。
    """
    try:
        result = await service.list_devices(
            payload.emulatorId, with_settings=payload.withSettings
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"list_devices失败: {type(e).__name__}: {e}")
        return Emulator2DevicesOut(**_error(e))
    return Emulator2DevicesOut(**result)


@router.post(
    "/instances/create",
    tags=["Add"],
    summary="新建模拟器实例",
    response_model=Emulator2InstanceCreateOut,
    status_code=200,
)
async def create_instance(
    payload: Emulator2InstanceCreateIn = Body(...),
) -> Emulator2InstanceCreateOut:
    """在某条模拟器安装下新建一个实例，并给它分配设备号。

    新建成功与否**不看命令返回码**——雷电新建成功时返回码也不为 0，
    判据是列表里有没有多出实例。
    """
    try:
        result = await service.create_instance(
            payload.emulatorId, payload.pathId, payload.name
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"create_instance失败: {type(e).__name__}: {e}"
        )
        return Emulator2InstanceCreateOut(**_error(e))
    return Emulator2InstanceCreateOut(**result)


@router.post(
    "/instances/delete/preview",
    tags=["Get"],
    summary="预览删除实例的影响",
    response_model=Emulator2InstanceDeletePreviewOut,
    status_code=200,
)
async def preview_delete_instance(
    payload: Emulator2InstanceDeleteIn = Body(...),
) -> Emulator2InstanceDeletePreviewOut:
    """只读。列出绑定了该设备号的脚本，供确认页使用。"""
    try:
        result = await service.preview_delete_instance(payload.emulatorId, payload.slot)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"preview_delete_instance失败: {type(e).__name__}: {e}"
        )
        return Emulator2InstanceDeletePreviewOut(**_error(e))
    return Emulator2InstanceDeletePreviewOut(**result)


@router.post(
    "/instances/delete",
    tags=["Delete"],
    summary="删除模拟器实例",
    response_model=Emulator2InstanceDeleteOut,
    status_code=200,
)
async def delete_instance(
    payload: Emulator2InstanceDeleteIn = Body(...),
) -> Emulator2InstanceDeleteOut:
    """删除一个实例。实例必须先关闭。

    设备号不写墓碑——以后在同一原生索引重建实例仍然是这个设备号；
    在那之前该设备号显示为「未找到」，绑定它的脚本下一次执行直接失败。
    """
    try:
        result = await service.delete_instance(payload.emulatorId, payload.slot)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_instance失败: {type(e).__name__}: {e}"
        )
        return Emulator2InstanceDeleteOut(**_error(e))
    return Emulator2InstanceDeleteOut(**result)


@router.post(
    "/instances/store/open",
    tags=["Action"],
    summary="打开游戏中心",
    response_model=Emulator2StoreOpenOut,
    status_code=200,
)
async def open_store(
    payload: Emulator2StoreOpenIn = Body(...),
) -> Emulator2StoreOpenOut:
    """在一台**已在线**的设备上打开模拟器自带的游戏中心。

    雷电纯净模式会把游戏中心从桌面藏掉，这是它唯一的图形入口。
    拉不起来返回 ``ok=false`` 和一句说明，不算接口错误；只有设备号解析不出来才是 500。
    """
    try:
        result = await service.open_store(payload.emulatorId, payload.slot)
    except Exception as e:
        logger.opt(exception=True).warning(f"open_store失败: {type(e).__name__}: {e}")
        return Emulator2StoreOpenOut(**_error(e))
    return Emulator2StoreOpenOut(**result)


@router.post(
    "/settings/apply",
    tags=["Action"],
    summary="修改实例设置",
    response_model=Emulator2SettingsApplyOut,
    status_code=200,
)
async def apply_settings(
    payload: Emulator2SettingsApplyIn = Body(...),
) -> Emulator2SettingsApplyOut:
    """写一台设备的设置。

    只提交用户改过的字段；``expected`` 与文件现状对不上就拒绝写入并交回冲突字段，
    绝不把表单打开时的旧值整片盖回去。
    """
    try:
        result = await service.apply_settings(
            payload.emulatorId, payload.slot, payload.changes, payload.expected
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"apply_settings失败: {type(e).__name__}: {e}"
        )
        return Emulator2SettingsApplyOut(**_error(e))
    return Emulator2SettingsApplyOut(**result)


@router.post(
    "/settings/apply-all",
    tags=["Action"],
    summary="批量修改全部实例设置",
    response_model=Emulator2SettingsApplyAllOut,
    status_code=200,
)
async def apply_settings_to_all(
    payload: Emulator2SettingsApplyAllIn = Body(...),
) -> Emulator2SettingsApplyAllOut:
    """把同一组设置写到全部实例上。

    没有勾选也没有冲突比对——点它就是明确要求「所有实例都设成这组值」。
    一台失败不影响其余，逐台交回结果。
    """
    try:
        result = await service.apply_settings_to_all(
            payload.emulatorId, payload.changes
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"apply_settings_to_all失败: {type(e).__name__}: {e}"
        )
        return Emulator2SettingsApplyAllOut(**_error(e))
    return Emulator2SettingsApplyAllOut(**result)


@router.post(
    "/stable-mode/apply",
    tags=["Action"],
    summary="应用稳定模式",
    response_model=Emulator2SettingsApplyAllOut,
    status_code=200,
)
async def apply_stable_mode(
    payload: Emulator2StableModeIn = Body(...),
) -> Emulator2SettingsApplyAllOut:
    """把设备切进稳定模式：关掉会干扰截图识别的模拟器功能。

    ``slots`` 留空表示全部。每台交回实际改动了哪几项；已经安全的返回空改动列表。
    **关掉稳定模式不由这个接口负责**——我们不知道用户原来想要什么值，不替他猜。
    """
    try:
        result = await service.apply_stable_mode(payload.emulatorId, payload.slots)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"apply_stable_mode失败: {type(e).__name__}: {e}"
        )
        return Emulator2SettingsApplyAllOut(**_error(e))
    return Emulator2SettingsApplyAllOut(**result)


@router.post(
    "/guard/capture",
    tags=["Action"],
    summary="记录配置守卫的基准",
    response_model=Emulator2GuardCaptureOut,
    status_code=200,
)
async def capture_baselines(
    payload: Emulator2DevicesIn = Body(...),
) -> Emulator2GuardCaptureOut:
    """把当前所有设备的设置记成守卫基准。开启守卫时调一次。

    只记用户显式设过的字段：模拟器默认值和从没设过的项没有「应该是什么」可言，
    写进基准等于替用户决定。
    """
    try:
        result = await service.capture_baselines(payload.emulatorId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"capture_baselines失败: {type(e).__name__}: {e}"
        )
        return Emulator2GuardCaptureOut(**_error(e))
    return Emulator2GuardCaptureOut(**result)
