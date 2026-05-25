from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.plugins.fields import PluginField
from app.utils.constants import UTC4


def _option_values(values: list[str]) -> list[dict[str, str]]:
    return [{"label": value, "value": value} for value in values]


def _build_user_tags(config: Any) -> str:
    """生成通用脚本用户标签。"""

    tags: list[dict[str, str]] = []

    if (
        datetime.strptime(config.get("Data", "LastProxyDate"), "%Y-%m-%d").date()
        == datetime.now(tz=UTC4).date()
    ):
        tags.append(
            {
                "text": f"任务：已代理{config.get('Data', 'ProxyTimes')}次",
                "color": "green",
            }
        )
    else:
        tags.append({"text": "任务：未代理", "color": "orange"})

    remained_day = config.get("Info", "RemainedDay")
    if remained_day == -1:
        tag_color = "gold"
    elif remained_day == 0:
        tag_color = "red"
    elif remained_day <= 3:
        tag_color = "orange"
    elif remained_day <= 7:
        tag_color = "yellow"
    elif remained_day <= 30:
        tag_color = "blue"
    else:
        tag_color = "green"
    tags.append(
        {
            "text": (
                f"剩余天数：{remained_day}天"
                if remained_day >= 0
                else "剩余天数：无限制"
            ),
            "color": tag_color,
        }
    )

    notes = config.get("Info", "Notes")
    tags.append(
        {
            "text": f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}...",
            "color": "pink",
        }
    )

    return json.dumps(tags, ensure_ascii=False)


WEBHOOK_GROUPS = (
    PluginField.group(
        "Info",
        "基础信息",
        [
            PluginField.string("Name", "Webhook 名称", "新自定义 Webhook 通知"),
            PluginField.boolean("Enabled", "启用 Webhook", True),
        ],
    ),
    PluginField.group(
        "Data",
        "请求设置",
        [
            PluginField.string("Url", "请求地址", "", format="url"),
            PluginField.string("Template", "消息模板", "", rows=4, size="large"),
            PluginField.json("Headers", "请求头", "{ }"),
            PluginField.select(
                "Method",
                "请求方法",
                "POST",
                _option_values(["POST", "GET"]),
            ),
        ],
    ),
)


