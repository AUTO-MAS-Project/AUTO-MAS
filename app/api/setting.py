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
from datetime import datetime
from typing import (
    Dict,
    List,
    Literal,
    Optional,
    Union,
)

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import (
    BaseModel,
    Field,
)
from starlette.background import BackgroundTask

import app.core.notify.bootstrap as notify_channels
import app.models.config as _config_models
from app.config.wire import ConfigInput, ConfigPayload
from app.core import Config, Notify
from app.models.config import Webhook as WebhookConfig
from app.models.notification import NotifyPayload, WebhookTargetSnapshot
from app.models.schema import (
    ObsReplayCheckOut,
    OutBase,
    VirtualDisplayCheckOut,
    VirtualDisplayCheckResultItem,
    WebhookDeleteIn,
    WebhookGetIn,
    WebhookInBase,
    WebhookIndexItem,
)
from app.models.schema import (
    WebhookCreateOut as SharedWebhookCreateOut,
)
from app.models.schema import (
    WebhookGetOut as SharedWebhookGetOut,
)
from app.models.schema import (
    WebhookUpdateIn as SharedWebhookUpdateIn,
)
from app.services.common.update import transport as _service_update_transport
from app.utils import debug_pattern, get_logger

GlobalConfig = ConfigPayload[_config_models.GlobalConfig]
GlobalConfigInput = ConfigInput[_config_models.GlobalConfig]
Webhook = ConfigPayload[_config_models.Webhook]
WebhookInput = ConfigInput[_config_models.Webhook]
WebhookGetOut = SharedWebhookGetOut[Webhook]
WebhookCreateOut = SharedWebhookCreateOut[Webhook]
WebhookUpdateIn = SharedWebhookUpdateIn[WebhookInput]


class VirtualDisplayDetachOut(OutBase):
    detached: bool = Field(
        default=False, description="有没有真的拆掉一块屏；没挂着时为 False"
    )


class PushLogPattern(BaseModel):
    """推送日志采集模式配置（split/regex/multiline 三种模式按 type 区分，各模式使用对应字段）"""

    type: Literal["split", "regex", "multiline"] = Field(..., description="匹配类型")
    name: Optional[str] = Field(
        default=None, description="规则标题（供分享站展示/说明）"
    )
    enabled: Optional[bool] = Field(
        default=None, description="单条规则启用/停用开关：停用时保留配置但不参与采集"
    )
    logType: Optional[str] = Field(default=None, description="日志类型：普通/失败")
    match: Optional[str] = Field(default=None, description="split 模式的匹配关键字")
    head: Optional[str] = Field(default=None, description="split 模式的首部关键字")
    headInclude: Optional[bool] = Field(
        default=None, description="split 模式是否包含首部关键字"
    )
    tail: Optional[str] = Field(default=None, description="split 模式的尾部关键字")
    tailInclude: Optional[bool] = Field(
        default=None, description="split 模式是否包含尾部关键字"
    )
    extract: Optional[str] = Field(
        default=None, description="regex 模式的提取正则（split/regex 通用）"
    )
    start: Optional[str] = Field(default=None, description="multiline 模式的起始行正则")
    end: Optional[str] = Field(default=None, description="multiline 模式的结束行正则")
    maxLines: Optional[int] = Field(
        default=None, description="multiline 模式的最大跨行数"
    )


class NotifyChannelOptionOut(BaseModel):
    """渠道下拉选项的取值与文案键；取值保持后端配置字面量（含布尔）。"""

    value: Union[bool, str] = Field(..., description="选项值，保持后端配置字面量")
    labelKey: str = Field(..., description="选项文案的词表键")


class NotifyChannelFieldOut(BaseModel):
    """渠道在某个作用域暴露的一个配置字段描述。"""

    group: str = Field(..., description="配置组，如 Notify")
    name: str = Field(..., description="配置字段名")
    labelKey: str = Field(..., description="字段标签词表键")
    control: str = Field(
        ..., description="控件类型：bool/text/password/url/select/json"
    )
    options: List[NotifyChannelOptionOut] = Field(default=[], description="下拉选项")
    placeholderKey: str = Field(default="", description="占位文案词表键")
    tipKey: str = Field(default="", description="提示文案词表键")


