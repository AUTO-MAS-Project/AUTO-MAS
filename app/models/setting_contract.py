from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel, OutBase


class WebhookIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["Webhook"] = Field(..., description="配置类型")


class WebhookInfoRead(ApiModel):
    Name: str = Field(default="新自定义 Webhook 通知", description="Webhook名称")
    Enabled: bool = Field(default=True, description="是否启用")


class WebhookInfoPatch(ApiModel):
    Name: str | None = Field(default=None, description="Webhook名称")
    Enabled: bool | None = Field(default=None, description="是否启用")


class WebhookDataRead(ApiModel):
    Url: str = Field(default="", description="Webhook URL")
    Template: str = Field(default="", description="消息模板")
    Headers: str = Field(default="{ }", description="自定义请求头")
    Method: Literal["POST", "GET"] = Field(default="POST", description="请求方法")


class WebhookDataPatch(ApiModel):
    Url: str | None = Field(default=None, description="Webhook URL")
    Template: str | None = Field(default=None, description="消息模板")
    Headers: str | None = Field(default=None, description="自定义请求头")
    Method: Literal["POST", "GET"] | None = Field(
        default=None, description="请求方法"
    )


class WebhookRead(ApiModel):
    Info: WebhookInfoRead = Field(
        default_factory=WebhookInfoRead, description="Webhook基础信息"
    )
    Data: WebhookDataRead = Field(
        default_factory=WebhookDataRead, description="Webhook配置数据"
    )


class WebhookPatch(ApiModel):
    Info: WebhookInfoPatch | None = Field(default=None, description="Webhook基础信息")
    Data: WebhookDataPatch | None = Field(default=None, description="Webhook配置数据")


class GlobalConfigFunctionRead(ApiModel):
    HistoryRetentionTime: Literal[7, 15, 30, 60, 90, 180, 365, 0] = Field(
        default=0, description="历史记录保留时间, 0表示永久保存"
    )
    IfAllowSleep: bool = Field(default=False, description="允许休眠")
    IfSilence: bool = Field(default=False, description="静默模式")
    IfAgreeBilibili: bool = Field(default=False, description="同意哔哩哔哩用户协议")
    IfBlockAd: bool = Field(default=False, description="屏蔽模拟器广告")


class GlobalConfigFunctionPatch(ApiModel):
    HistoryRetentionTime: Literal[7, 15, 30, 60, 90, 180, 365, 0] | None = Field(
        default=None, description="历史记录保留时间, 0表示永久保存"
    )
    IfAllowSleep: bool | None = Field(default=None, description="允许休眠")
    IfSilence: bool | None = Field(default=None, description="静默模式")
    IfAgreeBilibili: bool | None = Field(
        default=None, description="同意哔哩哔哩用户协议"
    )
    IfBlockAd: bool | None = Field(default=None, description="屏蔽模拟器广告")


class GlobalConfigVoiceRead(ApiModel):
    Enabled: bool = Field(default=False, description="语音功能是否启用")
    Type: Literal["simple", "noisy"] = Field(
        default="simple", description="语音类型, simple为简洁, noisy为聒噪"
    )


class GlobalConfigVoicePatch(ApiModel):
    Enabled: bool | None = Field(default=None, description="语音功能是否启用")
    Type: Literal["simple", "noisy"] | None = Field(
        default=None, description="语音类型, simple为简洁, noisy为聒噪"
    )


class GlobalConfigStartRead(ApiModel):
    IfSelfStart: bool = Field(default=False, description="是否在系统启动时自动运行")
    IfMinimizeDirectly: bool = Field(
        default=False, description="启动时是否直接最小化到托盘而不显示主窗口"
    )


class GlobalConfigStartPatch(ApiModel):
    IfSelfStart: bool | None = Field(default=None, description="是否在系统启动时自动运行")
    IfMinimizeDirectly: bool | None = Field(
        default=None, description="启动时是否直接最小化到托盘而不显示主窗口"
    )


class GlobalConfigUIRead(ApiModel):
    IfShowTray: bool = Field(default=False, description="是否常态显示托盘图标")
    IfToTray: bool = Field(default=False, description="是否最小化到托盘")


