"""OK-WW 半动态表单：原生 JSON 提供字段，有限元数据补充选项和联动。

运行中 Web API 可提供完整描述；离线配置不包含选项，需维护这部分元数据。
不导入或执行用户安装目录中的 Python 任务源码。
"""

from copy import deepcopy
from typing import Literal

ECHO_DEFAULTS = {
    "Teleport to Boss": "No",
    "Boss Level": "80",
    "Boss": "Other",
    "Repeat Farm Count": 10000,
    "Combat Wait Time": 0,
    "Echo Pickup Method": "Walk",
    "Use Liberation": True,
    "Switch to Healer before and after Combat": True,
    "Which Weekly Boss to Teleport": 1,
    "Which Boss Challenge to Teleport": 1,
    "Which Special Nightmare to Teleport": 1,
    "Exit After Task": False,
}
PanelKind = Literal["daily", "echo", "nightmare", "combat", "character", "monthly"]
PANEL_FILES = {
    "daily": "DailyTask.json",
    "echo": "FarmEchoTask.json",
    "nightmare": "NightmareNestTask.json",
    "combat": "AutoCombatTask.json",
    "character": "Character Config.json",
    "monthly": "Monthly Card Config.json",
}
PANEL_DEFAULTS = {
    "daily": {
        "Which to Farm": "Tacet Suppression",
        "Which Tacet Suppression to Farm": 1,
        "Which Forgery Challenge to Farm": 1,
        "Material Selection": "Shell Credit",
        "Farm Nightmare Nest for Daily Echo": True,
        "Additional Tasks to Run After Daily Task": ["Check Weekly Garden"],
        "Exit After Task": False,
    },
    "echo": ECHO_DEFAULTS,
    "nightmare": {"Which to Farm": ["Nightmare Purification", "Tacet Discord Nest"]},
    "combat": {
        "Auto Target": True,
        "Use Liberation": True,
        "Check Levitator": True,
        "Switch to Healer before and after Combat": True,
    },
    "character": {
        "Iuno C6": False,
        "Roccia C6": False,
        "Chisa DPS": False,
        "Suoming DPS": False,
    },
    "monthly": {"Check Monthly Card": True, "Monthly Card Time": 4},
}


def panel_values(user, kind: str) -> dict:
    """面板数据保持原生键名，已有日常与4C字段继续兼容。"""
    if kind == "daily":
        return dict(user.Task.DailyConfig)
    if kind == "echo":
        return dict(user.Task.FarmEchoConfig)
    return dict(user.Task.NativeConfigs.get(PANEL_FILES[kind], {}))


def runtime_panels(user) -> dict[str, dict]:
    """输出本次实际下发的面板，快速配置总开关关闭时仅计划生效。"""
    from .plan import task_config

    result = {}
    if user.Info.IfQuickConfig:
        result = {
            filename: panel_values(user, kind) for kind, filename in PANEL_FILES.items()
        }
    daily = result.setdefault(PANEL_FILES["daily"], {})
    daily.update(task_config(user))
    return {filename: values for filename, values in result.items() if values}


OPTIONS = {
    "Teleport to Boss": [
        "No",
        "Weekly Challenge",
        "Boss Challenge",
        "Special Nightmare",
    ],
    "Boss Level": ["50", "60", "70", "80", "90"],
    "Boss": [
        "Other",
        "Hyvatia",
        "Fallacy of No Return",
        "Sentry Construct",
        "Lorelei",
        "Lioness of Glory",
        "Nightmare: Hecate",
        "Fenrico",
        "Nameless Explorer",
    ],
    "Echo Pickup Method": ["Yolo", "Run in Circle", "Walk"],
    "Which to Farm": ["Tacet Suppression", "Forgery Challenge", "Simulation Challenge"],
    "Material Selection": ["Resonator EXP", "Weapon EXP", "Shell Credit"],
    "Additional Tasks to Run After Daily Task": [
        "Check Weekly Garden",
        "Auto Farm all Nightmare Nest",
        "Merge Echo If discarded > 1000",
        "Teleport and Farm 4C Echo",
    ],
}
CONDITIONS = {
    "Which Weekly Boss to Teleport": ("Teleport to Boss", ["Weekly Challenge"]),
    "Which Boss Challenge to Teleport": ("Teleport to Boss", ["Boss Challenge"]),
    "Which Special Nightmare to Teleport": ("Teleport to Boss", ["Special Nightmare"]),
    "Boss Level": (
        "Teleport to Boss",
        ["Weekly Challenge", "Boss Challenge", "Special Nightmare"],
    ),
    "Which Tacet Suppression to Farm": ("Which to Farm", ["Tacet Suppression"]),
    "Which Forgery Challenge to Farm": ("Which to Farm", ["Forgery Challenge"]),
    "Material Selection": ("Which to Farm", ["Simulation Challenge"]),
}


