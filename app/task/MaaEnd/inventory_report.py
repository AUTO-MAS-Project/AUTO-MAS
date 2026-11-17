"""从 MXU 用户可见日志采集任务奖励和协议空间材料状态。

采集保留上游每一轮的原始记录；展示前由 ``merge_gain_entries`` 把同一材料
各轮数量相加成一行合计，不据此判断库存目标是否达成。
"""

import re
from collections.abc import Iterable, Mapping
from html import unescape
from pathlib import Path

from app.task.MaaEnd.push_log import _parse_line_ts, maaend_plain_text
from app.utils import LOG_TYPE_NORMAL, get_logger
from app.utils.common.io import ConfigCorruptedError, read_dict_file
from app.utils.common.log_box.results import LogEntry

logger = get_logger("MaaEnd 奖励统计")

INVENTORY_REPORT_RULE = (r"^(?:本次获得|上游报告)：", "")
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

# 展示合并：「本次获得：材料 ×N」按材料名累加；数量允许千分位逗号，
# 写法认不出（如夹带说明文字）的整行保持原样，不静默丢内容
_GAIN_PREFIX = "本次获得："
_GAIN_SEPARATORS_RE = re.compile(r"[、，；;]|,(?![0-9]{3}(?:[,\s]|$))")
_GAIN_ITEM_RE = re.compile(r"(?P<name>[^、，,；;×]+?)\s*×\s*(?P<count>\d+(?:,\d{3})*)")
_TASK_LINE_RE = re.compile(r"^\[([^\]]+)\]\s*(.+)$")
_CONSUMABLES = "🧪 消耗品"
_OTHER_REWARDS = "📦 其他"
_REWARD_GROUPS = {
    "🧬 培养材料": ("Nurturance", "SpecialItem"),
    _CONSUMABLES: ("Usable",),
    "✨ 经验": ("AdventureExp", "BPExp"),
    "💰 货币": (
        "Diamond",
        "DomainGold",
        "Gold",
        "Originium",
        "SpaceshipGold",
        "WeaponGold",
    ),
    "🌿 采集材料": ("Doodad", "Ore", "Plant"),
    "🏭 工业物资": ("Producer", "Product"),
    "⚔️ 装备": ("PortableDevice", "Weapon"),
    "🎫 贵重物品": ("CommercialItem",),
    _OTHER_REWARDS: (),
}
_GROUP_BY_CATEGORY_TYPE = {
    kind: group for group, kinds in _REWARD_GROUPS.items() for kind in kinds
}


def load_reward_groups(
    root: Path | None, item_labels: Mapping[str, str]
) -> dict[str, str]:
    """用上游公开物品目录和本轮词表将日志中的物品名映射到报告分组。"""

    if root is None:
        return {}
    try:
        catalog = read_dict_file(root / "data/IconRecognition/recognition_items.json")
    except (ConfigCorruptedError, OSError) as error:
        logger.warning(f"读取 MaaEnd 物品目录失败，奖励仍会计入其他：{error}")
        return {}

    names: dict[str, set[str]] = {}
    for item_id, metadata in catalog.items():
        if not isinstance(metadata, dict):
            continue
        category = metadata.get("categoryType")
        if item_id == "item_bp_double_reward" or item_id.startswith(
            ("ap_supply_", "item_ap_supply_")
        ):
            group = _CONSUMABLES
        elif isinstance(category, str):
            group = _GROUP_BY_CATEGORY_TYPE.get(category, _OTHER_REWARDS)
        else:
            group = _OTHER_REWARDS
        for name in (metadata.get("name"), item_labels.get(item_id)):
            if isinstance(name, str) and name:
                names.setdefault(name, set()).add(group)
    return {
        name: next(iter(groups)) for name, groups in names.items() if len(groups) == 1
    }


