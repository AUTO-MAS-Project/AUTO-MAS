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

import re
from pathlib import Path

from app.core import Config
from app.services import Notify
from app.utils import get_logger
from app.models.config import M9AUserConfig

logger = get_logger("M9A通知工具")


class M9ALogAnalyzer:
    """M9A 运行日志分析器"""

    SPECIAL_TASKS = {"切换账号", "常规作战"}
    DROP_KEYWORDS = ("掉落统计:", "材料掉落总结:")
    RARITY_TAGS = {"[紫色]", "[金色]", "[蓝色]", "[绿色]", "[白色]"}

    HTML_TAG_RE = re.compile(r"<[^>]+>")

    @staticmethod
    def _strip_html(text: str) -> str:
        return M9ALogAnalyzer.HTML_TAG_RE.sub("", text).strip()

    @staticmethod
    def _extract_task_start(line: str) -> str | None:
        m = re.search(r"开始任务：(.+)$", line)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def _extract_record(line: str) -> str | None:
        m = re.search(r"\[Record\] (.+)$", line)
        if m:
            return M9ALogAnalyzer._strip_html(m.group(1).strip())
        return None

    @staticmethod
    def _is_task_start(line: str) -> bool:
        return "队列任务开始（异步）" in line

    @staticmethod
    def _is_task_complete(line: str) -> bool:
        return "队列任务完成（异步）" in line

    @staticmethod
    def _is_all_done(line: str) -> bool:
        return "任务已全部完成！" in line

    @staticmethod
    def _is_drop_line(line: str) -> bool:
        return "掉落统计:" in line or "材料掉落总结:" in line

    @staticmethod
    def parse_log(log_path: Path) -> dict:
        tasks = []
        current_task = None
        in_drops = False
        drops = []
        overall_status = "失败"
        duration = ""

        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return {
                "tasks": [],
                "overall_status": "失败",
                "duration": "",
            }

        for i, line in enumerate(lines):
            if "src=Monitor" not in line and "src=Worker" not in line:
                continue

            task_name = M9ALogAnalyzer._extract_task_start(line)
            if task_name:
                if current_task and current_task["status"] == "开始":
                    current_task["status"] = "失败"
                current_task = {
                    "name": task_name,
                    "status": "开始",
                    "details": [],
                    "extra": {},
                }
                tasks.append(current_task)
                in_drops = False
                drops = []
                continue

            if M9ALogAnalyzer._is_all_done(line):
                overall_status = "成功"
                if i + 1 < len(lines):
                    m = re.search(r"用时 (.+)", lines[i + 1])
                    if m:
                        raw_dur = m.group(1).rstrip(")")
                        duration = raw_dur
                if current_task and current_task["status"] == "开始":
                    current_task["status"] = "完成"
                continue

            if M9ALogAnalyzer._is_task_complete(line):
                if current_task and current_task["status"] == "开始":
                    current_task["status"] = "完成"
                    if current_task["name"] == "常规作战" and drops:
                        current_task["extra"]["drops"] = drops
                    drops = []
                    in_drops = False
                continue

            if M9ALogAnalyzer._is_drop_line(line):
                in_drops = True
                continue

            if in_drops and current_task and current_task["name"] == "常规作战":
                if "MonitorMarkdown" in line:
                    idx = line.find("MonitorMarkdown")
                    raw = line[idx + len("MonitorMarkdown"):].lstrip("] ")
                    drop_text = M9ALogAnalyzer._strip_html(raw.strip())
                    if drop_text and drop_text not in ("", "掉落统计:", "材料掉落总结:"):
                        drops.append(drop_text)
                    continue
                if "MonitorLog" not in line:
                    continue

            if current_task:
                record = M9ALogAnalyzer._extract_record(line)
                if record:
                    current_task["details"].append(record)
                    if current_task["name"] == "常规作战":
                        if "当前关卡" in record:
                            current_task["extra"]["stage"] = record.replace(
                                "当前关卡：", ""
                            )
                        elif "任务结束，总共刷了" in record:
                            m = re.search(r"总共刷了 (\d+) 次", record)
                            if m:
                                current_task["extra"]["count"] = m.group(1)

        if current_task and current_task["status"] == "开始":
            current_task["status"] = "失败"

        return {
            "tasks": tasks,
            "overall_status": overall_status,
            "duration": duration,
        }

    @staticmethod
    def build_notification_text(analysis: dict) -> str:
        lines = []
        for task in analysis["tasks"]:
            line = f"{task['name']} - {task['status']}"

            if task["name"] in M9ALogAnalyzer.SPECIAL_TASKS:
                if task["name"] == "切换账号" and task["details"]:
                    account_match = None
                    for d in task["details"]:
                        if "匹配到目标账号" in d:
                            account_match = d
                            break
                    if account_match:
                        line += f"（{account_match}）"

                elif task["name"] == "常规作战":
                    parts = []
                    stage = task["extra"].get("stage", "")
                    count = task["extra"].get("count", "")
                    if stage:
                        parts.append(stage)
                    if count:
                        parts.append(f"刷图{count}次")
                    if parts:
                        line += f"（{', '.join(parts)}）"

                    drops = task["extra"].get("drops", [])
                    drops = [d for d in drops if d not in M9ALogAnalyzer.RARITY_TAGS]
                    if drops:
                        lines.append(line)
                        for d in drops:
                            lines.append(f"  掉落：{d}")
                        continue

            lines.append(line)

        if analysis.get("duration"):
            lines.append(f"\n总计用时: {analysis['duration']}")

        return "\n".join(lines)


