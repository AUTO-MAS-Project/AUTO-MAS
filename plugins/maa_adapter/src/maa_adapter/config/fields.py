from __future__ import annotations

from typing import Annotated

from auto_mas_core.host.config import (
    select,
)
from pydantic import Field

StageCode = Annotated[str, select(endpoint="/api/plugin/maa_adapter/stages/options")]


DepotQuotaNumb = Annotated[int | None, Field(ge=0, le=9999)]