class TaskRewardReport:
    """按奖励种类汇总各阶段已获得的物品。"""

    def __init__(self, groups: Mapping[str, str]) -> None:
        self.groups = groups
        self.rewards: dict[str, tuple[float | None, dict[str, int]]] = {}

    def add_stage(self, lines: Iterable[str]) -> None:
        """消费单次进程日志，每个阶段重新识别任务和奖励区块。"""

        in_task = False
        in_rewards = False
        for line in lines:
            match = _TASK_LINE_RE.match(maaend_plain_text(line).strip())
            if match is None:
                in_rewards = False
                continue
            timestamp, text = match.groups()
            if text.startswith("任务开始:"):
                in_task = True
                in_rewards = False
            elif text.startswith(("任务完成:", "任务失败:")):
                in_task = False
                in_rewards = False
            elif in_task:
                heading = next(
                    (title for title in _GAIN_TITLES if text.startswith(title)), ""
                )
                if heading:
                    in_rewards = True
                    text = text.removeprefix(heading).strip()
                    if not text:
                        continue
                if not in_rewards:
                    continue
                items = _gain_items(text)
                if not items:
                    in_rewards = False
                    continue
                for item, count in items:
                    group = self.groups.get(item, _OTHER_REWARDS)
                    if group not in self.rewards:
                        self.rewards[group] = (_parse_line_ts(timestamp, None), {})
                    _, totals = self.rewards[group]
                    totals[item] = totals.get(item, 0) + count

    def entries(self) -> list[LogEntry]:
        entries = []
        for group in _REWARD_GROUPS:
            if group not in self.rewards:
                continue
            timestamp, totals = self.rewards[group]
            items = "、".join(f"{item} ×{count}" for item, count in totals.items())
            entries.append(
                LogEntry(
                    log_type=LOG_TYPE_NORMAL,
                    text=f"{group}：{items}",
                    timestamp=timestamp,
                )
            )
        return entries


class InventoryReport:
    """仅收集协议空间范围内的获得和上游状态，忽略全量库存。"""

    def __init__(
        self, task_names: set[str], status_messages: set[str] | None = None
    ) -> None:
        self.task_names = task_names
        self.status_messages = status_messages or set()
        self.in_protocol_space = False
        self.section = ""

    def select(self, line: str) -> str | None:
        """供 log_box 前置过滤使用；只把奖励记录作为材料增量。"""

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
            self.section = ""
            return None
        elif gain_title:
            self.section = "本次获得"
            text = text.split(gain_title, 1)[1].strip()
        elif text in self.status_messages or re.search(
            r"(?:目标.*(?:不足|满足|达标|切换)|理智.*不足|扫描.*失败)",
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
    results: list[tuple[str, str, float | None]],
) -> list[tuple[str, str, float | None]]:
    """还原本轮报告时间；逐轮记录保持原样，合计在展示前由 ``merge_gain_entries`` 完成。"""

    resolved = []
    for log_type, text, ts in results:
        report, _, timestamp = text.partition("\n")
        resolved.append((log_type, report, _parse_line_ts(timestamp, ts)))
    return resolved


def _gain_items(text: str) -> list[tuple[str, int]] | None:
    """拆出一行里的「材料 ×数量」；有空段或写法不认识时返回 None，该行不合并。"""

    parts = _GAIN_SEPARATORS_RE.split(text.removeprefix(_GAIN_PREFIX))
    items: list[tuple[str, int]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = _GAIN_ITEM_RE.fullmatch(part)
        if match is None:
            return None
        items.append((match.group("name"), int(match.group("count").replace(",", ""))))
    return items or None


def merge_gain_entries(entries: Iterable[LogEntry]) -> list[LogEntry]:
    """把逐轮「本次获得」合并成每种材料一行合计，上游报告保持原样。

    Args:
        entries: 已采集并按时间排好的展示条目。

    Returns:
        合并后的条目：同一材料各轮数量相加，括号里带获得次数；行位置与时间
        取该材料首次出现的那条，材料顺序沿用上游行内顺序。合计只做展示，
        不据此判断库存目标是否达成。
    """

    totals: dict[str, list[int]] = {}
    # 每个合计行占位时的上下文：{占位序号: (日志类型, 时间戳, 本行首次出现的材料)}
    pending: dict[int, tuple[str, float | None, list[str]]] = {}
    slots: list[LogEntry | None] = []
    for entry in entries:
        items = _gain_items(entry.text) if entry.text.startswith(_GAIN_PREFIX) else None
        if items is None:
            slots.append(entry)
            continue
        firsts: list[str] = []
        for name, count in items:
            if name not in totals:
                totals[name] = [0, 0]
                firsts.append(name)
            totals[name][0] += count
            totals[name][1] += 1
        if not firsts:
            # 材料都在更早的行里出现过，本轮不再单独占一行
            continue
        pending[len(slots)] = (entry.log_type, entry.timestamp, firsts)
        slots.append(None)

    merged: list[LogEntry] = []
    for index, slot in enumerate(slots):
        if slot is not None:
            merged.append(slot)
            continue
        log_type, timestamp, names = pending[index]
        merged.extend(
            LogEntry(
                log_type=log_type,
                text=f"{_GAIN_PREFIX}{name} ×{totals[name][0]}（{totals[name][1]} 次）",
                timestamp=timestamp,
            )
            for name in names
        )
    return merged