class NotifyChannelOut(BaseModel):
    """一个通知渠道的展示元数据；服务无鉴权，负载不得出现任何配置值。"""

    key: str = Field(..., description="渠道标识")
    nameKey: str = Field(..., description="渠道名称词表键")
    descKey: str = Field(default="", description="渠道一句话说明词表键")
    icon: str = Field(default="", description="图标标识，policy 段为空串")
    group: str = Field(..., description="分组：builtin/custom")
    order: int = Field(..., description="排序值，与投递顺序一致")
    docUrl: Optional[str] = Field(default=None, description="使用文档链接")
    scopes: List[str] = Field(default=[], description="可用作用域：global/user")
    kind: str = Field(..., description="渲染类型：fields/custom/policy")
    customBlock: Optional[str] = Field(
        default=None, description="自定义块标识：claw:qq/webhook_list"
    )
    enableField: Optional[List[str]] = Field(
        default=None, description="启用开关的 [配置组, 字段名]"
    )
    summaryKey: Optional[str] = Field(default=None, description="卡片摘要词表键")
    summaryFields: List[str] = Field(
        default=[], description="参与摘要插值与空值判定的字段名"
    )
    fields: Dict[str, List[NotifyChannelFieldOut]] = Field(
        default={}, description="按作用域分组的字段列表"
    )


class NotifyChannelsOut(OutBase):
    """通知渠道描述表。"""

    channels: List[NotifyChannelOut] = Field(default=[], description="渠道描述列表")


class ObsReplaySaveOut(OutBase):
    capture_path: str | None = None


class WebhookTestIn(WebhookInBase):
    data: WebhookInput = Field(..., description="Webhook配置数据")


class SettingGetOut(OutBase):
    data: GlobalConfig = Field(..., description="全局设置数据")


class SettingUpdateIn(BaseModel):
    data: GlobalConfigInput = Field(..., description="全局设置需要更新的数据")


class SettingMirrorCdkIn(BaseModel):
    cdk: str = Field(..., repr=False, description="待校验的 Mirror 酱 CDK")


class SettingMirrorCdkData(BaseModel):
    status: str = Field(
        ...,
        description="CDK 状态：ok / absent / error / expired / invalid / quota / mismatched / blocked",
    )
    expiredTime: int | None = Field(
        default=None, description="CDK 到期时间（unix 秒）；未返回时为空"
    )


class SettingMirrorCdkOut(OutBase):
    data: SettingMirrorCdkData


class PatternDebugIn(BaseModel):
    """日志模式调试请求"""

    pattern: PushLogPattern = Field(..., description="待调试的推送日志模式配置")
    logText: str = Field(default="", description="待调试的多行日志文本")


class PatternDebugResultItem(BaseModel):
    """单行/单窗口调试结果"""

    idx: int = Field(..., description="行号或窗口序号")
    hit: bool = Field(..., description="是否命中")
    extracted: str = Field(default="", description="提取后的文本")
    line: str = Field(default="", description="原始日志行（多行模式为空）")
    error: Optional[str] = Field(default=None, description="该行/窗口的错误信息")


class PatternDebugOut(OutBase):
    """日志模式调试响应"""

    configError: Optional[str] = Field(
        default=None, description="配置级错误（正则/表达式语法错误等）"
    )
    isMultiline: bool = Field(default=False, description="是否为多行聚合模式")
    results: List[PatternDebugResultItem] = Field(
        default_factory=list, description="逐行/逐窗口调试结果"
    )


router = APIRouter(prefix="/api/setting", tags=["全局设置"])
logger = get_logger("全局设置")
backup_lock = asyncio.Lock()


