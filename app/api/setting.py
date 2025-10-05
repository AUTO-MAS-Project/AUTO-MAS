#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import os
from pathlib import Path
import shutil
from fastapi import APIRouter, Body
import uuid as uuid_module
from app.core import Config
from app.services import System, Notify
from app.models.schema import (
    SettingGetOut,
    GlobalConfig,
    OutBase,
    SettingUpdateIn,
    WebhookGetOut,
    WebhookIndexItem,
    Webhook,
    WebhookGetIn,
    WebhookCreateOut,
    WebhookUpdateIn,
    WebhookDeleteIn,
    WebhookReorderIn,
    WebhookTestIn,
    EmulatorGetOut,
    EmulatorIndexItem,
    EmulatorOutBase,
    EmulatorUpdateIn,
    EmulatorDeleteIn,
    EmulatorDevicesIn,
    EmulatorDevicesOut,
    EmulatorSearchOut,
    EmulatorSearchResult,
    EmulatorStartIn,
    EmulatorStartOut,
    EmulatorStopIn,
    EmulatorStatusIn,
    EmulatorStatusOut,
)
from app.models.config import Webhook as WebhookConfig

from app.core.emulator_manager import emulator_manager
from app.models.config import EmulatorManagerConfig
from app.core.emulator_manager.emulator_search import (
    search_emulators as search_emulators_func,
)

router = APIRouter(prefix="/api/setting", tags=["全局设置"])


@router.post("/get", summary="查询配置", response_model=SettingGetOut, status_code=200)
async def get_scripts() -> SettingGetOut:
    """查询配置"""

    try:
        data = await Config.get_setting()
    except Exception as e:
        return SettingGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=GlobalConfig(**{}),
        )
    return SettingGetOut(data=GlobalConfig(**data))


@router.post("/update", summary="更新配置", response_model=OutBase, status_code=200)
async def update_script(script: SettingUpdateIn = Body(...)) -> OutBase:
    """更新配置"""

    try:
        data = script.data.model_dump(exclude_unset=True)
        await Config.update_setting(data)

        if data.get("Start", {}).get("IfSelfStart", None) is not None:
            await System.set_SelfStart()
        if data.get("Function", None) is not None:
            function = data["Function"]
            if function.get("IfAllowSleep", None) is not None:
                await System.set_Sleep()
            if function.get("IfSkipMumuSplashAds", None) is not None:
                MuMu_splash_ads_path = (
                    Path(os.getenv("APPDATA") or "")
                    / "Netease/MuMuPlayer-12.0/data/startupImage"
                )
                if Config.get("Function", "IfSkipMumuSplashAds"):
                    if MuMu_splash_ads_path.exists() and MuMu_splash_ads_path.is_dir():
                        shutil.rmtree(MuMu_splash_ads_path)
                    MuMu_splash_ads_path.touch()
                else:
                    if MuMu_splash_ads_path.exists() and MuMu_splash_ads_path.is_file():
                        MuMu_splash_ads_path.unlink()

    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/test_notify", summary="测试通知", response_model=OutBase, status_code=200
)
async def test_notify() -> OutBase:
    """测试通知"""

    try:
        await Notify.send_test_notification()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/get",
    summary="查询 webhook 配置",
    response_model=WebhookGetOut,
    status_code=200,
)
async def get_webhook(webhook: WebhookGetIn = Body(...)) -> WebhookGetOut:
    try:
        index, data = await Config.get_webhook(None, None, webhook.webhookId)
        index = [WebhookIndexItem(**_) for _ in index]
        data = {uid: Webhook(**cfg) for uid, cfg in data.items()}
    except Exception as e:
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
    summary="添加定时项",
    response_model=WebhookCreateOut,
    status_code=200,
)
async def add_webhook() -> WebhookCreateOut:
    uid, config = await Config.add_webhook(None, None)
    data = Webhook(**(await config.toDict()))
    return WebhookCreateOut(webhookId=str(uid), data=data)


@router.post(
    "/webhook/update", summary="更新定时项", response_model=OutBase, status_code=200
)
async def update_webhook(webhook: WebhookUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.update_webhook(
            None, None, webhook.webhookId, webhook.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/delete", summary="删除定时项", response_model=OutBase, status_code=200
)
async def delete_webhook(webhook: WebhookDeleteIn = Body(...)) -> OutBase:
    try:
        await Config.del_webhook(None, None, webhook.webhookId)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/order", summary="重新排序定时项", response_model=OutBase, status_code=200
)
async def reorder_webhook(webhook: WebhookReorderIn = Body(...)) -> OutBase:
    try:
        await Config.reorder_webhook(None, None, webhook.indexList)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/test", summary="测试Webhook配置", response_model=OutBase, status_code=200
)
async def test_webhook(webhook: WebhookTestIn = Body(...)) -> OutBase:
    """测试自定义Webhook"""

    try:
        webhook_config = WebhookConfig()
        await webhook_config.load(webhook.data.model_dump())
        await Notify.WebhookPush(
            "AUTO-MAS Webhook测试",
            "这是一条测试消息，如果您收到此消息，说明Webhook配置正确！",
            webhook_config,
        )
    except Exception as e:
        return OutBase(code=500, status="error", message=f"Webhook测试失败: {str(e)}")
    return OutBase()


