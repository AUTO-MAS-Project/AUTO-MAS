"""Official Wuthering Waves website adapter."""

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
    split_pool_sections,
    stable_digest,
)

MAX_KURO_ARTICLES = 12
_WUTHERING_POOL_LINE = re.compile(
    r"^\s*※?\s*可通过\s*[\[「]\s*(?P<subject>[^\]」]+)\s*[\]」]\s*"
    r"(?P<kind>角色|武器)(?:联动|活动)唤取获得[。.]?\s*$"
)


def _wuthering_sections(title: str, body_text: str) -> list[PoolSection]:
    if "版本内容说明" in title:
        sections: list[PoolSection] = []
        for line in body_text.splitlines():
            match = _WUTHERING_POOL_LINE.match(line)
            if match is None:
                continue
            subject = match.group("subject").strip()
            pool_kind = match.group("kind")
            sections.append(
                PoolSection(
                    title=f"{subject}｜{pool_kind}活动唤取",
                    text=f"版本更新维护后\n{line}",
                )
            )
        return sections
    return split_pool_sections(title, body_text)


def _source_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()).replace(tzinfo=UTC8)
    except ValueError:
        return None


class WutheringWavesSource(BaseBannerSource):
    game = "wutheringwaves"
    source_key = "wutheringwaves"
    authoritative_url = "https://mc.kurogames.com/main/news/detail/1659"
    menu_url = (
        "https://media-cdn-mingchao.kurogame.com/"
        "akiwebsite/website2.0/json/G152/zh/ArticleMenu.json"
    )
    detail_url = (
        "https://media-cdn-mingchao.kurogame.com/"
        "akiwebsite/website2.0/json/G152/zh/article/{article_id}.json"
    )
    public_url = "https://mc.kurogames.com/main/news/detail/{article_id}"

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        verified_at: str,
    ) -> list[ObservationDraft]:
        menu_response = await self._request(client, self.menu_url)
        menu = menu_response.json()
        if not isinstance(menu, list):
            raise BannerSourceError("wutheringwaves: article menu is invalid")

        candidates = [
            item
            for item in menu
            if isinstance(item, dict)
            and (
                "版本内容说明" in str(item.get("articleTitle") or "")
                or (
                    "概率UP" in str(item.get("articleTitle") or "")
                    and any(
                        term in str(item.get("articleTitle") or "")
                        for term in ("角色活动唤取", "武器活动唤取")
                    )
                )
            )
        ]
        drafts: list[ObservationDraft] = []
        for item in candidates[:MAX_KURO_ARTICLES]:
            article_id = str(item.get("articleId") or "").strip()
            if not article_id:
                raise BannerSourceError(
                    "wutheringwaves: banner article has no articleId"
                )
            detail_response = await self._request(
                client,
                self.detail_url.format(article_id=article_id),
            )
            detail = detail_response.json()
            if not isinstance(detail, dict):
                raise BannerSourceError(
                    f"wutheringwaves: invalid banner article {article_id}"
                )
            title = str(detail.get("articleTitle") or item.get("articleTitle") or "")
            body_text = html_to_text(detail.get("articleContent"))
            published_at = _source_datetime(
                detail.get("startTime") or item.get("startTime")
            )
            revision = stable_digest(
                article_id,
                title,
                body_text,
                published_at.isoformat() if published_at is not None else None,
            )
            for section in _wuthering_sections(title, body_text):
                if not section.text:
                    continue
                combined = f"{section.title}\n{section.text}"
                drafts.append(
                    self._draft(
                        title=section.title,
                        body_text=section.text,
                        published_at=published_at,
                        official_url=self.public_url.format(article_id=article_id),
                        article_id=article_id,
                        official_id=explicit_pool_id(combined),
                        verified_at=verified_at,
                        revision=f"{revision}:{section.title}",
                        cancelled=explicit_cancellation(combined),
                        related=[f"{self.source_key}:article:{article_id}"],
                    )
                )
        return drafts
