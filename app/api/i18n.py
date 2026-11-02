"""初始化完成后的界面语言资源。"""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, JsonValue

from app.core import I18n
from app.core.i18n import AppLocale
from app.models.schema import OutBase
from app.utils import get_logger

logger = get_logger("国际化接口")
router = APIRouter(prefix="/api/i18n", tags=["国际化"])


class I18nLocalesData(BaseModel):
    available: list[AppLocale] = Field(default_factory=list)
    revision: str = ""


class I18nLocalesOut(OutBase):
    data: I18nLocalesData


class I18nMessagesData(BaseModel):
    locale: AppLocale
    revision: str
    messages: dict[str, JsonValue]


class I18nMessagesOut(OutBase):
    data: I18nMessagesData


@router.get("/locales", response_model=I18nLocalesOut)
async def get_locales() -> I18nLocalesOut:
    """列出可用语言及当前资源版本。"""
    try:
        available, revision = await I18n.get_locales()
        return I18nLocalesOut(
            data=I18nLocalesData(available=available, revision=revision)
        )
    except (OSError, ValueError):
        logger.exception("语言资源目录读取失败")
        return I18nLocalesOut(
            code=500,
            status="error",
            message="语言资源读取失败，请重试",
            data=I18nLocalesData(),
        )


@router.get("/messages", response_model=I18nMessagesOut)
async def get_messages(locale: AppLocale = Query(...)) -> I18nMessagesOut:
    """读取指定语言的原始词表；回退和字符串插值由前端处理。"""
    try:
        messages, revision = await I18n.get_messages(locale)
        return I18nMessagesOut(
            data=I18nMessagesData(locale=locale, revision=revision, messages=messages)
        )
    except (OSError, ValueError):
        logger.exception("语言词表读取失败")
        return I18nMessagesOut(
            code=500,
            status="error",
            message="语言资源读取失败，请重试",
            data=I18nMessagesData(locale=locale, revision="", messages={}),
        )