def describe_fields(values: dict, panel: str = "echo") -> list[dict]:
    """未知字段按 JSON 值生成控件；保留未知选项，内部字段不暴露。"""
    fields = []
    for name, value in values.items():
        if name.startswith("_"):
            continue
        options = (
            list(PANEL_DEFAULTS["nightmare"]["Which to Farm"])
            if panel == "nightmare" and name == "Which to Farm"
            else list(OPTIONS.get(name, []))
        )
        if options and (
            isinstance(value, str)
            or isinstance(value, list)
            and all(isinstance(item, str) for item in value)
        ):
            existing = value if isinstance(value, list) else [value]
            options.extend(item for item in existing if item not in options)
            kind = "multi_selection" if isinstance(value, list) else "select"
        elif isinstance(value, bool):
            kind = "bool"
        elif isinstance(value, (int, float)):
            kind = "number"
        elif isinstance(value, str):
            kind = "string"
        else:
            kind = "json"
        parent, choices = CONDITIONS.get(name, (None, []))
        fields.append(
            {
                "name": name,
                "integer": isinstance(value, int) and not isinstance(value, bool),
                "minimum": 0
                if panel == "monthly" and name == "Monthly Card Time"
                else None,
                "maximum": 23
                if panel == "monthly" and name == "Monthly Card Time"
                else None,
                "type": kind,
                "options": options,
                "parent": parent,
                "choices": choices,
            }
        )
    return fields


def echo_defaults() -> dict:
    return deepcopy(ECHO_DEFAULTS)


def load_labels(root_path, locale: str) -> dict[str, str]:
    """读取脚本与框架 UI 词表；不执行上游代码，缺失时使用后备文案。"""
    from pathlib import Path
    from xml.etree import ElementTree

    from app.utils import get_logger, i18n

    if root_path is None or locale == "en_US":
        return {}
    logger = get_logger("OK-WW 配置词表")
    root = Path(root_path)
    resources = [
        directory
        for base in (
            root / "data/apps/ok-ww/working",
            root / "data/apps/ok-ww/repo",
            root,
        )
        for directory in (base, base / "_internal")
    ]
    labels = {}
    for base in resources:
        directory = base / "i18n" / locale / "LC_MESSAGES"
        for extension, parser in ((".mo", i18n.parse_mo), (".po", i18n.parse_po)):
            path = directory / ("ok" + extension)
            if path.is_file():
                try:
                    labels = parser(path)
                except (OSError, UnicodeError, ValueError) as error:
                    logger.warning(f"读取词表失败: {path}: {error}")
                if labels:
                    break
        if labels:
            break
    for base in resources:
        for relative in ("ok/ui/qt/i18n", "ok/gui/i18n"):
            path = base / relative / (locale + ".ts")
            if not path.is_file():
                continue
            try:
                for message in ElementTree.parse(path).iter("message"):
                    source, translated = (
                        message.findtext("source"),
                        message.find("translation"),
                    )
                    if (
                        source
                        and translated is not None
                        and translated.text
                        and translated.get("type") != "unfinished"
                    ):
                        labels.setdefault(source, translated.text)
                return labels
            except (OSError, ElementTree.ParseError) as error:
                logger.warning(f"读取框架词表失败: {path}: {error}")
    return labels
