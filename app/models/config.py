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

"""主程序配置字段表（新基类）。

仅覆盖：全局设置 ``Setting``、调度队列、工具设置。
脚本 / 计划表 / 模拟器等领域类见 ``config_legacy.py``（本阶段暂不迁入）。
"""

from __future__ import annotations

import calendar
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, cast

from pydantic import Field, PrivateAttr

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    Trigger,
    Virtual,
    encrypted,
    virtual_field,
)
from app.config.shortcuts import collection, trigger_field
from app.config.types import (
    HHMMString,
    JsonDictString,
    JsonListString,
    KeyboardKeyString,
    UrlString,
    YmdHmString,
    YmdHmsString,
    YmdString,
)
from app.utils.constants import MATERIALS_MAP, RESOURCE_STAGE_INFO, UTC8
from .schema import TagItem

# ──────────────────────────── Webhook ────────────────────────────


class Webhook(ConfigEntry):
    """自定义 Webhook 通知项。"""

    class Info(ConfigGroup):
        name: str = Field(default="新自定义 Webhook 通知", description="Webhook名称")
        enabled: bool = Field(default=True, description="是否启用")
        test: Trigger = Field(default=False, description="测试推送（写 True 触发一次）")

    class Data(ConfigGroup):
        url: UrlString = Field(default="", description="Webhook URL")
        template: str = Field(default="", description="消息模板")
        headers: JsonDictString = Field(default="{ }", description="自定义请求头")
        method: Literal["POST", "GET"] = Field(default="POST", description="请求方法")

    info: Info = Field(default_factory=Info, description="Webhook基础信息")
    data: Data = Field(default_factory=Data, description="Webhook配置数据")

    @trigger_field("info.test")
    async def on_test(self) -> None:
        """发送测试 Webhook。"""
        from app.services import Notify

        await Notify.WebhookPush(
            "AUTO-MAS Webhook测试",
            "这是一条测试消息，如果您收到此消息，说明Webhook配置正确！",
            self,
        )


# ──────────────────────────── 调度队列 ────────────────────────────


class QueueItemEntry(ConfigEntry):
    """队列项：引用脚本 uid（脚本集合迁入前仅存字符串）。"""

    class Info(ConfigGroup):
        script_id: str = Field(
            default="-",
            description="任务所对应的脚本ID, 为None时表示未选择",
        )

    info: Info = Field(default_factory=Info, description="队列项")


class TimeSetEntry(ConfigEntry):
    """队列定时时间点。"""

    class Info(ConfigGroup):
        enabled: bool = Field(default=True, description="是否启用")
        days: list[str] = Field(
            default_factory=lambda: list(calendar.day_name),
            description="执行周期, 可多选",
        )
        time: HHMMString = Field(default="00:00", description="时间设置, 格式为HH:MM")

    info: Info = Field(default_factory=Info, description="时间项")


class QueueEntry(ConfigEntry):
    """单条调度队列。"""

    class Info(ConfigGroup):
        name: str = Field(default="新队列", description="队列名称")
        time_enabled: bool = Field(default=False, description="是否启用定时")
        start_up_enabled: bool = Field(default=False, description="是否启动时运行")
        after_accomplish: Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
            "Logoff",
        ] = Field(default="NoAction", description="完成后操作")

    class Data(ConfigGroup):
        last_timed_start: YmdHmString = Field(
            default="2000-01-01 00:00",
            description="上次定时启动时间",
        )

    info: Info = Field(default_factory=Info, description="队列信息")
    data: Data = Field(default_factory=Data, description="队列运行时数据")
    time_sets: ConfigCollection[TimeSetEntry] = collection(TimeSetEntry)
    items: ConfigCollection[QueueItemEntry] = collection(QueueItemEntry)


# ──────────────────────────── 工具设置 ────────────────────────────


class GameSignAccount(ConfigEntry):
    """游戏签到账号组。"""

    class Info(ConfigGroup):
        name: str = Field(default="用户 1", description="账号组名称")
        enabled: bool = Field(default=True, description="是否启用")
        miyoushe_token: Annotated[str, encrypted()] = Field(
            default="", description="米游社登录凭证"
        )
        kuro_token: Annotated[str, encrypted()] = Field(
            default="", description="库街区登录凭证"
        )
        skland_token: Annotated[str, encrypted()] = Field(
            default="", description="森空岛登录凭证"
        )
        last_sign_date: YmdString = Field(
            default="2000-01-01", description="上次签到日期"
        )

    info: Info = Field(default_factory=Info, description="账号组配置")


