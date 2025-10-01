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

from app.core import Config
from app.services import System, Notify
from app.models.schema import *
import uuid

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
    "/webhook/test",
    summary="测试自定义Webhook",
    response_model=OutBase,
    status_code=200,
)
async def test_webhook(webhook_data: dict = Body(...)) -> OutBase:
    """测试自定义Webhook"""

    try:
        webhook_config = {
            "name": webhook_data.get("name", "测试Webhook"),
            "url": webhook_data.get("url", ""),
            "template": webhook_data.get("template", ""),
            "enabled": True,
            "headers": webhook_data.get("headers", {}),
            "method": webhook_data.get("method", "POST"),
        }

        await Notify.CustomWebhookPush(
            "AUTO-MAS Webhook测试",
            "这是一条测试消息，如果您收到此消息，说明Webhook配置正确！",
            webhook_config,
        )

        return OutBase(message="Webhook测试成功")

    except Exception as e:
        return OutBase(code=500, status="error", message=f"Webhook测试失败: {str(e)}")
