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
    Emulator2SettingsIn,
    Emulator2SettingsOut,
    Emulator2StableModeIn,
)
from app.utils.emulator2 import service

router = APIRouter(prefix="/api/emulator2", tags=["Emulator 2.0"])


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
    既不写墓碑也不影响下次恢复。
    """
    try:
        result = await service.list_devices(payload.emulatorId)
    except Exception as e:
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
        return Emulator2InstanceDeleteOut(**_error(e))
    return Emulator2InstanceDeleteOut(**result)


@router.post(
    "/settings/get",
    tags=["Get"],
    summary="查询实例设置",
    response_model=Emulator2SettingsOut,
    status_code=200,
)
async def get_settings(
    payload: Emulator2SettingsIn = Body(...),
) -> Emulator2SettingsOut:
    """读一台设备的四项设置。

    每项都带状态：``.config`` 里有的才是用户保存过的，没有而从模拟器默认读到的
    标 ``default``，两边都没有标 ``unset``。
    """
    try:
        result = await service.get_settings(payload.emulatorId, payload.slot)
    except Exception as e:
        return Emulator2SettingsOut(**_error(e))
    return Emulator2SettingsOut(**result)


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
        return Emulator2SettingsApplyAllOut(**_error(e))
    return Emulator2SettingsApplyAllOut(**result)