class GlobalConfigUIPatch(ApiModel):
    IfShowTray: bool | None = Field(default=None, description="是否常态显示托盘图标")
    IfToTray: bool | None = Field(default=None, description="是否最小化到托盘")


class GlobalConfigNotifyRead(ApiModel):
    SendTaskResultTime: Literal["不推送", "任何时刻", "仅失败时"] = Field(
        default="不推送", description="任务结果推送时机"
    )
    IfSendStatistic: bool = Field(default=False, description="是否发送统计信息")
    IfSendSixStar: bool = Field(default=False, description="是否发送公招六星通知")
    IfPushPlyer: bool = Field(default=False, description="是否推送系统通知")
    IfSendMail: bool = Field(default=False, description="是否发送邮件通知")
    IfKoishiSupport: bool = Field(default=False, description="是否启用Koishi支持")
    KoishiServerAddress: str = Field(
        default="ws://localhost:5140/AUTO_MAS", description="Koishi服务器地址"
    )
    KoishiToken: str = Field(default="", description="Koishi Token")
    SMTPServerAddress: str = Field(default="", description="SMTP服务器地址")
    AuthorizationCode: str = Field(default="", description="SMTP授权码")
    FromAddress: str = Field(default="", description="邮件发送地址")
    ToAddress: str = Field(default="", description="邮件接收地址")
    IfServerChan: bool = Field(default=False, description="是否使用ServerChan推送")
    ServerChanKey: str = Field(default="", description="ServerChan推送密钥")


class GlobalConfigNotifyPatch(ApiModel):
    SendTaskResultTime: Literal["不推送", "任何时刻", "仅失败时"] | None = Field(
        default=None, description="任务结果推送时机"
    )
    IfSendStatistic: bool | None = Field(default=None, description="是否发送统计信息")
    IfSendSixStar: bool | None = Field(default=None, description="是否发送公招六星通知")
    IfPushPlyer: bool | None = Field(default=None, description="是否推送系统通知")
    IfSendMail: bool | None = Field(default=None, description="是否发送邮件通知")
    IfKoishiSupport: bool | None = Field(default=None, description="是否启用Koishi支持")
    KoishiServerAddress: str | None = Field(default=None, description="Koishi服务器地址")
    KoishiToken: str | None = Field(default=None, description="Koishi Token")
    SMTPServerAddress: str | None = Field(default=None, description="SMTP服务器地址")
    AuthorizationCode: str | None = Field(default=None, description="SMTP授权码")
    FromAddress: str | None = Field(default=None, description="邮件发送地址")
    ToAddress: str | None = Field(default=None, description="邮件接收地址")
    IfServerChan: bool | None = Field(default=None, description="是否使用ServerChan推送")
    ServerChanKey: str | None = Field(default=None, description="ServerChan推送密钥")


class GlobalConfigUpdateRead(ApiModel):
    IfAutoUpdate: bool = Field(default=False, description="是否自动更新")
    Source: Literal["GitHub", "MirrorChyan", "AutoSite"] = Field(
        default="GitHub", description="更新源: GitHub源, Mirror酱源, 自建源"
    )
    Channel: Literal["stable", "beta"] = Field(
        default="stable", description="更新渠道: 稳定版, 测试版"
    )
    ProxyAddress: str = Field(default="", description="网络代理地址")
    MirrorChyanCDK: str = Field(default="", description="Mirror酱CDK")


class GlobalConfigUpdatePatch(ApiModel):
    IfAutoUpdate: bool | None = Field(default=None, description="是否自动更新")
    Source: Literal["GitHub", "MirrorChyan", "AutoSite"] | None = Field(
        default=None, description="更新源: GitHub源, Mirror酱源, 自建源"
    )
    Channel: Literal["stable", "beta"] | None = Field(
        default=None, description="更新渠道: 稳定版, 测试版"
    )
    ProxyAddress: str | None = Field(default=None, description="网络代理地址")
    MirrorChyanCDK: str | None = Field(default=None, description="Mirror酱CDK")