# 模拟器管理相关API
@router.post(
    "/emulator/get",
    summary="查询全部模拟器配置",
    response_model=EmulatorGetOut,
    status_code=200,
)
async def get_emulators() -> EmulatorGetOut:
    """查询模拟器配置"""

    try:
        data_dict = await emulator_manager.config.toDict()

        # 从字典中移除 'instances' 键（它是列表类型，不是配置数据）
        instances_list = data_dict.pop("instances", [])

        # 构建索引列表（从instances或剩余的键中获取）
        if instances_list:
            index = [
                EmulatorIndexItem(uuid=str(item["uid"])) for item in instances_list
            ]
        else:
            index = [EmulatorIndexItem(uuid=str(uuid)) for uuid in data_dict.keys()]

        # 将UUID键转换为字符串
        data = {str(uuid): config for uuid, config in data_dict.items()}  # type: ignore

        return EmulatorGetOut(index=index, data=data)
    except Exception as e:
        return EmulatorGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )


@router.post(
    "/emulator/add",
    summary="添加模拟器配置",
    response_model=EmulatorOutBase,
    status_code=200,
)
async def add_emulator() -> EmulatorOutBase:
    """添加新的模拟器配置"""

    try:

        uuid, new_config = await emulator_manager.config.add(EmulatorManagerConfig)
        data = await new_config.toDict() if new_config else dict()
        return EmulatorOutBase(
            code=200,
            status="success",
            message="",
            emulator_data=data,
            emulator_uuid=str(uuid),
        )
    except Exception as e:
        return EmulatorOutBase(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            emulator_data=dict(),
            emulator_uuid="",
        )


@router.post(
    "/emulator/update",
    summary="更新模拟器配置",
    response_model=OutBase,
    status_code=200,
)
async def update_emulator(emulator: EmulatorUpdateIn = Body(...)) -> OutBase:
    """更新模拟器配置"""

    try:
        # 将字符串UUID转换为UUID对象
        emulator_uuid = uuid_module.UUID(emulator.emulator_uuid)

        # 检查UUID是否存在
        if emulator_uuid not in emulator_manager.config:
            return OutBase(
                code=404,
                status="error",
                message=f"未找到UUID为 {emulator.emulator_uuid} 的模拟器配置",
            )

        # 获取配置实例(从 MultipleConfig 中直接获取)
        config_instance = emulator_manager.config[emulator_uuid]

        # 直接加载字典数据,配置会自动保存
        await config_instance.load(emulator.data)

        return OutBase(code=200, status="success", message="模拟器配置更新成功")

    except ValueError as e:
        return OutBase(code=400, status="error", message=f"无效的UUID格式: {str(e)}")
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/emulator/delete",
    summary="删除模拟器配置",
    response_model=OutBase,
    status_code=200,
)
async def delete_emulator(emulator: EmulatorDeleteIn = Body(...)) -> OutBase:
    """删除模拟器配置"""

    try:
        # 将字符串UUID转换为UUID对象
        emulator_uuid = uuid_module.UUID(emulator.emulator_uuid)

        # 检查UUID是否存在
        if emulator_uuid not in emulator_manager.config:
            return OutBase(
                code=404,
                status="error",
                message=f"未找到UUID为 {emulator.emulator_uuid} 的模拟器配置",
            )

        # 删除配置
        await emulator_manager.config.remove(emulator_uuid)

        return OutBase(code=200, status="success", message="模拟器配置删除成功")

    except ValueError as e:
        return OutBase(code=400, status="error", message=f"无效的UUID格式: {str(e)}")
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/emulator/devices",
    summary="获取模拟器设备信息",
    response_model=EmulatorDevicesOut,
    status_code=200,
)
async def get_emulator_devices(
    emulator: EmulatorDevicesIn = Body(...),
) -> EmulatorDevicesOut:
    """获取指定模拟器下的所有设备信息"""

    try:
        # 调用 emulator_manager.get_emulator_status 获取设备信息
        success, result = await emulator_manager.get_emulator_status(
            emulator.emulator_uuid
        )

        if success:
            # success=True 时, result 是 dict
            return EmulatorDevicesOut(
                code=200,
                status="success",
                message="获取设备信息成功",
                devices=result,  # type: ignore
            )
        else:
            # success=False 时, result 是错误消息字符串
            return EmulatorDevicesOut(
                code=500, status="error", message=str(result), devices={}
            )

    except Exception as e:
        return EmulatorDevicesOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            devices={},
        )


