from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def proxy_date_tag(
    last_date: str, proxy_times: int, tz: Any, label: str = "日常"
) -> dict[str, str]:
    if (
        datetime.strptime(last_date, "%Y-%m-%d").date()
        == datetime.now(tz=tz).date()
    ):
        return {"text": f"{label}：已代理{proxy_times}次", "color": "green"}
    return {"text": f"{label}：未代理", "color": "orange"}


def remained_day_tag(remained_day: int) -> dict[str, str]:
    if remained_day == -1:
        color = "gold"
    elif remained_day == 0:
        color = "red"
    elif remained_day <= 3:
        color = "orange"
    elif remained_day <= 7:
        color = "yellow"
    elif remained_day <= 30:
        color = "blue"
    else:
        color = "green"
    text = f"剩余天数：{remained_day}天" if remained_day >= 0 else "剩余天数：无期限"
    return {"text": text, "color": color}


def notes_tag(notes: str) -> dict[str, str]:
    text = f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}..."
    return {"text": text, "color": "pink"}
