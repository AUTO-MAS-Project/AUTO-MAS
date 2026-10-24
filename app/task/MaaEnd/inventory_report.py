"""从 MXU 用户可见日志采集协议空间材料报告，不读取 IMS 缓存。"""

import re
from html import unescape

from app.task.MaaEnd.push_log import _parse_line_ts

INVENTORY_REPORT_RULE = (r"^(?:扫描库存|本次获得|上游报告)：", "")
_SCAN_TITLES = (
    "识别到以下物品：",
    "識別到以下物品：",
    "Found items:",
    "認識したアイテム：",
    "인식한 아이템:",
)
_GAIN_TITLES = (
    "获得以下物品：",
    "獲得以下物品：",
    "Gained items:",
    "獲得したアイテム：",
    "획득한 아이템:",
)


class InventoryReport:
    """仅收集协议空间范围内的扫描、获得和上游状态原文。"""

    def __init__(
        self, task_names: set[str], status_messages: set[str] | None = None
    ) -> None:
        self.task_names = task_names
        self.status_messages = status_messages or set()
        self.in_protocol_space = False
        self.section = ""

    def select(self, line: str) -> str | None:
        """供 log_box 前置过滤使用；保留扫描与获得的不同含义。"""

        text = unescape(re.sub(r"<[^>]*>", "", line))
        text = re.sub(r"^\[[^\]]+\]\s*", "", text).strip()
        start = re.match(r"任务开始:\s*(.+)", text)
        if start:
            self.in_protocol_space = start.group(1) in self.task_names
            self.section = ""
            return None
        if not self.in_protocol_space:
            return None
        if re.match(r"任务(?:完成|失败):", text):
            self.in_protocol_space = False
            self.section = ""
            return None
        scan_title = next((title for title in _SCAN_TITLES if title in text), "")
        gain_title = next((title for title in _GAIN_TITLES if title in text), "")
        if scan_title:
            self.section = "扫描库存"
            text = text.split(scan_title, 1)[1].strip()
        elif gain_title:
            self.section = "本次获得"
            text = text.split(gain_title, 1)[1].strip()
        elif text in self.status_messages or re.search(
            r"(?:(?:当前 |目前 |Current |現在 |현재 ).+[:：]\s*\d+|目标.*(?:不足|满足|达标|切换)|理智.*不足|扫描.*失败)",
            text,
        ):
            self.section = ""
            stamp = re.match(r"^\[([^\]]+)\]", line)
            timestamp = stamp.group(1) if stamp else ""
            return f"上游报告：{text}\n{timestamp}"
        elif not re.search(r"×\s*\d+", text):
            self.section = ""
            return None
        if self.section and text:
            stamp = re.match(r"^\[([^\]]+)\]", line)
            timestamp = stamp.group(1) if stamp else ""
            return f"{self.section}：{text}\n{timestamp}"
        return None


def inventory_resolve(
    results: list[tuple[str, str, float]],
) -> list[tuple[str, str, float]]:
    """还原本轮报告时间，不合并掉落数量或自行判断达标。"""

    resolved = []
    for log_type, text, ts in results:
        report, _, timestamp = text.partition("\n")
        resolved.append((log_type, report, _parse_line_ts(timestamp, ts)))
    return resolved
