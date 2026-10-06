"""MAA 用户配置。"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from annotated_types import Ge, Le
from pydantic import Field

from auto_mas_core import (
    Config as HostConfig,
    ConfigGroup,
    FilePath,
    JsonDictString,
    JsonListString,
    TagItem,
    UserEntry,
    Virtual,
    encrypted,
    select,
    ui,
    virtual_field,
)

from ..constants import get_game_day_tz, game_now
from .choices import (
    _ANNIHILATION,
    _DEPOT_DEFAULT,
    _INFRAST,
    _SERVERS,
    _SERIES,
    _WEEKDAYS,
)
from .plan import MaaPlan

class MaaUser(UserEntry):
    """MAA 用户配置。"""

    class Info(UserEntry.Info):
        name: str = Field(default="新用户", description="用户名")
        account_id: str = Field(default="", description="用户 ID")
        password: Annotated[str, encrypted(), ui(secret=True)] = Field(
            default="", description="密码"
        )
        mode: Annotated[Literal["脚本", "用户", "直控"], select()] = Field(
            default="脚本", description="配置来源"
        )
        if_quick_config: bool = Field(default=True, description="是否启用快速配置")
        server: Annotated[Literal[*_SERVERS], select()] = Field(
            default="Official", description="游戏服务器"
        )
        remained_day: Annotated[int, Ge(-1), Le(9999)] = Field(
            default=-1, description="剩余天数"
        )
        annihilation: Annotated[Literal[*_ANNIHILATION], select()] = Field(
            default="Annihilation", description="剿灭模式"
        )
        annihilation_start_weekday: Annotated[Literal[*_WEEKDAYS], select()] = Field(
            default="Monday", description="剿灭开始星期"
        )
        infrast_mode: Annotated[Literal[*_INFRAST], select()] = Field(
            default="Normal", description="基建模式"
        )
        infrast_name: Virtual[str] = None
        if_script_before_task: bool = Field(default=False, description="任务前执行脚本")
        script_before_task: FilePath = Field(default=None, description="任务前脚本")
        if_script_after_task: bool = Field(default=False, description="任务后执行脚本")
        script_after_task: FilePath = Field(default=None, description="任务后脚本")
        notes: str = Field(default="无", description="备注")
        medicine_numb: Annotated[int, Ge(0), Le(9999)] = Field(
            default=0, description="理智药数量"
        )
        series_numb: Annotated[Literal[*_SERIES], select()] = Field(
            default="0", description="连战次数"
        )
        stage: str = Field(default="-", description="关卡")
        stage_1: str = Field(default="-", description="关卡 1")
        stage_2: str = Field(default="-", description="关卡 2")
        stage_3: str = Field(default="-", description="关卡 3")

    class Data(ConfigGroup):
        last_proxy_date: date = Field(
            default=date(2000, 1, 1), description="上次代理日期"
        )
        proxy_times: Annotated[int, Ge(0), Le(9999)] = Field(
            default=0, description="代理次数"
        )
        annihilation_completed_week: str = Field(
            default="2000-W01", description="剿灭达到周上限时的 ISO 周"
        )
        green_ticket_store_month: str = Field(
            default="2000-01", description="上次完成绿票商店购买的月份"
        )
        last_res_version: str = Field(default="", description="上次成功代理时的资源版本")
        cultivate_notice: str = Field(default="", description="养成接管提示")
        custom_infrast: JsonDictString = Field(default="{ }", description="自定义基建配置")
        infrast_plan_index: Annotated[int, Ge(0), Le(9999)] = Field(
            default=0, description="无时段排班表下一班索引"
        )

    class Task(ConfigGroup):
        if_start_up: bool = Field(default=True, description="是否自动唤醒")
        if_fight: bool = Field(default=True, description="是否理智作战")
        if_infrast: bool = Field(default=True, description="是否基建换班")
        if_recruit: bool = Field(default=True, description="是否公开招募")
        if_mall: bool = Field(default=True, description="是否信用收支")
        if_award: bool = Field(default=True, description="是否领取奖励")
        if_switch_theme: bool = Field(default=False, description="是否更换主题")
        if_depot_maintain: bool = Field(default=True, description="是否库存保持")
        depot_maintain_plans: JsonListString = Field(
            default=_DEPOT_DEFAULT, description="库存保持计划"
        )
        if_green_ticket_store: bool = Field(
            default=False, description="是否每月自动购买一次绿票商店"
        )
        if_activity_first: bool = Field(default=True, description="活动期间是否优先刷活动关")
        activity_stage_index: Annotated[int, Ge(1), Le(9999)] = Field(
            default=1, description="优先刷取的活动关卡序号"
        )
        activity_medicine_numb: Annotated[int, Ge(0), Le(9999)] = Field(
            default=0, description="活动关优先任务吃理智药数量"
        )
        if_cultivate: bool = Field(default=False, description="是否干员养成")
        cultivate_targets: JsonListString = Field(default="[]", description="干员养成目标")
        cultivate_skip_during_activity: bool = Field(
            default=False, description="活动期间是否跳过养成计划"
        )
        cultivate_skip_during_resource_collection: bool = Field(
            default=False, description="资源收集期是否跳过养成计划"
        )
        cultivate_skland_account: str = Field(
            default="", description="森空岛绑定：签到账号组 UUID"
        )
        cultivate_skland_uid: str = Field(
            default="", description="森空岛绑定：角色游戏 uid"
        )

    class Notify(ConfigGroup):
        enabled: bool = Field(default=False, description="是否启用通知")
        if_send_statistic: bool = Field(default=False, description="是否发送统计信息")
        if_send_six_star: bool = Field(default=False, description="是否发送六星通知")
        if_send_mail: bool = Field(default=False, description="是否发送邮件")
        to_address: str = Field(default="", description="收件地址")
        if_server_chan: bool = Field(default=False, description="是否启用 Server 酱")
        server_chan_key: Annotated[str, ui(secret=True)] = Field(
            default="", description="Server 酱密钥"
        )

    info: Info = Field(default_factory=Info, description="用户信息")
    data: Data = Field(default_factory=Data, description="运行数据")
    task: Task = Field(default_factory=Task, description="任务开关")
    notify: Notify = Field(default_factory=Notify, description="通知")

    @virtual_field("info.infrast_name")
    def compute_infrast_name(self) -> str:
        """自定义基建文件标题摘要。"""

        if self.info.infrast_mode != "Custom":
            return "未使用自定义基建模式"
        try:
            payload = json.loads(self.data.custom_infrast or "{}")
        except json.JSONDecodeError:
            return "未命名自定义基建"
        if not isinstance(payload, dict):
            return "未命名自定义基建"
        title = payload.get("title", "文件标题")
        desc = payload.get("description", "文件描述")
        if title != "文件标题" and desc != "文件描述":
            return f"{title} - {desc}"
        if title != "文件标题":
            return str(title)
        if payload.get("id"):
            return str(payload["id"])
        return "未命名自定义基建"

    @virtual_field("info.tags")
    def compute_tags(self) -> list[TagItem]:
        """用户卡片标签：代理日、剩余天数、基建、关卡。"""

        tags: list[TagItem] = []
        tz = get_game_day_tz(self.info.server)
        last = self.data.last_proxy_date
        today = datetime_today(tz)
        if last == today:
            tags.append(TagItem(text="今日已代理", color="green"))
        else:
            tags.append(TagItem(text="今日未代理", color="orange"))
        day = self.info.remained_day
        if day == -1:
            tags.append(TagItem(text="剩余天数：不限", color="blue"))
        elif day == 0:
            tags.append(TagItem(text="剩余天数：0", color="red"))
        else:
            tags.append(TagItem(text=f"剩余天数：{day}", color="blue"))
        if self.task.if_infrast:
            mode = self.info.infrast_mode
            if mode == "Normal":
                text = "基建：常规"
            elif mode == "Rotation":
                text = "基建：轮换"
            elif mode == "Custom":
                name = self.info.infrast_name or ""
                if len(name) >= 10:
                    name = name[:10] + "..."
                text = f"基建：{name}"
            else:
                text = "基建：开启"
            tags.append(TagItem(text=text, color="purple"))
        else:
            tags.append(TagItem(text="基建：关闭", color="red"))
        pid = (self.info.plan_id or "-").strip()
        if pid in ("", "-", "Fixed"):
            tags.append(TagItem(text=f"主关卡：{self.info.stage}", color="blue"))
        else:
            try:
                plan = HostConfig.PlanConfig[UUID(pid)]
            except Exception:
                plan = None
            if isinstance(plan, MaaPlan):
                tags.append(
                    TagItem(
                        text=f"主关卡：{plan.current_value('Stage', self.info.server)}",
                        color="green",
                    )
                )
            else:
                tags.append(TagItem(text=f"主关卡：{self.info.stage}", color="green"))
        notes = (self.info.notes or "").strip()
        if notes and notes != "无":
            tags.append(TagItem(text=notes, color="gray"))
        return tags


def datetime_today(tz) -> date:
    from datetime import datetime

    return datetime.now(tz=tz).date()

