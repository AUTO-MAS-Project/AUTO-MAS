from __future__ import annotations

from typing import Any

from app.plugins.fields import PluginField


schema = {
    "__no_plugin_config__": {
        "type": "boolean",
        "default": True,
        "hidden": True,
        "configurable": False,
        "title": "No plugin-level configuration",
    },
}


SCRIPT_GROUPS = (
    PluginField.group(
        "Info",
        "基础信息",
        [
            PluginField.string("Name", "脚本名称", "新 MaaFW 脚本"),
            PluginField.string("ProjectLabel", "项目标签", ""),
            PluginField.folder(
                "Path",
                "MaaFW 项目路径",
                "",
                placeholder="选择包含 interface.json 的项目目录",
                size="large",
                required=True,
            ),
            PluginField.string("Controller", "Controller", ""),
            PluginField.string("Resource", "Resource", ""),
        ],
    ),
    PluginField.group(
        "Emulator",
        "模拟器",
        [
            PluginField.related_id(
                "Id",
                "模拟器",
                "-",
                related_config="EmulatorConfig",
            ),
            PluginField.string("Index", "模拟器实例", "-"),
        ],
    ),
    PluginField.group(
        "Device",
        "控制器",
        [
            PluginField.file("AdbPath", "ADB 路径", "", size="large"),
            PluginField.string("AdbAddress", "ADB 地址", ""),
            PluginField.number(
                "AdbScreencapMethods",
                "ADB 截图方法",
                -57,
                min=-999,
                max=999999999999,
                step=1,
            ),
            PluginField.number(
                "AdbInputMethods",
                "ADB 输入方法",
                -1,
                min=-999,
                max=999999999999,
                step=1,
            ),
            PluginField.number("HWnd", "Win32 窗口句柄", 0, min=0, max=999999999999, step=1),
            PluginField.number(
                "Win32ScreencapMethod",
                "Win32 截图方法",
                0,
                min=0,
                max=999999999999,
                step=1,
            ),
            PluginField.number(
                "Win32MouseMethod",
                "Win32 鼠标方法",
                0,
                min=0,
                max=999999999999,
                step=1,
            ),
            PluginField.number(
                "Win32KeyboardMethod",
                "Win32 键盘方法",
                0,
                min=0,
                max=999999999999,
                step=1,
            ),
            PluginField.number(
                "GamepadType",
                "Gamepad 类型",
                0,
                min=0,
                max=999999999999,
                step=1,
            ),
            PluginField.string("PlayCoverAddress", "PlayCover 地址", ""),
            PluginField.string("PlayCoverUuid", "PlayCover UUID", ""),
        ],
    ),
    PluginField.group(
        "Game",
        "游戏",
        [
            PluginField.file("Path", "游戏路径", "", size="large"),
            PluginField.string("Arguments", "启动参数", ""),
            PluginField.number("WaitTime", "等待窗口时间", 60, min=0, max=9999, step=1),
            PluginField.boolean("CloseOnFinish", "结束后关闭游戏", True),
        ],
    ),
    PluginField.group(
        "Update",
        "项目更新",
        [
            PluginField.boolean("IfAutoUpdate", "运行前自动更新", True),
            PluginField.select(
                "Source",
                "更新源",
                "MirrorChyan",
                ["MirrorChyan", "GitHub"],
            ),
            PluginField.select("Channel", "更新渠道", "", ["", "stable", "beta"]),
            PluginField.string("MirrorChyanCDK", "Mirror 酱 CDK", "", sensitive=True),
            PluginField.string("GitHubRepo", "GitHub 仓库", ""),
            PluginField.string("GitHubTag", "GitHub Tag", ""),
            PluginField.string("GitHubAssetPattern", "GitHub Asset 匹配", ""),
        ],
    ),
    PluginField.group(
        "Run",
        "运行",
        [
            PluginField.number("ProxyTimesLimit", "每日代理次数限制", 0, min=0, max=9999, step=1),
            PluginField.number("RunTimesLimit", "失败重试次数", 1, min=1, max=9999, step=1),
            PluginField.number("RunTimeLimit", "单次运行超时（分钟）", 30, min=1, max=9999, step=1),
            PluginField.json("DailyOnceTasks", "每日一次任务", "[]", json_type="array"),
            PluginField.json("WeeklyOnceTasks", "每周一次任务", "[]", json_type="array"),
            PluginField.json("MonthlyOnceTasks", "每月一次任务", "[]", json_type="array"),
        ],
    ),
)