class Tools(ConfigEntry):
    """工具箱配置（明日方舟 PC 键位 + 游戏签到）。"""

    class ArknightsPc(ConfigGroup):
        enabled: bool = Field(default=False, description="是否启用 ArknightsPC 工具")
        pause_key: KeyboardKeyString = Field(default="f10", description="暂停键位")
        select_deployed_key: KeyboardKeyString = Field(
            default="w", description="选中已部署干员键位"
        )
        use_skill_key: KeyboardKeyString = Field(
            default="r", description="释放技能键位"
        )
        retreat_key: KeyboardKeyString = Field(default="t", description="撤退键位")
        next_frame_key: KeyboardKeyString = Field(default="f", description="下一帧键位")
        another_quit_key: KeyboardKeyString = Field(
            default="space", description="自定义退出、暂停键位"
        )
        status: Virtual[str] = Field(default=None, description="工具状态 Tag")

    class GameSign(ConfigGroup):
        enabled: bool = Field(default=False, description="是否启用游戏签到")
        notify_enabled: bool = Field(default=False, description="签到后是否发送通知")
        window_start: HHMMString = Field(
            default="08:00", description="签到窗口起点 HH:mm"
        )
        window_end: HHMMString = Field(
            default="22:00", description="签到窗口终点 HH:mm"
        )
        run_on_startup: bool = Field(default=False, description="启动时运行")
        scheduled_run: bool = Field(default=True, description="定时运行")
        auto_start: bool = Field(default=False, description="是否立即开始")
        last_sign_date: YmdString = Field(
            default="2000-01-01", description="上次签到日期"
        )
        scheduled_time: str = Field(default="", description="今日计划签到时间")
        status: Virtual[str] = Field(default=None, description="签到状态标签")
        result: Virtual[str] = Field(default=None, description="签到结果 JSON")

    arknights_pc: ArknightsPc = Field(
        default_factory=ArknightsPc, description="明日方舟PC工具配置"
    )
    game_sign: GameSign = Field(
        default_factory=GameSign, description="游戏社区签到配置"
    )
    accounts: ConfigCollection[GameSignAccount] = collection(GameSignAccount)

    # 运行时态（不落盘）
    _arknights_pc_running: bool = PrivateAttr(default=False)
    _arknights_pc_get_connected: Callable[[], bool] = PrivateAttr(
        default_factory=lambda: (lambda: False)
    )
    _game_sign_result_data: dict = PrivateAttr(default_factory=dict)

    @virtual_field("arknights_pc.status")
    def _arknights_pc_status(self) -> str:
        if not self.arknights_pc.enabled:
            return TagItem(text="未启用", color="gray").model_dump_json()
        if self._arknights_pc_running:
            if self._arknights_pc_get_connected():
                return TagItem(text="运行中", color="green").model_dump_json()
            return TagItem(text="未连接", color="red").model_dump_json()
        return TagItem(text="已暂停", color="yellow").model_dump_json()

    @virtual_field("game_sign.status")
    def _game_sign_status(self) -> str:
        if not self.game_sign.enabled:
            return TagItem(text="未启用", color="gray").model_dump_json()
        return TagItem(text="已启用", color="green").model_dump_json()

    @virtual_field("game_sign.result")
    def _game_sign_result(self) -> str:
        return json.dumps(self._game_sign_result_data, ensure_ascii=False)

    @property
    def arknights_pc_running(self) -> bool:
        return self._arknights_pc_running

    @arknights_pc_running.setter
    def arknights_pc_running(self, value: bool) -> None:
        self._arknights_pc_running = value

    @property
    def arknights_pc_get_connected(self) -> Callable[[], bool]:
        return self._arknights_pc_get_connected

    @arknights_pc_get_connected.setter
    def arknights_pc_get_connected(self, value: Callable[[], bool]) -> None:
        self._arknights_pc_get_connected = value

    @property
    def arknights_pc_keys(self) -> list[str]:
        pc = self.arknights_pc
        return [
            pc.select_deployed_key,
            pc.use_skill_key,
            pc.retreat_key,
            pc.next_frame_key,
            pc.another_quit_key,
        ]


# ──────────────────────────── 全局设置 ────────────────────────────