@router.post(
    "/mirror-cdk",
    tags=["Get"],
    summary="查询全局 Mirror 酱 CDK 状态与到期时间",
    response_model=SettingMirrorCdkOut,
)
async def query_setting_mirror_cdk(request: SettingMirrorCdkIn) -> SettingMirrorCdkOut:
    try:
        result = await _service_update_transport.query_mirror_cdk_status(
            "AUTO_MAS",
            cdk=request.cdk,
            channel=Config.setting.Update.Channel,
            proxy=Config.proxy,
        )
    except Exception as error:
        # 网络异常可能包含带 CDK 的请求 URL，只记录异常类型。
        logger.warning(f"全局 Mirror 酱 CDK 状态查询失败: {type(error).__name__}")
        return SettingMirrorCdkOut(data=SettingMirrorCdkData(status="error"))
    return SettingMirrorCdkOut(
        data=SettingMirrorCdkData(status=result.status, expiredTime=result.expired_time)
    )


@router.post(
    "/obs/check",
    tags=["Get"],
    response_model=ObsReplayCheckOut,
    operation_id="check_obs_replay_api_setting_obs_check_post",
    summary="检查 OBS 回放缓冲",
)
async def check_obs_replay() -> ObsReplayCheckOut:
    from app.services import obs_replay as _service_obs_replay

    try:
        return await _service_obs_replay.ObsReplay.check(Config.obs_replay_options())
    except Exception as error:
        return ObsReplayCheckOut(
            code=500,
            status="error",
            message=str(error),
            directory=str(_service_obs_replay.ObsReplay.directory),
        )


@router.post(
    "/obs/save",
    tags=["Action"],
    response_model=ObsReplaySaveOut,
    operation_id="save_obs_replay_api_setting_obs_save_post",
    summary="试存 OBS 回放",
)
async def save_obs_replay() -> ObsReplaySaveOut:
    from app.services import obs_replay as _service_obs_replay

    try:
        path = await _service_obs_replay.ObsReplay.capture(
            Config.obs_replay_options(), temporary_copy=False
        )
        return ObsReplaySaveOut(capture_path=str(path))
    except Exception as error:
        return ObsReplaySaveOut(code=500, status="error", message=str(error))


@router.get(
    "/backup",
    tags=["Get"],
    summary="导出数据备份",
    response_model=None,
    status_code=200,
)
async def backup_data() -> FileResponse | JSONResponse:
    """导出数据、配置与历史记录。"""

    if backup_lock.locked():
        return JSONResponse(
            status_code=409,
            content={"code": 409, "status": "error", "message": "数据备份正在生成"},
        )

    async with backup_lock:
        try:
            backup_path = await Config.create_data_backup()
        except Exception as error:
            logger.exception(f"生成数据备份失败: {error}")
            return JSONResponse(
                status_code=500,
                content={
                    "code": 500,
                    "status": "error",
                    "message": "生成数据备份失败",
                },
            )

    filename = f"AUTO-MAS-backup-{datetime.now():%Y-%m-%d_%H-%M-%S}.zip"
    return FileResponse(
        backup_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(backup_path.unlink, missing_ok=True),
    )


@router.post(
    "/get",
    tags=["Get"],
    summary="查询配置",
    response_model=SettingGetOut,
    status_code=200,
)
async def get_scripts() -> SettingGetOut:
    """查询配置"""

    try:
        data = await Config.get_setting()
    except Exception as e:
        logger.opt(exception=True).warning(f"get_scripts失败: {type(e).__name__}: {e}")
        return SettingGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=GlobalConfig(**{}),
        )
    return SettingGetOut(data=GlobalConfig(**data))


