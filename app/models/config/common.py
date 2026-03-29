import calendar

from ..ConfigBase import (
    ConfigBase,
    MultipleConfig,
    ConfigItem,
    MultipleUIDValidator,
    BoolValidator,
    OptionsValidator,
    MultipleOptionsValidator,
    RangeValidator,
    DateTimeValidator,
    JSONValidator,
    URLValidator,
    EmulatorPathValidator,
)


class EmulatorConfig(ConfigBase):
    """模拟器配置"""

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## 模拟器名称
        self.Info_Name = ConfigItem("Info", "Name", "新模拟器")
        ## 模拟器类型
        self.Info_Type = ConfigItem(
            "Info",
            "Type",
            "general",
            OptionsValidator(
                [
                    "general",
                    "mumu",
                    "ldplayer",
                    # "nox",  # 以下都是骗你的, 根本没有写~~
                    # "memu",
                    # "blueStacks",
                ]
            ),
            legacy_group="Data",
        )
        ## 模拟器路径
        self.Info_Path = ConfigItem(
            "Info", "Path", "", EmulatorPathValidator(self.Info_Type)
        )
        ## 老板键快捷键配置
        self.Info_BossKey = ConfigItem(
            "Info", "BossKey", "[ ]", JSONValidator(list), legacy_group="Data"
        )
        ## 最大等待时间（秒）
        self.Info_MaxWaitTime = ConfigItem(
            "Info", "MaxWaitTime", 60, RangeValidator(1, 9999), legacy_group="Data"
        )

        super().__init__()


class Webhook(ConfigBase):
    """Webhook 配置"""

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## Webhook 名称
        self.Info_Name = ConfigItem("Info", "Name", "新自定义 Webhook 通知")
        ## 是否启用
        self.Info_Enabled = ConfigItem("Info", "Enabled", True, BoolValidator())

        ## Data ------------------------------------------------------------
        ## Webhook URL 地址
        self.Data_Url = ConfigItem("Data", "Url", "", URLValidator())
        ## 消息模板
        self.Data_Template = ConfigItem("Data", "Template", "")
        ## 请求头
        self.Data_Headers = ConfigItem("Data", "Headers", "{ }", JSONValidator())
        ## 请求方法
        self.Data_Method = ConfigItem(
            "Data", "Method", "POST", OptionsValidator(["POST", "GET"])
        )

        super().__init__()


class QueueItem(ConfigBase):
    """队列项配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## 脚本 ID
        self.Info_ScriptId = ConfigItem(
            "Info",
            "ScriptId",
            "-",
            MultipleUIDValidator("-", self.related_config, "ScriptConfig"),
        )

        super().__init__()


class TimeSet(ConfigBase):
    """时间设置配置"""

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## 是否启用
        self.Info_Enabled = ConfigItem("Info", "Enabled", True, BoolValidator())
        ## 执行周期
        self.Info_Days = ConfigItem(
            "Info",
            "Days",
            list(calendar.day_name),
            MultipleOptionsValidator(list(calendar.day_name)),
        )
        ## 执行时间
        self.Info_Time = ConfigItem("Info", "Time", "00:00", DateTimeValidator("%H:%M"))

        super().__init__()


class QueueConfig(ConfigBase):
    """队列配置"""

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## 队列名称
        self.Info_Name = ConfigItem("Info", "Name", "新队列")
        ## 是否启用定时启动
        self.Info_TimeEnabled = ConfigItem(
            "Info", "TimeEnabled", False, BoolValidator()
        )
        ## 是否在启动时自动运行
        self.Info_StartUpEnabled = ConfigItem(
            "Info", "StartUpEnabled", False, BoolValidator()
        )
        ## 完成后操作
        self.Info_AfterAccomplish = ConfigItem(
            "Info",
            "AfterAccomplish",
            "NoAction",
            OptionsValidator(
                [
                    "NoAction",
                    "Shutdown",
                    "ShutdownForce",
                    "Reboot",
                    "Hibernate",
                    "Sleep",
                    "KillSelf",
                ]
            ),
        )

        ## Data ------------------------------------------------------------
        ## 上次定时启动时间
        self.Data_LastTimedStart = ConfigItem(
            "Data",
            "LastTimedStart",
            "2000-01-01 00:00",
            DateTimeValidator("%Y-%m-%d %H:%M"),
        )

        self.TimeSet = MultipleConfig([TimeSet])
        self.QueueItem = MultipleConfig([QueueItem])

        super().__init__()


__all__ = ["EmulatorConfig", "Webhook", "QueueItem", "TimeSet", "QueueConfig"]
