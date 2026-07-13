from __future__ import annotations

from typing import Any

from automas_script_hsr.contracts import HSRStageCategory, HSRStageOption


def normalize_stage_categories(payload: dict[str, Any]) -> tuple[HSRStageCategory, ...]:
    """Convert the legacy rich-editor stage payload to the public HSR contract."""

    categories: list[HSRStageCategory] = []
    for raw_category in payload.get("categories", []):
        if not isinstance(raw_category, dict):
            continue
        options: list[HSRStageOption] = []
        for raw_option in raw_category.get("options", []):
            if not isinstance(raw_option, dict):
                continue
            native_payload = {
                key: value
                for key, value in raw_option.items()
                if key in {"m7a", "sra"} and isinstance(value, dict)
            }
            options.append(
                HSRStageOption(
                    id=str(raw_option.get("value") or ""),
                    label=str(raw_option.get("label") or ""),
                    detail=str(raw_option.get("detail") or ""),
                    cost=_optional_int(raw_option.get("cost")),
                    max_count=_optional_int(raw_option.get("maxCount")),
                    native_payload=native_payload,
                )
            )
        categories.append(
            HSRStageCategory(
                key=str(raw_category.get("categoryKey") or ""),
                label=str(raw_category.get("categoryLabel") or ""),
                options=tuple(options),
            )
        )
    return tuple(categories)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