USER_GROUPS = (
    PluginField.group(
        "Info",
        "基础信息",
        [
            PluginField.string("Name", "用户名称", "新用户", validator="username"),
            PluginField.boolean("Status", "启用用户", True),
            PluginField.number("RemainedDay", "剩余天数", -1, min=-1, max=9999, step=1),
            PluginField.boolean("IfScriptBeforeTask", "任务前脚本", False),
            PluginField.file("ScriptBeforeTask", "任务前脚本路径", "", size="large"),
            PluginField.boolean("IfScriptAfterTask", "任务后脚本", False),
            PluginField.file("ScriptAfterTask", "任务后脚本路径", "", size="large"),
            PluginField.string("Notes", "备注", "无", rows=3, size="large"),
            PluginField.string("Account", "账号", ""),
            PluginField.string("Password", "密码", "", sensitive=True),
            PluginField.string("Controller", "Controller", ""),
            PluginField.string("Resource", "Resource", ""),
        ],
    ),
    PluginField.group(
        "Task",
        "任务",
        [
            PluginField.string("SelectedPreset", "Preset", ""),
            PluginField.json("TaskSnapshot", "任务快照", "{}", json_type="object"),
        ],
    ),
    PluginField.group(
        "Device",
        "控制器覆盖",
        [
            PluginField.string("AdbAddress", "ADB 地址", ""),
            PluginField.number("HWnd", "Win32 窗口句柄", 0, min=0, max=999999999999, step=1),
            PluginField.string("PlayCoverAddress", "PlayCover 地址", ""),
            PluginField.string("PlayCoverUuid", "PlayCover UUID", ""),
        ],
    ),
    PluginField.group(
        "Data",
        "运行数据",
        [
            PluginField.datetime("LastProxyDate", "上次代理日期", "2000-01-01", format="%Y-%m-%d"),
            PluginField.number("ProxyTimes", "今日代理次数", 0, min=0, max=9999, step=1),
            PluginField.boolean("IfPassCheck", "检查通过", True),
            PluginField.string("LastProxyStatus", "上次运行状态", "未知"),
            PluginField.json("PeriodTaskRecords", "周期任务记录", "{}", json_type="object"),
        ],
    ),
    PluginField.group(
        "Notify",
        "通知",
        [
            PluginField.boolean("Enabled", "启用通知", False),
            PluginField.boolean("IfSendStatistic", "发送统计信息", False),
            PluginField.boolean("IfSendMail", "邮件通知", False),
            PluginField.string("ToAddress", "收件地址", ""),
            PluginField.boolean("IfServerChan", "启用 Server 酱", False),
            PluginField.string("ServerChanKey", "Server 酱密钥", "", sensitive=True),
            PluginField.json("CustomWebhooks", "自定义 Webhook", "{}", json_type="object"),
        ],
    ),
)


def build_source_config(script_data: dict[str, Any]) -> dict[str, Any] | None:
    update = script_data.get("Update")
    if not isinstance(update, dict):
        return None

    source = str(update.get("Source") or "").strip()
    if source == "GitHub":
        return {
            "source": "github_release",
            "repo": str(update.get("GitHubRepo") or "").strip(),
            "tag": str(update.get("GitHubTag") or "").strip(),
            "asset_pattern": str(update.get("GitHubAssetPattern") or "").strip(),
            "channel": str(update.get("Channel") or "").strip(),
        }
    if source == "MirrorChyan":
        return {
            "source": "mirrorchyan",
            "channel": str(update.get("Channel") or "").strip(),
            "cdk": str(update.get("MirrorChyanCDK") or "").strip(),
        }
    return None