async def push_notification(
    mode: str, title: str, message: dict, user_config: M9AUserConfig | None
) -> None:
    """通过所有渠道推送通知"""

    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

    if mode == "代理结果" and (
        Config.get("Notify", "SendTaskResultTime") == "任何时刻"
        or (
            Config.get("Notify", "SendTaskResultTime") == "仅失败时"
            and message["uncompleted_count"] != 0
        )
    ):
        # 生成文本通知内容
        message_text = (
            f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
            f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
            f"{message['result']}"
        )

        # 生成HTML通知内容
        template = Config.notify_env.get_template("general_result.html")
        message_html = template.render(message)

        # ServerChan的换行是两个换行符。故而将\n替换为\n\n
        serverchan_message = message_text.replace("\n", "\n\n")

        # 发送全局通知
        if Config.get("Notify", "IfSendMail"):
            await Notify.send_mail(
                "网页", title, message_html, Config.get("Notify", "ToAddress")
            )

        if Config.get("Notify", "IfServerChan"):
            await Notify.ServerChanPush(
                title,
                f"{serverchan_message}\n\nAUTO-MAS 敬上",
                Config.get("Notify", "ServerChanKey"),
            )

        # 发送自定义Webhook通知
        for webhook in Config.Notify_CustomWebhooks.values():
            await Notify.WebhookPush(title, f"{message_text}\n\nAUTO-MAS 敬上", webhook)

        # 发送Koishi通知
        if Config.get("Notify", "IfKoishiSupport"):
            await Notify.send_koishi(f"{title}\n\n{message_text}\n\nAUTO-MAS 敬上")

    elif mode == "统计信息":
        task_details = message.get("task_details", "")
        detail_str = f"\n{task_details}\n" if task_details else ""
        message_text = (
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"M9A脚本执行结果: {message['user_result']}"
            f"{detail_str}\n"
        )

        # 生成HTML通知内容
        template = Config.notify_env.get_template("general_statistics.html")
        message_html = template.render(message)

        # ServerChan的换行是两个换行符。故而将\n替换为\n\n
        serverchan_message = message_text.replace("\n", "\n\n")

        # 发送全局通知
        if Config.get("Notify", "IfSendStatistic"):
            if Config.get("Notify", "IfSendMail"):
                await Notify.send_mail(
                    "网页", title, message_html, Config.get("Notify", "ToAddress")
                )

            if Config.get("Notify", "IfServerChan"):
                await Notify.ServerChanPush(
                    title,
                    f"{serverchan_message}\n\nAUTO-MAS 敬上",
                    Config.get("Notify", "ServerChanKey"),
                )

            # 发送自定义Webhook通知
            for webhook in Config.Notify_CustomWebhooks.values():
                await Notify.WebhookPush(
                    title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
                )

            # 发送Koishi通知
            if Config.get("Notify", "IfKoishiSupport"):
                await Notify.send_koishi(f"{title}\n\n{message_text}\n\nAUTO-MAS 敬上")

        # 发送用户单独通知
        if (
            user_config is not None
            and user_config.get("Notify", "Enabled")
            and user_config.get("Notify", "IfSendStatistic")
        ):
            # 发送邮件通知
            if user_config.get("Notify", "IfSendMail"):
                if user_config.get("Notify", "ToAddress"):
                    await Notify.send_mail(
                        "网页",
                        title,
                        message_html,
                        user_config.get("Notify", "ToAddress"),
                    )
                else:
                    logger.error("用户邮箱地址为空, 无法发送用户单独的邮件通知")

            # 发送ServerChan通知
            if user_config.get("Notify", "IfServerChan"):
                if user_config.get("Notify", "ServerChanKey"):
                    await Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\n\nAUTO-MAS 敬上",
                        user_config.get("Notify", "ServerChanKey"),
                    )
                else:
                    logger.error(
                        "用户ServerChan密钥为空, 无法发送用户单独的ServerChan通知"
                    )

            # 推送CompanyWebHookBot通知
            for webhook in user_config.Notify_CustomWebhooks.values():
                await Notify.WebhookPush(
                    title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
                )

    