@router.post(
    "/update",
    tags=["Update"],
    summary="更新配置",
    response_model=OutBase,
    status_code=200,
)
async def update_script(script: SettingUpdateIn = Body(...)) -> OutBase:
    """更新配置"""

    try:
        data = script.data.model_dump(exclude_unset=True)
        await Config.update_setting(data)

    except Exception as e:
        logger.opt(exception=True).warning(
            f"update_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/test_notify",
    tags=["Action"],
    summary="测试通知",
    response_model=OutBase,
    status_code=200,
)
async def test_notify() -> OutBase:
    """测试通知"""

    try:
        result = await Notify.send_test_notification()
    except Exception as e:
        logger.opt(exception=True).warning(f"test_notify失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    if result.failed:
        return OutBase(
            code=500,
            status="error",
            message=f"部分通知发送失败: {'、'.join(result.failed)}",
        )
    if result.attempted == 0:
        return OutBase(
            code=400,
            status="error",
            message="没有已启用的通知渠道，请先完成绑定并开启通知",
        )
    return OutBase(message=f"测试通知已提交至：{'、'.join(result.succeeded)}")


@router.get(
    "/notify/channels",
    tags=["Get"],
    summary="查询通知渠道描述",
    response_model=NotifyChannelsOut,
    status_code=200,
)
async def get_notify_channels() -> NotifyChannelsOut:
    """返回通知渠道描述表，仅展示元数据，不含任何配置值。"""

    try:
        channels = [
            NotifyChannelOut(
                key=channel.key,
                nameKey=channel.name_key,
                descKey=channel.desc_key,
                icon=channel.icon,
                group=channel.group,
                order=channel.order,
                docUrl=channel.doc_url,
                scopes=sorted(channel.scopes),
                kind=channel.kind,
                customBlock=channel.custom_block,
                enableField=list(channel.enable_field)
                if channel.enable_field
                else None,
                summaryKey=channel.summary_key,
                summaryFields=list(channel.summary_fields),
                fields={
                    scope: [
                        NotifyChannelFieldOut(
                            group=item.group,
                            name=item.name,
                            labelKey=item.label_key,
                            control=item.control,
                            options=[
                                NotifyChannelOptionOut(value=value, labelKey=label_key)
                                for value, label_key in item.options
                            ],
                            placeholderKey=item.placeholder_key,
                            tipKey=item.tip_key,
                        )
                        for item in items
                    ]
                    for scope, items in channel.fields.items()
                },
            )
            for channel in notify_channels.get_notify_channels()
        ]
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_notify_channels失败: {type(e).__name__}: {e}"
        )
        return NotifyChannelsOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            channels=[],
        )
    return NotifyChannelsOut(channels=channels)


@router.post(
    "/debug_pattern",
    tags=["Action"],
    summary="调试日志模式",
    response_model=PatternDebugOut,
    status_code=200,
)
async def debug_pattern_api(req: PatternDebugIn = Body(...)) -> PatternDebugOut:
    """调试单条日志模式配置，返回逐行/逐窗口匹配结果

    前端调试弹窗调用此接口，由后端统一执行模式匹配，
    确保调试结果与实际推送日志采集逻辑完全一致。
    """
    try:
        error, is_multiline, results = debug_pattern(
            req.pattern.model_dump(exclude_none=True), req.logText
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"debug_pattern_api失败: {type(e).__name__}: {e}"
        )
        return PatternDebugOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            configError=f"{type(e).__name__}: {str(e)}",
            isMultiline=False,
            results=[],
        )
    return PatternDebugOut(
        configError=error,
        isMultiline=is_multiline,
        results=[PatternDebugResultItem(**r) for r in results],
    )


