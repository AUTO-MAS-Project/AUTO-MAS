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
    """M9A 运行日志分析器
    用于解析 M9A 运行日志，提取任务执行详情（任务名、状态、关卡信息、掉落物品等），
    并提供格式化通知文本的方法。
    """

    SPECIAL_TASKS = {"切换账号", "常规作战"}
    """需要提取额外详情的任务名集合"""

    DROP_KEYWORDS = ("掉落统计:", "材料掉落总结:")
    """掉落物统计行的关键词"""

    RARITY_TAGS = {"[紫色]", "[金色]", "[蓝色]", "[绿色]", "[白色]"}
    """稀有度标签，在最终输出中过滤掉"""

    HTML_TAG_RE = re.compile(r"<[^>]+>")

    @staticmethod
    def _strip_html(text: str) -> str:
        """去除 HTML 标签，如 <span style=...>xxx</span>"""
        return M9ALogAnalyzer.HTML_TAG_RE.sub("", text).strip()

    @staticmethod
    def _extract_task_start(line: str) -> str | None:
        """从"开始任务：XXX"行提取任务名"""
        m = re.search(r"开始任务：(.+)$", line)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def _extract_record(line: str) -> str | None:
        """从 [Record] 行提取记录文本（已去除 HTML 标签）"""
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
        return any(kw in line for kw in M9ALogAnalyzer.DROP_KEYWORDS)

    @staticmethod
    def parse_log(log_path: Path) -> dict:
        """解析 M9A 运行日志文件

        Args:
            log_path: 日志文件路径

        Returns:
            解析结果字典，结构如下：
            {
                "tasks": [
                    {
                        "name": "启动游戏",
                        "status": "完成" | "失败" | "开始",
                        "details": ["文本内容", ...],
                        "extra": {
                            "stage": "12-5, 难度：Hard",   # 仅常规作战
                            "count": "1",                   # 仅常规作战
                            "drops": ["物品 x1", ...]       # 仅常规作战
                        }
                    },
                    ...
                ],
                "overall_status": "成功" | "失败",
                "duration": "00:05:30"
            }
        """
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
                        duration = m.group(1).rstrip(")")
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
                    if drop_text and drop_text not in ("",) + M9ALogAnalyzer.DROP_KEYWORDS:
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
        """根据 parse_log 的分析结果构建可读的通知文本

        特殊任务（切换账号、常规作战）会附加额外信息：
        - 切换账号：附加匹配到的目标账号
        - 常规作战：附加关卡信息、刷图次数、每项掉落物

        Args:
            analysis: parse_log 返回的分析结果字典

        Returns:
            格式化的通知文本
        """
        lines = []
        for task in analysis["tasks"]:
            line = f"{task['name']} - {task['status']}"

            if task["name"] not in M9ALogAnalyzer.SPECIAL_TASKS:
                lines.append(line)
                continue

            if task["name"] == "切换账号":
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


# ==================== 通知推送辅助函数 ====================


async def _send_to_all_global_channels(
    title: str, message_text: str, message_html: str
) -> None:
    """向所有启用的全局通知渠道推送消息

    Args:
        title: 通知标题
        message_text: 纯文本格式内容
        message_html: HTML 格式内容
    """
    serverchan_message = message_text.replace("\n", "\n\n")

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

    for webhook in Config.Notify_CustomWebhooks.values():
        await Notify.WebhookPush(title, f"{message_text}\n\nAUTO-MAS 敬上", webhook)

    if Config.get("Notify", "IfKoishiSupport"):
        await Notify.send_koishi(f"{title}\n\n{message_text}\n\nAUTO-MAS 敬上")


async def _send_to_user_channels(
    title: str, message_text: str, message_html: str,
    user_config: M9AUserConfig
) -> None:
    """向用户配置的独立通知渠道推送消息

    与全局渠道不同，这里额外检查用户的 Enabled 和 IfSendStatistic 配置。

    Args:
        title: 通知标题
        message_text: 纯文本格式内容
        message_html: HTML 格式内容
        user_config: 用户配置对象
    """
    serverchan_message = message_text.replace("\n", "\n\n")

    if user_config.get("Notify", "IfSendMail"):
        if not user_config.get("Notify", "ToAddress"):
            logger.error("用户邮箱地址为空，无法发送邮件通知")
        else:
            await Notify.send_mail(
                "网页", title, message_html, user_config.get("Notify", "ToAddress")
            )

    if user_config.get("Notify", "IfServerChan"):
        if not user_config.get("Notify", "ServerChanKey"):
            logger.error("用户 ServerChan 密钥为空，无法发送通知")
        else:
            await Notify.ServerChanPush(
                title,
                f"{serverchan_message}\n\nAUTO-MAS 敬上",
                user_config.get("Notify", "ServerChanKey"),
            )

    for webhook in user_config.Notify_CustomWebhooks.values():
        await Notify.WebhookPush(title, f"{message_text}\n\nAUTO-MAS 敬上", webhook)


# ==================== 对外接口 ====================


async def push_notification(
    mode: str, title: str, message: dict, user_config: M9AUserConfig | None
) -> None:
    """统一通知推送入口，根据 mode 分支到不同策略

    Args:
        mode: 通知模式 - "代理结果" 或 "统计信息"
        title: 通知标题
        message: 通知内容字典，各模式所需字段不同：
            - "代理结果": start_time, end_time, completed_count, uncompleted_count, result
            - "统计信息": start_time, end_time, user_result, task_details
        user_config: 用户配置（统计信息模式用于发送独立通知，可为 None）
    """
    logger.info(f"开始推送通知，模式: {mode}，标题: {title}")

    if mode == "代理结果":
        await _push_proxy_result(title, message)
    elif mode == "统计信息":
        await _push_statistics(title, message, user_config)


async def _push_proxy_result(title: str, message: dict) -> None:
    """推送全局代理结果通知"""
    result_time_setting = Config.get("Notify", "SendTaskResultTime")
    if result_time_setting != "任何时刻" and (
        result_time_setting != "仅失败时" or message["uncompleted_count"] == 0
    ):
        logger.debug("当前 SendTaskResultTime 配置不满足推送条件，跳过")
        return

    message_text = (
        f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
        f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
        f"{message['result']}"
    )

    template = Config.notify_env.get_template("general_result.html")
    message_html = template.render(message)

    await _send_to_all_global_channels(title, message_text, message_html)


async def _push_statistics(
    title: str, message: dict, user_config: M9AUserConfig | None
) -> None:
    """推送统计信息通知（全局 + 用户独立）"""
    task_details = message.get("task_details", "")
    detail_str = f"\n{task_details}\n" if task_details else ""
    message_text = (
        f"开始时间: {message['start_time']}\n"
        f"结束时间: {message['end_time']}\n"
        f"M9A脚本执行结果: {message['user_result']}"
        f"{detail_str}\n"
    )

    template = Config.notify_env.get_template("general_statistics.html")
    message_html = template.render(message)

    if Config.get("Notify", "IfSendStatistic"):
        await _send_to_all_global_channels(title, message_text, message_html)

    if (
        user_config is not None
        and user_config.get("Notify", "Enabled")
        and user_config.get("Notify", "IfSendStatistic")
    ):
        await _send_to_user_channels(title, message_text, message_html, user_config)