SCRIPT_GROUPS = (
    PluginField.group(
        "Info",
        "基础信息",
        [
            PluginField.string("Name", "脚本名称", "新通用脚本"),
            PluginField.file(
                "RootPath",
                "根目录路径",
                str(Path.cwd()),
                placeholder="选择脚本根目录",
                size="medium",
            ),
        ],
    ),
    PluginField.group(
        "Script",
        "脚本设置",
        [
            PluginField.file(
                "ScriptPath",
                "脚本入口",
                str(Path.cwd()),
                placeholder="选择脚本可执行文件或入口目录",
                size="large",
            ),
            PluginField.string(
                "Arguments",
                "脚本参数",
                "",
                rows=3,
                size="large",
                help="多段参数可使用 | 分隔；若需指定不同入口，可使用 相对路径%参数 的格式。",
            ),
            PluginField.boolean("IfTrackProcess", "追踪子进程", False),
            PluginField.string("TrackProcessName", "追踪进程名称", ""),
            PluginField.string("TrackProcessExe", "追踪进程路径", ""),
            PluginField.string("TrackProcessCmdline", "追踪进程命令行", ""),
            PluginField.file(
                "ConfigPath",
                "配置路径",
                str(Path.cwd()),
                placeholder="选择脚本配置文件或配置目录",
                size="large",
            ),
            PluginField.select(
                "ConfigPathMode",
                "配置路径模式",
                "File",
                _option_values(["File", "Folder"]),
            ),
            PluginField.select(
                "UpdateConfigMode",
                "配置回写策略",
                "Never",
                _option_values(["Never", "Success", "Failure", "Always"]),
            ),
            PluginField.file(
                "LogPath",
                "日志路径",
                str(Path.cwd()),
                placeholder="选择日志文件路径",
                size="large",
            ),
            PluginField.string("LogPathFormat", "日志文件名格式", "%Y-%m-%d"),
            PluginField.number("LogTimeStart", "日志时间起始位置", 1, min=1, max=9999, step=1),
            PluginField.number("LogTimeEnd", "日志时间结束位置", 1, min=1, max=9999, step=1),
            PluginField.string("LogTimeFormat", "日志时间格式", "%Y-%m-%d %H:%M:%S"),
            PluginField.string(
                "SuccessLog",
                "成功日志关键字",
                "",
                rows=3,
                size="large",
                help="多个成功关键字可使用 | 分隔。",
            ),
            PluginField.string(
                "ErrorLog",
                "失败日志关键字",
                "",
                rows=3,
                size="large",
                help="多个失败关键字可使用 | 分隔。",
            ),
        ],
    ),
    PluginField.group(
        "Game",
        "游戏设置",
        [
            PluginField.boolean("Enabled", "启用游戏联动", False),
            PluginField.select(
                "Type",
                "游戏类型",
                "Emulator",
                _option_values(["Emulator", "Client", "URL"]),
            ),
            PluginField.file(
                "Path",
                "游戏路径",
                str(Path.cwd()),
                placeholder="选择游戏可执行文件",
                size="large",
            ),
            PluginField.string("URL", "游戏协议地址", ""),
            PluginField.string("ProcessName", "游戏进程名", ""),
            PluginField.string("Arguments", "游戏启动参数", ""),
            PluginField.number("WaitTime", "启动等待时间", 0, min=0, max=9999, step=1),
            PluginField.boolean("IfForceClose", "任务结束后强制关闭", False),
            PluginField.related_id(
                "EmulatorId",
                "模拟器",
                "-",
                related_config="EmulatorConfig",
            ),
            PluginField.string("EmulatorIndex", "多开实例", "-"),
        ],
    ),
    PluginField.group(
        "Run",
        "运行设置",
        [
            PluginField.number("ProxyTimesLimit", "代理次数限制", 0, min=0, max=9999, step=1),
            PluginField.number("RunTimesLimit", "运行次数限制", 3, min=1, max=9999, step=1),
            PluginField.number("RunTimeLimit", "运行时间限制（分钟）", 10, min=1, max=9999, step=1),
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
            PluginField.file(
                "ScriptBeforeTask",
                "任务前脚本路径",
                str(Path.cwd()),
                placeholder="选择任务前脚本文件",
                size="large",
            ),
            PluginField.boolean("IfScriptAfterTask", "任务后脚本", False),
            PluginField.file(
                "ScriptAfterTask",
                "任务后脚本路径",
                str(Path.cwd()),
                placeholder="选择任务后脚本文件",
                size="large",
            ),
            PluginField.string(
                "Notes",
                "备注",
                "无",
                rows=4,
                size="large",
                placeholder="填写该用户的备注信息",
            ),
            PluginField.tag(
                "Tag",
                "用户标签",
                "[ ]",
                handler=_build_user_tags,
                help="运行时自动生成，仅用于展示。",
            ),
        ],
    ),
    PluginField.group(
        "Notify",
        "通知设置",
        [
            PluginField.boolean("Enabled", "启用通知", False),
            PluginField.boolean("IfSendStatistic", "发送统计信息", False),
            PluginField.boolean("IfSendMail", "邮件通知", False),
            PluginField.string("ToAddress", "收件邮箱", ""),
            PluginField.boolean("IfServerChan", "Server酱通知", False),
            PluginField.string("ServerChanKey", "Server酱 SENDKEY", ""),
            PluginField.multiple(
                "CustomWebhooks",
                "自定义 Webhook 通知",
                WEBHOOK_GROUPS,
                class_name="Webhook",
            ),
        ],
    ),
    PluginField.group(
        "Data",
        "运行数据",
        [
            PluginField.datetime(
                "LastProxyDate",
                "上次代理日期",
                "2000-01-01",
                format="%Y-%m-%d",
                readonly=True,
                help="运行结束后自动更新。",
            ),
            PluginField.number(
                "ProxyTimes",
                "今日代理次数",
                0,
                min=0,
                max=9999,
                step=1,
                readonly=True,
                help="运行结束后自动更新。",
            ),
        ],
    ),
    PluginField.group(
        "Action",
        "交互操作",
        [
            PluginField.button(
                "GeneralConfig",
                "通用配置",
                {
                    "label": "通用配置",
                    "path": "/api/dispatch/start",
                    "method": "POST",
                    "payload": {"taskId": "{{userId}}", "mode": "ScriptConfig"},
                    "refresh": True,
                    "session": {
                        "response_task_id_key": "taskId",
                        "stop_path": "/api/dispatch/stop",
                        "stop_method": "POST",
                        "stop_payload": {"taskId": "{{session.websocketId}}"},
                        "overlay_title": "正在进行通用配置",
                        "overlay_description": (
                            "当前正在进行该用户的通用配置，请在配置界面完成相关设置。\n"
                            "配置完成后，请点击“保存配置”按钮结束配置会话。"
                        ),
                        "stop_label": "保存配置",
                        "start_message": "已开始配置用户 {{userName}} 的通用设置",
                        "success_message": "用户 {{userName}} 的配置已完成",
                        "stop_message": "用户 {{userName}} 的通用配置已保存",
                        "timeout_ms": 1800000,
                        "timeout_auto_stop": True,
                        "timeout_message": (
                            "用户 {{userName}} 的配置会话已超时（30分钟），正在自动保存配置..."
                        ),
                    },
                },
                help="启动该用户的脚本配置会话，完成后点击保存配置结束会话。",
            ),
        ],
    ),
)


__all__ = [
    "SCRIPT_GROUPS",
    "USER_GROUPS",
    "WEBHOOK_GROUPS",
]