@router.post(
    "/webhook/get",
    tags=["Get"],
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
async def add_webhook() -> WebhookCreateOut:
    try:
        uid, config = await Config.add_webhook(None, None)
        data = Webhook(**config.model_dump(context={"audience": "api"}))
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
            None, None, webhook.webhookId, webhook.data.model_dump(exclude_unset=True)
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
        await Config.del_webhook(None, None, webhook.webhookId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_webhook失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


def _webhook_test_snapshot(webhook: WebhookConfig) -> WebhookTargetSnapshot:
    """草稿测试固定输入，不按正式目标的启用状态过滤。"""

    return WebhookTargetSnapshot(
        name=str(webhook.Info.Name),
        enabled=bool(webhook.Info.Enabled),
        url=webhook.Data.Url,
        template=webhook.Data.Template,
        headers=webhook.Data.Headers,
        method=webhook.Data.Method,
    )


@router.post(
    "/webhook/test",
    tags=["Action"],
    summary="测试Webhook配置",
    response_model=OutBase,
    status_code=200,
)
async def test_webhook(webhook: WebhookTestIn = Body(...)) -> OutBase:
    """测试自定义Webhook"""

    try:
        webhook_config = WebhookConfig.build(
            payload=webhook.data.model_dump(exclude_unset=True)
        )
        await webhook_config.activate()
        await Notify.test_webhook(
            NotifyPayload(
                title="AUTO-MAS Webhook测试",
                text="这是一条测试消息，如果您收到此消息，说明Webhook配置正确！",
                append_signature=False,
            ),
            _webhook_test_snapshot(webhook_config),
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"test_webhook失败: {type(e).__name__}: {e}")
        return OutBase(code=500, status="error", message=f"Webhook测试失败: {str(e)}")
    return OutBase()


@router.post(
    "/virtual-display/check",
    tags=["Get"],
    summary="检测虚拟显示驱动",
    response_model=VirtualDisplayCheckOut,
    status_code=200,
)
async def check_virtual_display() -> VirtualDisplayCheckOut:
    """三段式检测虚拟显示驱动。

    前两段验「能不能调用」，第三段真插一块屏再拆掉，验「有没有效果」——只做前两段
    会出现「设置页显示检测通过、无人值守时照样失败」的假信号。第三段会真的改变桌面
    拓扑，所以只挂在用户手动触发的按钮上，不在任务流程里自动跑。
    """

    from app.core.desktop_guard import check_virtual_display_driver

    try:
        return await check_virtual_display_driver()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"check_virtual_display失败: {type(e).__name__}: {e}"
        )
        return VirtualDisplayCheckOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            results=[
                VirtualDisplayCheckResultItem(
                    stage="installed", passed=False, message="检测过程异常"
                )
            ],
        )


@router.post(
    "/virtual-display/detach",
    tags=["Action"],
    summary="立即拆除虚拟显示器",
    response_model=VirtualDisplayDetachOut,
    status_code=200,
)
async def detach_virtual_display() -> VirtualDisplayDetachOut:
    """用户明示要拆：真实显示器回来时的询问弹窗和设置页的「立即拆除」都走这里。

    任务在不在跑都照办。拆完守卫的巡检照常：桌面上还有真实输出就什么都不做，一块都没有
    的话下一轮会重新挂上——要彻底停用得关开关。
    """

    from app.core import DesktopGuard

    try:
        detached = await DesktopGuard.detach_now("用户手动拆除")
    except Exception as e:
        logger.opt(exception=True).warning(
            f"detach_virtual_display失败: {type(e).__name__}: {e}"
        )
        return VirtualDisplayDetachOut(
            code=500, status="error", message=f"拆除失败: {str(e)}"
        )
    if not detached:
        return VirtualDisplayDetachOut(message="当前没有挂载虚拟显示器")
    return VirtualDisplayDetachOut(detached=True, message="已拆除虚拟显示器")


@router.post(
    "/virtual-display/status",
    tags=["Get"],
    summary="查询虚拟显示驱动状态",
    response_model=VirtualDisplayCheckOut,
    status_code=200,
)
async def virtual_display_status() -> VirtualDisplayCheckOut:
    """只查驱动装没装、能不能调，不改变桌面拓扑。

    设置页打开时自动调用，用来决定开关能不能打开。不做缓存也不持久化：一次 0.2ms，
    而存下来的状态只会变陈旧。
    """

    from app.core.desktop_guard import probe_virtual_display_driver

    try:
        return await probe_virtual_display_driver()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"virtual_display_status失败: {type(e).__name__}: {e}"
        )
        return VirtualDisplayCheckOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            results=[
                VirtualDisplayCheckResultItem(
                    stage="installed", passed=False, message="探测过程异常"
                )
            ],
        )
