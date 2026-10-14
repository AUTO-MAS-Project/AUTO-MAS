"""明日方舟工具箱「导出 MAA」的公开剪贴板格式，转换为现有养成目标。

格式来源：arkntools/arknights-toolbox 的 src/views/Material/index.js，
exportToMAA；不读取 MAA 原生配置。技能序号取自现有完整干员目录。
"""

import json
from typing import Any, Literal, Sequence

from .types import Goal, OperatorTarget

ImportErrorKind = Literal[
    "format",
    "empty",
    "operator",
    "ambiguous",
    "elite",
    "skill",
    "mastery",
    "unsupported",
]


class CultivateImportError(ValueError):
    """无法导入的条目与原因，供前端本地化。"""

    def __init__(
        self, reason: ImportErrorKind, *, index: int | None = None, name: str = ""
    ) -> None:
        self.reason = reason
        self.index = index
        self.name = name
        super().__init__(f"{reason}: item={index}, name={name}")


def parse_clipboard_targets(
    content: str, catalog: Sequence[dict[str, Any]]
) -> tuple[tuple[OperatorTarget, ...], tuple[CultivateImportError, ...]]:
    """转换有效干员并返回跳过的条目；专精补齐技能 7 级，不修改目录。"""

    try:
        payload = json.loads(content.strip().lstrip("\ufeff"))
    except ValueError as exc:
        raise CultivateImportError("format") from exc
    if not isinstance(payload, list):
        raise CultivateImportError("format")
    if not payload:
        raise CultivateImportError("empty")

    targets: list[OperatorTarget] = []
    skipped: list[CultivateImportError] = []
    for index, item in enumerate(payload, start=1):
        try:
            target = _parse_clipboard_target(item, index=index, catalog=catalog)
        except CultivateImportError as exc:
            skipped.append(exc)
            continue
        if target is not None:
            targets.append(target)
    if not targets and not skipped:
        raise CultivateImportError("empty")
    return tuple(targets), tuple(skipped)


def _parse_clipboard_target(
    item: Any, *, index: int, catalog: Sequence[dict[str, Any]]
) -> OperatorTarget | None:
    """完整校验单个干员，避免保留该条目中部分有效的目标。"""

    if not isinstance(item, dict):
        raise CultivateImportError("format", index=index)
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CultivateImportError("operator", index=index)
    name = name.strip()
    if item.keys() - {"role", "name", "elite", "skill_level", "skill_mastery"}:
        raise CultivateImportError("unsupported", index=index, name=name)
    role = item.get("role", "Unknown")
    matches = [
        entry
        for entry in catalog
        if entry["label"] == name
        and (role == "Unknown" or str(entry["profession"]).title() == role)
    ]
    if len(matches) != 1:
        raise CultivateImportError(
            "ambiguous" if matches else "operator", index=index, name=name
        )
    operator = matches[0]
    goals: list[Goal] = []
    level_fields: tuple[tuple[str, Literal["elite", "skill"], int], ...] = (
        ("elite", "elite", operator["maxElite"]),
        ("skill_level", "skill", operator["maxSkillLevel"]),
    )
    for field, kind, maximum in level_fields:
        level = item.get(field, 0)
        if type(level) is not int or not 0 <= level <= maximum:
            raise CultivateImportError(kind, index=index, name=name)
        # 0 表示未设置；技能 1 级没有升级需求，不创建目标。
        if level > (1 if kind == "skill" else 0):
            goals.append(Goal(kind=kind, target_id="", to_level=level))

    masteries = item.get("skill_mastery", [])
    if not isinstance(masteries, list) or len(masteries) > 3:
        raise CultivateImportError("mastery", index=index, name=name)
    skills_by_index = {skill["skillIndex"]: skill for skill in operator["skills"]}
    for skill_index, level in enumerate(masteries, start=1):
        if type(level) is not int or not 0 <= level <= 3:
            raise CultivateImportError("mastery", index=index, name=name)
        if not level:
            continue
        skill = skills_by_index.get(skill_index)
        if skill is None or level > skill["maxLevel"]:
            raise CultivateImportError("mastery", index=index, name=name)
        goals.append(Goal(kind="mastery", target_id=skill["value"], to_level=level))
    if any(goal.kind == "mastery" for goal in goals):
        if operator["maxSkillLevel"] < 7:
            raise CultivateImportError("skill", index=index, name=name)
        goals = [goal for goal in goals if goal.kind != "skill"]
        goals.insert(0, Goal(kind="skill", target_id="", to_level=7))
    return OperatorTarget(operator["value"], tuple(goals)) if goals else None