@router.post(
    "/emulator/search",
    summary="自动搜索模拟器",
    response_model=EmulatorSearchOut,
    status_code=200,
)
async def search_emulators() -> EmulatorSearchOut:
    """自动搜索系统中安装的模拟器"""

    try:
        emulators = await search_emulators_func()
        search_results = [EmulatorSearchResult(**emulator) for emulator in emulators]
        return EmulatorSearchOut(emulators=search_results)
    except Exception as e:
        return EmulatorSearchOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            emulators=[],
        )


@router.post(
    "/emulator/start",
    summary="启动指定模拟器",
    response_model=EmulatorStartOut,
    status_code=200,
)
async def start_emulator(emulator: EmulatorStartIn = Body(...)) -> EmulatorStartOut:
    """根据UUID和索引启动指定模拟器"""

    try:
        # 验证UUID格式
        try:
            emulator_uuid = uuid_module.UUID(emulator.emulator_uuid)
        except ValueError:
            return EmulatorStartOut(
                code=400,
                status="error",
                message=f"无效的UUID格式: {emulator.emulator_uuid}",
                adb_info={},
            )

        # 检查模拟器配置是否存在
        if emulator_uuid not in emulator_manager.config:
            return EmulatorStartOut(
                code=404,
                status="error",
                message=f"未找到UUID为 {emulator.emulator_uuid} 的模拟器配置",
                adb_info={},
            )

        # 调用启动函数
        success, message, adb_info = await emulator_manager.start_emulator(
            emulator.emulator_uuid, emulator.index, emulator.package_name
        )

        if success:
            return EmulatorStartOut(message=message, adb_info=adb_info)
        else:
            return EmulatorStartOut(
                code=500, status="error", message=message, adb_info=adb_info
            )

    except Exception as e:
        return EmulatorStartOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            adb_info={},
        )


@router.post(
    "/emulator/stop",
    summary="关闭指定模拟器",
    response_model=OutBase,
    status_code=200,
)
async def stop_emulator(emulator: EmulatorStopIn = Body(...)) -> OutBase:
    """根据UUID和索引关闭指定模拟器"""

    try:
        # 验证UUID格式
        try:
            emulator_uuid = uuid_module.UUID(emulator.emulator_uuid)
        except ValueError:
            return OutBase(
                code=400,
                status="error",
                message=f"无效的UUID格式: {emulator.emulator_uuid}",
            )

        # 检查模拟器配置是否存在
        if emulator_uuid not in emulator_manager.config:
            return OutBase(
                code=404,
                status="error",
                message=f"未找到UUID为 {emulator.emulator_uuid} 的模拟器配置",
            )

        # 调用关闭函数
        success, message = await emulator_manager.close_emulator(
            emulator.emulator_uuid, emulator.index
        )

        if success:
            return OutBase(message=message)
        else:
            return OutBase(code=500, status="error", message=message)

    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/emulator/status",
    summary="获取模拟器状态",
    response_model=EmulatorStatusOut,
    status_code=200,
)
async def get_emulator_status_api(
    emulator: EmulatorStatusIn = Body(...),
) -> EmulatorStatusOut:
    """获取指定UUID的模拟器状态，或获取所有模拟器状态（不传UUID时）"""

    try:
        # 如果没有提供UUID，获取所有模拟器状态
        if emulator.emulator_uuid is None or emulator.emulator_uuid == "":
            success, result = await emulator_manager.get_all_emulator_status()

            if success:
                return EmulatorStatusOut(
                    message="成功获取所有模拟器状态",
                    status_data=result,  # type: ignore
                )
            else:
                return EmulatorStatusOut(
                    code=500,
                    status="error",
                    message=str(result),
                    status_data=result,  # type: ignore
                )

        # 验证UUID格式
        try:
            emulator_uuid = uuid_module.UUID(emulator.emulator_uuid)
        except ValueError:
            return EmulatorStatusOut(
                code=400,
                status="error",
                message=f"无效的UUID格式: {emulator.emulator_uuid}",
                status_data={},
            )

        # 检查模拟器配置是否存在
        if emulator_uuid not in emulator_manager.config:
            return EmulatorStatusOut(
                code=404,
                status="error",
                message=f"未找到UUID为 {emulator.emulator_uuid} 的模拟器配置",
                status_data={},
            )

        # 获取指定模拟器状态
        success, result = await emulator_manager.get_emulator_status(str(emulator_uuid))

        if success:
            return EmulatorStatusOut(
                message=f"成功获取模拟器 {emulator.emulator_uuid} 的状态",
                status_data=result,  # type: ignore
            )
        else:
            return EmulatorStatusOut(
                code=500, status="error", message=str(result), status_data={}
            )

    except Exception as e:
        return EmulatorStatusOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            status_data={},
        )
