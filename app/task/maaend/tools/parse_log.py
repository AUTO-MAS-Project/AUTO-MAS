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
import json


def parse_log(lines: list[str]) -> list[str]:
    """
    从原始日志行中提取 MXU 日志框文本。

    解析规则：
        - 仅解析 !!!OnEventNotify!!! 行
        - 支持内容来源：
            1. focus 字典中与消息类型匹配的内容（Pipeline focus 日志）
            2. 特殊消息类型的构造文本（Task、Resource 等）
        - 去除完全重复的行

    Args:
        lines(list[str]): 原始日志行列表

    Returns:
        list[str]: 解析后的可打印日志行列表
    """

    output: list[str] = []
    seen: set[str] = set()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # 固定只处理 OnEventNotify 事件行
        if "!!!OnEventNotify!!!" not in line:
            continue

        # 提取时间戳
        ts_match = re.compile(r"^\[([^\]]+)\]").match(line)
        timestamp = ts_match.group(1) if ts_match else ""

        # 提取 msg
        msg_marker = "[msg="
        msg_pos = line.find(msg_marker)
        if msg_pos < 0:
            continue
        msg_start = msg_pos + len(msg_marker)
        msg_end = line.find("]", msg_start)
        if msg_end < 0:
            continue
        message = line[msg_start:msg_end]
        if not message:
            continue

        # 提取 details JSON（支持字符串内转义）
        details_marker = "[details="
        details_pos = line.find(details_marker)
        if details_pos < 0:
            continue
        json_start = line.find("{", details_pos)
        if json_start < 0:
            continue

        brace = 0
        in_str = False
        escaped = False
        json_end = -1
        for i in range(json_start, len(line)):
            ch = line[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                brace += 1
                continue
            if ch == "}":
                brace -= 1
                if brace == 0:
                    json_end = i
                    break

        if json_end < 0:
            continue

        try:
            details = json.loads(line[json_start : json_end + 1])
        except Exception:
            continue
        if not isinstance(details, dict):
            continue

        # 尝试从 focus 字段提取内容
        focus = details.get("focus")
        content = None

        if focus is not None:
            if isinstance(focus, dict):
                # focus 是字典：查找与当前消息类型匹配的键
                if message in focus:
                    content = focus.get(message)
            elif isinstance(focus, str):
                # focus 是字符串：直接使用
                content = focus

        # 如果从 focus 中没有找到内容，尝试处理特殊消息类型
        if not content:
            if message == "Tasker.Task.Starting":
                entry = details.get("entry")
                task_id = details.get("task_id")
                if entry and task_id:
                    content = f"任务开始: {task_id} - {entry}"
            elif message == "Tasker.Task.Succeeded":
                entry = details.get("entry")
                task_id = details.get("task_id")
                if entry and task_id:
                    content = f"任务完成: {task_id} - {entry}"
            elif message == "Tasker.Task.Failed":
                entry = details.get("entry")
                task_id = details.get("task_id")
                if entry and task_id:
                    content = f"任务失败: {task_id} - {entry}"
            elif message == "Resource.Loading.Starting":
                res_type = details.get("type", "")
                path = details.get("path", "")
                if res_type == "Bundle" and path:
                    path_name = path.split("/")[-1] if "/" in path else path
                    content = f"正在加载资源: {path_name}"
            elif message == "Resource.Loading.Succeeded":
                res_type = details.get("type", "")
                path = details.get("path", "")
                if res_type == "Bundle" and path:
                    path_name = path.split("/")[-1] if "/" in path else path
                    content = f"资源加载成功: {path_name}"
            elif message == "Resource.Loading.Failed":
                res_type = details.get("type", "")
                path = details.get("path", "")
                if res_type == "Bundle" and path:
                    path_name = path.split("/")[-1] if "/" in path else path
                    content = f"资源加载失败: {path_name}"

        # 确保 content 是字符串
        if not isinstance(content, str) or not content:
            continue

        # 构建输出行
        output_line = content
        if timestamp:
            output_line = f"[{timestamp}] {content}"

        # 去重：只输出未见过的行
        if output_line not in seen:
            seen.add(output_line)
            output.append(output_line + "\n")

    return output