class Setting(ConfigEntry):
    """全局设置（原 ``GlobalConfig``），对应 ``config/setting.toml``。"""

    class Function(ConfigGroup):
        history_retention_time: Literal[7, 15, 30, 60, 90, 180, 365, 0] = Field(
            default=0, description="历史记录保留时间, 0表示永久保存"
        )
        if_allow_sleep: bool = Field(default=False, description="允许休眠")
        if_silence: bool = Field(default=False, description="静默模式")
        if_agree_bilibili: bool = Field(
            default=False, description="同意哔哩哔哩用户协议"
        )
        if_block_ad: bool = Field(default=False, description="屏蔽模拟器广告")

    class Voice(ConfigGroup):
        enabled: bool = Field(default=False, description="语音功能是否启用")
        type: Literal["simple", "noisy"] = Field(
            default="simple",
            description="语音类型, simple为简洁, noisy为聒噪",
        )

    class Start(ConfigGroup):
        if_self_start: bool = Field(
            default=False, description="是否在系统启动时自动运行"
        )
        if_minimize_directly: bool = Field(
            default=False,
            description="启动时是否直接最小化到托盘而不显示主窗口",
        )

    class Appearance(ConfigGroup):
        if_show_tray: bool = Field(default=False, description="是否常态显示托盘图标")
        if_to_tray: bool = Field(default=False, description="是否最小化到托盘")
        if_hide_close_button: bool = Field(
            default=False, description="是否隐藏主窗口关闭按钮"
        )

    class Notify(ConfigGroup):
        send_task_result_time: Literal["不推送", "任何时刻", "仅失败时"] = Field(
            default="不推送", description="任务结果推送时机"
        )
        if_send_statistic: bool = Field(default=False, description="是否发送统计信息")
        if_send_six_star: bool = Field(
            default=False, description="是否发送公招六星通知"
        )
        if_push_plyer: bool = Field(default=False, description="是否推送系统通知")
        if_send_mail: bool = Field(default=False, description="是否发送邮件通知")
        if_koishi_support: bool = Field(default=False, description="是否启用Koishi支持")
        koishi_server_address: UrlString = Field(
            default="ws://localhost:5140/AUTO_MAS",
            description="Koishi服务器地址",
        )
        koishi_token: str = Field(default="", description="Koishi Token")
        smtp_server_address: str = Field(default="", description="SMTP服务器地址")
        authorization_code: Annotated[str, encrypted()] = Field(
            default="", description="SMTP授权码"
        )
        from_address: str = Field(default="", description="邮件发送地址")
        to_address: str = Field(default="", description="邮件接收地址")
        if_server_chan: bool = Field(
            default=False, description="是否使用ServerChan推送"
        )
        server_chan_key: str = Field(default="", description="ServerChan推送密钥")
        test: Trigger = Field(default=False, description="测试通知（写 True 触发一次）")

    class Updates(ConfigGroup):
        if_auto_update: bool = Field(default=False, description="是否自动更新")
        source: Literal["GitHub", "MirrorChyan", "AutoSite", "CNB"] = Field(
            default="GitHub",
            description="更新源: GitHub源, Mirror酱源, 自建源, CNB 镜像源",
        )
        channel: Literal["stable", "beta"] = Field(
            default="stable", description="更新渠道: 稳定版, 测试版"
        )
        proxy_address: str = Field(default="", description="网络代理地址")
        mirror_chyan_cdk: Annotated[str, encrypted()] = Field(
            default="", description="Mirror酱CDK"
        )
        github_token: Annotated[str, encrypted()] = Field(
            default="", description="GitHub token/API key"
        )

    class Data(ConfigGroup):
        uid: str = Field(
            default_factory=lambda: str(uuid.uuid4()),
            description="全局实例 UID",
        )
        last_statistics_upload: YmdHmsString = Field(
            default="2000-01-01 00:00:00",
            description="上次统计上报时间",
        )
        last_stage_updated: YmdHmsString = Field(
            default="2000-01-01 00:00:00",
            description="关卡数据上次更新时间",
        )
        stage_etag: str = Field(default="", description="关卡数据 ETag")
        stage_data: JsonDictString = Field(
            default="{ }", description="关卡原始数据 JSON"
        )
        stage: Virtual[str] = Field(
            default=None, description="活动关卡下拉数据（由 stage_data 推导）"
        )
        last_notice_updated: YmdHmsString = Field(
            default="2000-01-01 00:00:00",
            description="公告上次更新时间",
        )
        notice_etag: str = Field(default="", description="公告 ETag")
        if_show_notice: bool = Field(default=True, description="是否显示公告")
        notice: JsonDictString = Field(default="{ }", description="公告内容 JSON")
        last_web_config_updated: YmdHmsString = Field(
            default="2000-01-01 00:00:00",
            description="Web 配置上次更新时间",
        )
        web_config: JsonListString = Field(
            default="[ ]", description="Web 配置 JSON 列表"
        )

    function: Function = Field(default_factory=Function, description="功能相关配置")
    voice: Voice = Field(default_factory=Voice, description="语音相关配置")
    start: Start = Field(default_factory=Start, description="启动相关配置")
    appearance: Appearance = Field(
        default_factory=Appearance, description="界面相关配置"
    )
    notify: Notify = Field(default_factory=Notify, description="通知相关配置")
    updates: Updates = Field(default_factory=Updates, description="更新相关配置")
    data: Data = Field(default_factory=Data, description="全局运行时数据")
    custom_webhooks: ConfigCollection[Webhook] = collection(Webhook)

    @virtual_field("data.stage")
    def get_stage(self) -> str:
        """由 ``stage_data`` 推导当前活动关卡下拉数据。"""
        try:
            raw_stage_data = json.loads(self.data.stage_data)
            activity_stage_drop_info = []
            activity_stage_combox = []

            for side_story in raw_stage_data.values():
                if (
                    datetime.strptime(
                        side_story["Activity"]["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
                    ).replace(tzinfo=UTC8)
                    < datetime.now(tz=UTC8)
                    < datetime.strptime(
                        side_story["Activity"]["UtcExpireTime"], "%Y/%m/%d %H:%M:%S"
                    ).replace(tzinfo=UTC8)
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
                                    "Activity": side_story["Activity"],
                                }
                            )
        except Exception:  # noqa: BLE001
            return "{ }"

        stage_data: dict = {"Info": activity_stage_drop_info}
        for day in range(0, 8):
            res_stage = []
            for stage in RESOURCE_STAGE_INFO:
                if day in stage["days"] or day == 0:
                    res_stage.append({"label": stage["text"], "value": stage["value"]})
            stage_data[calendar.day_name[day - 1] if day > 0 else "ALL"] = (
                res_stage[0:1] + activity_stage_combox + res_stage[1:]
            )
        return json.dumps(stage_data, ensure_ascii=False)

    @trigger_field("notify.test")
    async def on_notify_test(self) -> None:
        """发送测试通知。"""
        from app.services import Notify

        await Notify.send_test_notification()

    @staticmethod
    async def _on_if_self_start(sender: object, event: object) -> None:
        """开机自启开关变更（init 热化 + runtime）。"""
        from app.services import System

        await System.set_SelfStart(cast(Setting, sender).start.if_self_start)

    @staticmethod
    async def _on_if_allow_sleep(sender: object, event: object) -> None:
        """允许休眠开关变更（init 热化 + runtime）。"""
        from app.services import System

        await System.set_Sleep(cast(Setting, sender).function.if_allow_sleep)