class GlobalConfigRead(ApiModel):
    Function: GlobalConfigFunctionRead = Field(
        default_factory=GlobalConfigFunctionRead, description="功能相关配置"
    )
    Voice: GlobalConfigVoiceRead = Field(
        default_factory=GlobalConfigVoiceRead, description="语音相关配置"
    )
    Start: GlobalConfigStartRead = Field(
        default_factory=GlobalConfigStartRead, description="启动相关配置"
    )
    UI: GlobalConfigUIRead = Field(default_factory=GlobalConfigUIRead, description="界面相关配置")
    Notify: GlobalConfigNotifyRead = Field(
        default_factory=GlobalConfigNotifyRead, description="通知相关配置"
    )
    Update: GlobalConfigUpdateRead = Field(
        default_factory=GlobalConfigUpdateRead, description="更新相关配置"
    )


class GlobalConfigPatch(ApiModel):
    Function: GlobalConfigFunctionPatch | None = Field(
        default=None, description="功能相关配置"
    )
    Voice: GlobalConfigVoicePatch | None = Field(default=None, description="语音相关配置")
    Start: GlobalConfigStartPatch | None = Field(default=None, description="启动相关配置")
    UI: GlobalConfigUIPatch | None = Field(default=None, description="界面相关配置")
    Notify: GlobalConfigNotifyPatch | None = Field(default=None, description="通知相关配置")
    Update: GlobalConfigUpdatePatch | None = Field(default=None, description="更新相关配置")


class WebhookInBase(ApiModel):
    scriptId: str | None = Field(
        default=None, description="所属脚本ID, 获取全局设置的Webhook数据时无需携带"
    )
    userId: str | None = Field(
        default=None, description="所属用户ID, 获取全局设置的Webhook数据时无需携带"
    )


class WebhookGetIn(WebhookInBase):
    webhookId: str | None = Field(
        default=None, description="Webhook ID, 未携带时表示获取所有Webhook数据"
    )


class WebhookGetOut(OutBase):
    index: list[WebhookIndexItem] = Field(..., description="Webhook索引列表")
    data: dict[str, WebhookRead] = Field(
        ..., description="Webhook数据字典, key来自于index列表的uid"
    )


class WebhookCreateOut(OutBase):
    webhookId: str = Field(..., description="新创建的Webhook ID")
    data: WebhookRead = Field(..., description="Webhook配置数据")


class WebhookUpdateIn(WebhookInBase):
    webhookId: str = Field(..., description="Webhook ID")
    data: WebhookPatch = Field(..., description="Webhook更新数据")


class WebhookDeleteIn(WebhookInBase):
    webhookId: str = Field(..., description="Webhook ID")


class WebhookReorderIn(WebhookInBase):
    indexList: list[str] = Field(..., description="Webhook ID列表, 按新顺序排列")


class WebhookTestIn(WebhookInBase):
    data: WebhookPatch = Field(..., description="Webhook配置数据")


class SettingGetOut(OutBase):
    data: GlobalConfigRead = Field(..., description="全局设置数据")


class SettingUpdateIn(ApiModel):
    data: GlobalConfigPatch = Field(..., description="全局设置需要更新的数据")


__all__ = [
    "WebhookIndexItem",
    "WebhookInfoRead",
    "WebhookInfoPatch",
    "WebhookDataRead",
    "WebhookDataPatch",
    "WebhookRead",
    "WebhookPatch",
    "GlobalConfigFunctionRead",
    "GlobalConfigFunctionPatch",
    "GlobalConfigVoiceRead",
    "GlobalConfigVoicePatch",
    "GlobalConfigStartRead",
    "GlobalConfigStartPatch",
    "GlobalConfigUIRead",
    "GlobalConfigUIPatch",
    "GlobalConfigNotifyRead",
    "GlobalConfigNotifyPatch",
    "GlobalConfigUpdateRead",
    "GlobalConfigUpdatePatch",
    "GlobalConfigRead",
    "GlobalConfigPatch",
    "WebhookInBase",
    "WebhookGetIn",
    "WebhookGetOut",
    "WebhookCreateOut",
    "WebhookUpdateIn",
    "WebhookDeleteIn",
    "WebhookReorderIn",
    "WebhookTestIn",
    "SettingGetOut",
    "SettingUpdateIn",
]
