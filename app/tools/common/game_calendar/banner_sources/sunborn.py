"""Official Girls' Frontline 2 website adapter."""

from __future__ import annotations

import re
from datetime import datetime

import httpx

from .base import (
    UTC8,
    BannerSourceError,
    BaseBannerSource,
    ObservationDraft,
    PoolSection,
    explicit_cancellation,
    explicit_pool_id,
    html_to_text,
    is_banner_text,
    stable_digest,
)

MAX_SUNBORN_ARTICLES = 12


def _source_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()).replace(tzinfo=UTC8)
    except ValueError:
        return None


def _gf2_sections(title: str, body_text: str) -> list[PoolSection]:
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    timing: list[str] = []
    for index, line in enumerate(lines):
        if line == "活动时间：":
            timing = lines[index : index + 2]
            break

    character_match = re.search(r"精英人形「([^」]+)」", body_text)
    weapon_match = re.search(r"精英武器「([^」]+)」", body_text)
    sections: list[PoolSection] = []
    if "定向采购" in body_text and character_match is not None:
        character = character_match.group(1).strip()
        sections.append(
            PoolSection(
                title=f"定向采购｜{character}",
                text="\n".join(
                    (
                        *timing,
                        f"精英人形「{character}」获取概率提升",
                        "版本更新后开放",
                    )
                ),
            )
        )
    if "军备提升" in body_text and weapon_match is not None:
        weapon = weapon_match.group(1).strip()
        sections.append(
            PoolSection(
                title=f"军备提升｜{weapon}",
                text="\n".join(
                    (
                        *timing,
                        f"精英武器「{weapon}」获取概率提升",
                        "版本更新后开放",
                    )
                ),
            )
        )
    return sections


class GirlsFrontline2Source(BaseBannerSource):
    game = "girlsfrontline2"
    source_key = "girlsfrontline2"
    authoritative_url = "https://gf2.sunborngame.com/NewsInfo?id=2225&typeId=4"
    base_url = "https://gf2-web-preregister-api.sunborngame.com"
    list_url = f"{base_url}/website/news_list/4?page=1&limit=50"
    detail_url = f"{base_url}/website/news/{{news_id}}"
    public_url = "https://gf2.sunborngame.com/NewsInfo?id={news_id}&typeId=4"

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        verified_at: str,
    ) -> list[ObservationDraft]:
        list_response = await self._request(client, self.list_url)
        payload = list_response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        entries = data.get("list") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise BannerSourceError("girlsfrontline2: news list is missing")

        drafts: list[ObservationDraft] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("Title") or "")
            if not (
                "概率UP" in title
                or "概率提升" in title
                or "定向采购" in title
                or "军备提升" in title
            ):
                continue
            news_id = str(entry.get("Id") or "").strip()
            if not news_id:
                raise BannerSourceError("girlsfrontline2: banner entry has no id")
            detail_response = await self._request(
                client,
                self.detail_url.format(news_id=news_id),
            )
            detail_payload = detail_response.json()
            detail = (
                detail_payload.get("data") if isinstance(detail_payload, dict) else None
            )
            if not isinstance(detail, dict):
                raise BannerSourceError(
                    f"girlsfrontline2: invalid detail for {news_id}"
                )
            detail_title = detail.get("Title") or title
            body_text = html_to_text(detail.get("Content"))
            if not is_banner_text(f"{detail_title}\n{body_text}"):
                continue
            published_at = _source_datetime(detail.get("Date") or entry.get("Date"))
            revision = stable_digest(
                news_id,
                detail_title,
                body_text,
                published_at.isoformat() if published_at is not None else None,
            )
            for section in _gf2_sections(detail_title, body_text):
                if not section.text:
                    continue
                combined = f"{section.title}\n{section.text}"
                drafts.append(
                    self._draft(
                        title=section.title,
                        body_text=section.text,
                        published_at=published_at,
                        official_url=self.public_url.format(news_id=news_id),
                        article_id=news_id,
                        official_id=explicit_pool_id(combined),
                        verified_at=verified_at,
                        revision=f"{revision}:{section.title}",
                        cancelled=explicit_cancellation(combined),
                        related=[f"{self.source_key}:article:{news_id}"],
                        confirmed_open_at_override=(
                            published_at if "现已开启" in str(detail_title) else None
                        ),
                    )
                )
            if len(drafts) >= MAX_SUNBORN_ARTICLES:
                break
        return drafts
