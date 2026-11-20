"""Official Princess Connect Sina/Weibo profile adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape

import httpx

from .base import (
    UTC8,
    BannerSourceError,
    BaseBannerSource,
    ObservationDraft,
    explicit_cancellation,
    explicit_pool_id,
    stable_digest,
)

PRINCESS_CONNECT_SINA_ID = "6603867494"
PRINCESS_CONNECT_OFFICIAL_NAME = "公主连结ReDive"
PRINCESS_CONNECT_BILIBILI_UID = "353840826"
PRINCESS_CONNECT_BILIBILI_OPUS_ID = "1259278024604385281"

_POST = re.compile(
    r'<a class="post-link" href="(?P<href>/news/detail/'
    r'(?P<id>\d+)\.html)">\s*<article class="post">'
    r"(?P<body>.*?)</article>\s*</a>",
    re.DOTALL,
)
_POST_TIME = re.compile(r'<div class="time">(?P<time>.*?)<span', re.DOTALL)
_POST_TEXT = re.compile(r'<div class="post-text">(?P<text>.*?)</div>', re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_CHARACTER = re.compile(
    r"(?:新角色|期间限定角色|公主庆典限定角色)?\s*"
    r"(?:★|☆|⭐)\s*\d*\s*[「](?P<name>[^」]+)[」]"
)


@dataclass(frozen=True, slots=True)
class SinaPost:
    post_id: str
    url: str
    published_at: datetime
    text: str
    revision: str


def _plain_text(value: str) -> str:
    return " ".join(unescape(_TAG.sub(" ", value)).split())


def _published_at(value: str) -> datetime | None:
    match = re.search(
        r"(20\d{2})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})",
        _plain_text(value),
    )
    if match is None:
        return None
    try:
        return datetime(
            year=int(match.group(1)),
            month=int(match.group(2)),
            day=int(match.group(3)),
            hour=int(match.group(4)),
            minute=int(match.group(5)),
            tzinfo=UTC8,
        )
    except ValueError:
        return None


def _sina_posts(html: str) -> list[SinaPost]:
    if PRINCESS_CONNECT_OFFICIAL_NAME not in _plain_text(html):
        raise BannerSourceError(
            "princessconnect: official Sina profile identity is missing"
        )
    posts: dict[str, SinaPost] = {}
    for match in _POST.finditer(html):
        article = match.group("body")
        time_match = _POST_TIME.search(article)
        text_match = _POST_TEXT.search(article)
        if time_match is None or text_match is None:
            raise BannerSourceError(
                "princessconnect: Sina post is missing time or text"
            )
        published_at = _published_at(time_match.group("time"))
        if published_at is None:
            raise BannerSourceError(
                "princessconnect: Sina post has no absolute publication time"
            )
        post_id = match.group("id")
        post_text = _plain_text(text_match.group("text"))
        posts[post_id] = SinaPost(
            post_id=post_id,
            url=f"https://www.sina.cn{match.group('href')}",
            published_at=published_at,
            text=post_text,
            revision=stable_digest(post_id, published_at.isoformat(), post_text),
        )
    if not posts:
        raise BannerSourceError("princessconnect: Sina profile has no posts")
    return sorted(
        posts.values(),
        key=lambda post: post.published_at,
        reverse=True,
    )


def _princess_pool_sections(text: str) -> list[tuple[str, str]]:
    """Split only explicit pool products out of an official post."""

    if "礼包" in text and not any(term in text for term in ("扭蛋", "招募")):
        return []
    if "维护" in text and not any(term in text for term in ("扭蛋", "招募")):
        return []

    character_match = _CHARACTER.search(text)
    character = (
        character_match.group("name").strip() if character_match is not None else ""
    )
    sections: list[tuple[str, str]] = []
    if "精选扭蛋" in text:
        sections.append(
            (
                f"精选扭蛋｜{character}" if character else "精选扭蛋",
                f"维护后\n{text}",
            )
        )
    if "自选复刻" in text and "附奖扭蛋" in text:
        sections.append(("自选复刻附奖扭蛋｜限定角色", f"维护后\n{text}"))
    if "白金扭蛋" in text:
        sections.append(("白金扭蛋｜★3必得", f"维护后\n{text}"))
    if "公主庆典扭蛋" in text and "白金扭蛋" not in text:
        sections.append(
            (
                f"公主庆典扭蛋｜{character}" if character else "公主庆典扭蛋",
                f"维护后\n{text}",
            )
        )
    return list(dict.fromkeys(sections))


class PrincessConnectSource(BaseBannerSource):
    game = "princessconnect"
    source_key = "princessconnect"
    authoritative_url = f"https://www.sina.cn/media/{PRINCESS_CONNECT_SINA_ID}"
    profile_url = authoritative_url

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        verified_at: str,
    ) -> list[ObservationDraft]:
        response = await self._request(client, self.profile_url)
        drafts: list[ObservationDraft] = []
        for post in _sina_posts(response.text):
            for title, body_text in _princess_pool_sections(post.text):
                combined = f"{title}\n{body_text}"
                drafts.append(
                    self._draft(
                        title=title,
                        body_text=body_text,
                        published_at=post.published_at,
                        official_url=post.url,
                        article_id=post.post_id,
                        official_id=explicit_pool_id(combined),
                        verified_at=verified_at,
                        revision=f"{post.revision}:{title}",
                        cancelled=explicit_cancellation(combined),
                        related=[f"{self.source_key}:article:{post.post_id}"],
                    )
                )
        return drafts