# 类体无法写 ``@Setting.connect``（类名尚未绑定）；定义后装饰订阅两阶段
Setting.connect(
    Setting._on_if_self_start, phase="both", group="start", field="if_self_start"
)
Setting.connect(
    Setting._on_if_allow_sleep, phase="both", group="function", field="if_allow_sleep"
)


# ──────────────────────────── 兼容别名（本阶段） ────────────────────────────

GlobalConfig = Setting
Queue = QueueEntry
QueueItem = QueueItemEntry
TimeSet = TimeSetEntry
QueueConfig = QueueEntry
ToolsConfig = Tools
GameSignAccountGroup = GameSignAccount

# 脚本 / 计划 / 模拟器尚未迁入新基类；从 legacy 再导出，避免全仓 ImportError
from app.models.config_legacy import (  # noqa: E402
    EmulatorConfig,
    GeneralConfig,
    GeneralUserConfig,
    MaaConfig,
    MaaEndConfig,
    MaaEndUserConfig,
    MaaFWConfig,
    MaaFWUserConfig,
    MaaPlanConfig,
    MaaUserConfig,
    OkwwConfig,
    OkwwUserConfig,
    PluginConfig,
    SrcConfig,
    SrcUserConfig,
)

CLASS_BOOK = {
    "MAA": MaaConfig,
    "MaaPlan": MaaPlanConfig,
    "SRC": SrcConfig,
    "MaaEnd": MaaEndConfig,
    "MaaFW": MaaFWConfig,
    "General": GeneralConfig,
    "Okww": OkwwConfig,
}
"""配置类映射表（仍指向 legacy ConfigBase 实现）。"""
