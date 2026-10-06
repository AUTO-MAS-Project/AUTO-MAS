"""全局 i18n 资源 API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.i18n import i18n
from app.api import OutBase

router = APIRouter(prefix="/api/i18n", tags=["国际化"])


class I18nMessagesData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    locale: str
    fallback_locale: str = Field(alias="fallbackLocale")
    revision: str
    messages: dict[str, Any]


class I18nMessagesOut(OutBase):
    data: I18nMessagesData


class I18nLocalesData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current: str
    fallback: str
    available: list[str]
    revision: str


class I18nLocalesOut(OutBase):
    data: I18nLocalesData


class I18nLocaleIn(BaseModel):
    locale: str


@router.get("/messages", response_model=I18nMessagesOut)
async def get_messages(
    locale: str | None = Query(default=None),
) -> I18nMessagesOut:
    """返回可直接交给 Vue I18n 的 messages。"""
    try:
        messages = await i18n.get_messages(locale)
        state = await i18n.get_locales()
        selected = locale or state["current"]
        return I18nMessagesOut(
            data=I18nMessagesData(
                locale=selected,
                fallbackLocale=state["fallback"],
                revision=state["revision"],
                messages=messages,
            )
        )
    except Exception as exc:
        return I18nMessagesOut(
            code=500,
            status="error",
            message=f"{type(exc).__name__}: {exc}",
            data=I18nMessagesData(
                locale=locale or "",
                fallbackLocale=i18n.FALLBACK_LOCALE,
                revision="0",
                messages={},
            ),
        )


@router.get("/locales", response_model=I18nLocalesOut)
async def get_locales() -> I18nLocalesOut:
    """返回当前语言、回退语言和可用语言。"""
    try:
        return I18nLocalesOut(data=I18nLocalesData(**(await i18n.get_locales())))
    except Exception as exc:
        return I18nLocalesOut(
            code=500,
            status="error",
            message=f"{type(exc).__name__}: {exc}",
            data=I18nLocalesData(
                current="",
                fallback=i18n.FALLBACK_LOCALE,
                available=["en"],
                revision="0",
            ),
        )


@router.put("/locale", response_model=I18nLocalesOut)
async def set_locale(body: I18nLocaleIn) -> I18nLocalesOut:
    """设置后端当前 locale 并广播资源变更。"""
    try:
        return I18nLocalesOut(data=I18nLocalesData(**(await i18n.set_locale(body.locale))))
    except ValueError as exc:
        return I18nLocalesOut(
            code=400,
            status="error",
            message=str(exc),
            data=I18nLocalesData(
                current="",
                fallback=i18n.FALLBACK_LOCALE,
                available=[],
                revision="0",
            ),
        )
    except Exception as exc:
        return I18nLocalesOut(
            code=500,
            status="error",
            message=f"{type(exc).__name__}: {exc}",
            data=I18nLocalesData(
                current="",
                fallback="en",
                available=[],
                revision="0",
            ),
        )
