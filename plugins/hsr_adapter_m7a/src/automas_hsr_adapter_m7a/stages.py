from __future__ import annotations

from typing import Any

from automas_script_hsr.contracts import HSRStageCategory
from automas_script_hsr.runtime.stage_contract import normalize_stage_categories
from automas_script_hsr.runtime.stage_provider import get_m7a_stage_options


def load_m7a_stage_options(script_config: Any) -> tuple[HSRStageCategory, ...]:
    return normalize_stage_categories(get_m7a_stage_options(script_config))
