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


from __future__ import annotations

import calendar
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigGroup,
    UiVisibility,
    Virtual,
    collection,
    encrypted,
    legacy,
    tz,
    ui,
    virtual_field,
)
from app.config.types import (
    JsonDictString,
    UrlString,
)
from app.utils.constants import MATERIALS_MAP, RESOURCE_STAGE_INFO

from .base import DomainEntry
from .queue import Webhook
from .shared import (
    local_timezone,
    logger,
)


class GlobalConfig(DomainEntry):
    "全局配置"

    class DataFields(ConfigGroup):
        IfShowNotice: bool = Field(
            default_factory=lambda: True, description="是否显示公告"
        )

        LastMaintenanceUpdated: Annotated[
            datetime, tz(local_timezone), ui(format="hms")
        ] = Field(
            default_factory=lambda: datetime.fromisoformat(
                "2000-01-01 00:00:00"
            ).replace(tzinfo=local_timezone()),
            description="上次维护信息检查时间",
        )

        LastNoticeUpdated: Annotated[datetime, tz(local_timezone), ui(format="hms")] = (
            Field(
                default_factory=lambda: datetime.fromisoformat(
                    "2000-01-01 00:00:00"
                ).replace(tzinfo=local_timezone()),
                description="上次公告更新时间",
            )
        )

        LastStageUpdated: Annotated[datetime, tz(local_timezone), ui(format="hms")] = (
            Field(
                default_factory=lambda: datetime.fromisoformat(
                    "2000-01-01 00:00:00"
                ).replace(tzinfo=local_timezone()),
                description="上次关卡更新时间",
            )
        )

        LastStatisticsUpload: Annotated[
            datetime, tz(local_timezone), ui(format="hms")
        ] = Field(
            default_factory=lambda: datetime.fromisoformat(
                "2000-01-01 00:00:00"
            ).replace(tzinfo=local_timezone()),
            description="上次统计上传时间",
        )

        LastTelemetryActive: Annotated[
            datetime, tz(timezone.utc), ui(format="date")
        ] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc),
            description="上次记录遥测日活的 UTC 日期",
        )

        Maintenance: JsonDictString = Field(
            default_factory=lambda: '{"schema_version": 1, "games": {}}',
            description="维护信息内容",
        )

        MaintenanceETag: str = Field(
            default_factory=lambda: "", description="维护信息的版本标识符"
        )

        Notice: JsonDictString = Field(
            default_factory=lambda: "{ }", description="公告内容"
        )

        NoticeETag: str = Field(
            default_factory=lambda: "", description="公告的版本标识符"
        )

        ShareAppearanceUploads: JsonDictString = Field(
            default_factory=lambda: "{}",
            description="分享站外观上传记录：{用户名: {外观 ID: {fileId, fileKey, displayName, updatedAt}}}",
        )

        Stage: Virtual[str] = Field(
            default_factory=lambda: None, description="关卡信息"
        )
        StageData: Annotated[JsonDictString, legacy(group="Data", name="Stage")] = (
            Field(default_factory=lambda: "{ }", description="关卡信息数据")
        )

        StageETag: str = Field(
            default_factory=lambda: "", description="关卡数据的版本标识符"
        )

        UID: UUID = Field(
            default_factory=lambda: uuid.uuid4(), description="唯一标识符"
        )

    Data: Annotated[DataFields, ui(visibility=UiVisibility.HIDE)] = Field(
        default_factory=DataFields
    )

    class DisplayFields(ConfigGroup):
        IfEnableVirtualDisplay: bool = Field(
            default_factory=lambda: False,
            description="无人值守时是否允许 MAS 挂载虚拟显示器。 所有真实显示输出都断开后 Windows 只保留一块占位的幻影屏，它照旧上报正常的 分辨率但背后没有输出；冷启动时更会起在很小的分辨率上，把被托管的 PC 端游戏 窗口压小并被游戏写进自己的配置，之后每轮都在同一处失败。挂一块真实的虚拟屏 可从源头断掉。 需要用户自行安装 Parsec 虚拟显示驱动，MAS 不分发驱动。",
        )

        VirtualDisplayMode: Literal["1920x1080@60", "1920x1080@30"] = Field(
            default_factory=lambda: "1920x1080@60",
            description="虚拟显示器的刷新率（分辨率固定 1920x1080）。 分辨率固定是因为只有它 Windows 给 100% 缩放，再高会被自动上缩放，游戏窗口 又要面对 DPI 虚拟化。取值必须在驱动 advertise 的模式表里，否则会被 BADMODE 拒绝。",
        )

    Display: DisplayFields = Field(default_factory=DisplayFields)

    class FunctionFields(ConfigGroup):
        HistoryRetentionTime: Literal[7, 15, 30, 60, 90, 180, 365, 0] = Field(
            default_factory=lambda: 0, description="历史记录保留时间（天）"
        )

        IfAgreeBilibili: bool = Field(
            default_factory=lambda: False, description="是否同意 Bilibili 协议"
        )

        IfAllowSleep: bool = Field(
            default_factory=lambda: False, description="是否允许睡眠"
        )

        IfBlockAd: bool = Field(
            default_factory=lambda: False, description="是否屏蔽模拟器广告"
        )

        IfEnableTelemetry: bool = Field(
            default_factory=lambda: True, description="是否启用匿名遥测"
        )

        IfPersonalMss: bool = Field(
            default_factory=lambda: False,
            description="个人版 MSS 的专属编排（灾变防线），只对个人版项目生效， 普通版 MSS 与其它脚本都会忽略它。",
        )

        IfSilence: bool = Field(
            default_factory=lambda: False, description="是否启用静默模式"
        )

    Function: FunctionFields = Field(default_factory=FunctionFields)

    class NotifyFields(ConfigGroup):
        AuthorizationCode: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="邮箱授权码"
        )
        CMCCNewMsgApiKey: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="中国移动新消息 Channel API Key"
        )
        FromAddress: str = Field(default_factory=lambda: "", description="发件地址")

        IfCMCCNewMsg: bool = Field(
            default_factory=lambda: False, description="是否启用中国移动新消息通知"
        )

        IfKoishiSupport: bool = Field(
            default_factory=lambda: False, description="是否发送Koishi通知"
        )

        IfOpenClawQQ: bool = Field(
            default_factory=lambda: False,
            description="是否启用 QQ 官方机器人通知（凭据由扫码登录流程管理）",
        )

        IfPushPlyer: bool = Field(
            default_factory=lambda: False, description="是否推送系统通知"
        )

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendSixStar: bool = Field(
            default_factory=lambda: False, description="是否发送六星通知"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        KoishiServerAddress: UrlString = Field(
            default_factory=lambda: "ws://localhost:5140/AUTO_MAS",
            description="Koishi WebSocket 服务器地址",
        )

        KoishiToken: str = Field(default_factory=lambda: "", description="Koishi Token")

        OpenClawQQAppId: Annotated[str, ui(visibility=UiVisibility.HIDE)] = Field(
            default_factory=lambda: "",
            description="QQ 官方机器人应用 ID（由扫码登录响应返回）",
        )

        OpenClawQQClientSecret: Annotated[
            Annotated[str, encrypted()], ui(visibility=UiVisibility.HIDE)
        ] = Field(
            default_factory=lambda: "",
            description="QQ 官方机器人客户端密钥（由扫码登录响应返回）",
        )
        OpenClawQQTargetOpenId: Annotated[str, ui(visibility=UiVisibility.HIDE)] = (
            Field(
                default_factory=lambda: "",
                description="QQ 官方机器人目标用户 OpenID（由扫码登录响应返回）",
            )
        )

        SMTPServerAddress: str = Field(
            default_factory=lambda: "", description="SMTP 服务器地址"
        )

        OpenClawQQTargetType: Annotated[
            Literal["c2c", "group", "all"], ui(visibility=UiVisibility.HIDE)
        ] = Field(default="c2c", description="QQ 官方机器人通知接收位置")
        OpenClawQQGroupOpenIds: Annotated[
            list[str],
            ui(visibility=UiVisibility.HIDE),
            legacy(
                group="Notify",
                name="OpenClawQQGroupOpenId",
                convert=lambda value: [value] if value else [],
            ),
        ] = Field(default_factory=list, description="QQ 官方机器人自动发现的群 OpenID")

        SendTaskResultTime: Literal["不推送", "任何时刻", "仅失败时"] = Field(
            default_factory=lambda: "不推送", description="任务结果推送时间"
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(default_factory=lambda: "", description="收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class ReplayFields(ConfigGroup):
        Enabled: bool = Field(
            default_factory=lambda: False,
            description="连接已运行的 OBS，在自动代理最终失败时保存回放。",
        )

        MaxReplayCount: Annotated[int, Field(ge=1, le=20)] = Field(
            default_factory=lambda: 3,
            description="MAS 副本的保留数量，不清理 OBS 原文件。",
        )

        Password: Annotated[str, encrypted(), ui(visibility=UiVisibility.MASKED)] = (
            Field(
                default_factory=lambda: "",
                description="OBS 认证密码按现有敏感配置规则加密落盘。",
            )
        )
        Port: Annotated[int, Field(ge=1, le=65535)] = Field(
            default_factory=lambda: 4455,
            description="OBS WebSocket 仅连接本机。",
        )

        PasswordConfigured: Virtual[bool] = Field(
            default=None, description="OBS 密码是否已配置，只读"
        )

    Replay: ReplayFields = Field(default_factory=ReplayFields)

    @virtual_field("Replay.PasswordConfigured")
    def replay_password_configured(self):
        return bool(self.Replay.Password)

    class StartFields(ConfigGroup):
        IfMinimizeDirectly: bool = Field(
            default_factory=lambda: False, description="是否启动时直接最小化"
        )

        IfSelfStart: bool = Field(
            default_factory=lambda: False, description="是否自动启动"
        )

    Start: StartFields = Field(default_factory=StartFields)

    class UIFields(ConfigGroup):
        IfHideCloseButton: bool = Field(
            default_factory=lambda: False, description="是否隐藏主窗口关闭按钮"
        )

        IfShowTray: bool = Field(
            default_factory=lambda: False, description="是否显示托盘图标"
        )

        IfToTray: bool = Field(
            default_factory=lambda: False, description="是否关闭到托盘"
        )

    UI: UIFields = Field(default_factory=UIFields)

    class UpdateFields(ConfigGroup):
        Channel: Literal["stable", "beta"] = Field(
            default_factory=lambda: "stable", description="更新频道"
        )

        GitHubMirror: Literal["Auto", "Off"] = Field(
            default_factory=lambda: "Auto",
            description="GitHub 加速镜像 **只影响 MFW 项目包从 GitHub Release 下载这一条路**（脚本的 `Update.Source` 选 GitHub 时）：国内直连 GitHub 常年 100 多 KB/s， 359MB 的全量包要四十分钟。`Auto` 依次试镜像、全部失败再回直连； `Off` 只直连。MAS 自身的更新与初始化 clone 走前端 mirrorService， 不读这一项；Mirror 酱是另一个源，也不受它影响。",
        )

        IfAutoUpdate: bool = Field(
            default_factory=lambda: False, description="是否自动更新"
        )

        MirrorChyanCDK: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="镜像站 CDK"
        )
        PauseUntil: Annotated[
            datetime | None, tz(local_timezone), ui(widget="date", format="date")
        ] = Field(
            default=None,
            description="暂停更新截止时间，截止日期当天恢复；空值表示未暂停",
        )

        ProxyAddress: str = Field(default_factory=lambda: "", description="代理地址")

        Source: Literal["GitHub", "MirrorChyan", "AutoSite", "CNB"] = Field(
            default_factory=lambda: "GitHub", description="更新源"
        )

    Update: UpdateFields = Field(default_factory=UpdateFields)

    class VoiceFields(ConfigGroup):
        Enabled: bool = Field(default_factory=lambda: False, description="是否启用语音")

        Type: Literal["simple", "noisy"] = Field(
            default_factory=lambda: "simple", description="语音类型"
        )

    Voice: VoiceFields = Field(default_factory=VoiceFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)
    startup_notices: list = Field(default_factory=list, exclude=True)

    def getStage(self) -> str:
        """获取关卡信息"""
        try:
            raw_stage_data = json.loads(self.Data.StageData)
            if "Official" in raw_stage_data:
                stage_data_by_server = {
                    server: data.get("sideStoryStage", {})
                    for server, data in raw_stage_data.items()
                    if isinstance(data, dict)
                }
            else:
                stage_data_by_server = {"Official": raw_stage_data}
            all_stage_data = {}
            for server, server_stage_data in stage_data_by_server.items():
                activity_stage_drop_info = []
                activity_stage_combox = []
                for side_story in server_stage_data.values():
                    activity = side_story["Activity"]
                    activity_timezone = timezone(
                        timedelta(hours=activity.get("TimeZone", 8))
                    )
                    if (
                        datetime.strptime(
                            activity["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
                        ).replace(tzinfo=activity_timezone)
                        < datetime.now(tz=activity_timezone)
                        < datetime.strptime(
                            activity["UtcExpireTime"], "%Y/%m/%d %H:%M:%S"
                        ).replace(tzinfo=activity_timezone)
                    ):
                        for stage in side_story["Stages"]:
                            activity_stage_combox.append(
                                {"label": stage["Display"], "value": stage["Value"]}
                            )
                            if "SSReopen" not in stage["Display"]:
                                if stage["Drop"] in MATERIALS_MAP:
                                    drop_id = stage["Drop"]
                                elif "玉" in stage["Drop"]:
                                    drop_id = "30012"
                                else:
                                    drop_id = "NotFound"
                                activity_stage_drop_info.append(
                                    {
                                        "Display": stage["Display"],
                                        "Value": stage["Value"],
                                        "Drop": drop_id,
                                        "DropName": MATERIALS_MAP.get(
                                            stage["Drop"], stage["Drop"]
                                        ),
                                        "Activity": activity,
                                    }
                                )
                stage_data = {"Info": activity_stage_drop_info}
                for day in range(0, 8):
                    res_stage = []
                    for stage in RESOURCE_STAGE_INFO:
                        if day in stage["days"] or day == 0:
                            res_stage.append(
                                {"label": stage["text"], "value": stage["value"]}
                            )
                    stage_data[calendar.day_name[day - 1] if day > 0 else "ALL"] = (
                        res_stage[0:1] + activity_stage_combox + res_stage[1:]
                    )
                all_stage_data[server] = stage_data
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(
                f"解析活动关卡信息失败, 按空关卡处理: {type(e).__name__}: {e}"
            )
            return "{ }"
        return json.dumps(all_stage_data, ensure_ascii=False)

    @virtual_field("Data.Stage")
    def compute_Data_Stage(self):
        try:
            return self.getStage()
        except Exception as exc:
            return str(exc)


__all__ = ["GlobalConfig"]
