"""Hypergryph CMS and server-rendered news adapters."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .base import (
    BannerSourceError,
    BaseBannerSource,
    ObservationDraft,
    PoolSection,
    datetime_from_epoch,
    explicit_cancellation,
    explicit_pool_id,
    html_to_text,
    is_banner_text,
    split_pool_sections,
    stable_digest,
)

MAX_HYPERGRYPH_ARTICLES = 12

_ENDFIELD_POOL_HEADING = re.compile(
    r"^\d+[.、]\s*(?P<title>「[^」]+」(?:[^」\s]+)?)\s*$"
)


def _next_rsc_text(html: str) -> str:
    parts: list[str] = []
    for match in re.finditer(
        r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)',
        html,
        re.DOTALL,
    ):
        try:
            parts.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _json_value_after_marker(text: str, marker: str) -> Any:
    marker_index = text.find(marker)
    if marker_index < 0:
        raise ValueError(f"missing marker {marker}")
    start = marker_index + len(marker)
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] not in "{[":
        raise ValueError(f"marker {marker} is not followed by JSON")

    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError(f"unterminated JSON after marker {marker}")


def _walk_mappings(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def _endfield_version_sections(
    title: str,
    body_text: str,
) -> list[PoolSection]:
    """Extract pool headings from an official version announcement.

    A same-named standalone "限时特卖" post is not pool evidence. Only the
    numbered headings under "全新寻访及申领" in a version announcement are
    accepted here.
    """

    if "版本更新说明" not in title:
        return []
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    try:
        start = (
            next(index for index, line in enumerate(lines) if "全新寻访及申领" in line)
            + 1
        )
    except StopIteration:
        return []
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("■")),
        len(lines),
    )
    headings: list[tuple[int, str]] = []
    for index in range(start, end):
        match = _ENDFIELD_POOL_HEADING.match(lines[index])
        if match is None:
            continue
        heading = match.group("title")
        if any(term in heading for term in ("寻访", "申领")):
            headings.append((index, heading))
    sections: list[PoolSection] = []
    for position, (heading_index, heading) in enumerate(headings):
        next_index = headings[position + 1][0] if position + 1 < len(headings) else end
        sections.append(
            PoolSection(
                title=heading,
                text="\n".join(lines[heading_index:next_index]),
            )
        )
    return sections


def _endfield_sections(title: str, body_text: str) -> list[PoolSection]:
    version_sections = _endfield_version_sections(title, body_text)
    if version_sections:
        return version_sections
    return split_pool_sections(title, body_text)


class EndfieldSource(BaseBannerSource):
    game = "endfield"
    source_key = "endfield"
    authoritative_url = "https://endfield.hypergryph.com/news/7204"
    list_url = (
        "https://web-news.hypergryph.com/api/bulletin"
        "?lang=zh-cn&code=endfield_web&page=1&pageSize=30"
        "&tabs%5B%5D=notices"
    )
    detail_url = "https://web-news.hypergryph.com/api/bulletin/{cid}"
    public_url = "https://endfield.hypergryph.com/news/{cid}"

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
            raise BannerSourceError("endfield: bulletin list is missing")

        drafts: list[ObservationDraft] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "")
            brief = html_to_text(entry.get("brief"))
            if "限时特卖" in title:
                continue
            if not (
                any(
                    term in title
                    for term in (
                        "特许寻访",
                        "重构寻访",
                        "限定寻访",
                        "限时寻访",
                        "版本更新说明",
                    )
                )
            ):
                continue
            cid = str(entry.get("cid") or "").strip()
            if not cid:
                raise BannerSourceError("endfield: banner entry has no cid")
            url = self.detail_url.format(cid=cid) + "?lang=zh-cn&code=endfield_web"
            detail_response = await self._request(client, url)
            detail_payload = detail_response.json()
            detail = (
                detail_payload.get("data") if isinstance(detail_payload, dict) else None
            )
            if not isinstance(detail, dict):
                raise BannerSourceError(f"endfield: invalid bulletin detail for {cid}")
            detail_title = detail.get("title") or title
            body_text = html_to_text(detail.get("data")) or brief
            published_at = datetime_from_epoch(
                detail.get("displayTime") or entry.get("displayTime")
            )
            revision = stable_digest(
                cid,
                detail_title,
                body_text,
                published_at.isoformat() if published_at is not None else None,
            )
            for section in _endfield_sections(detail_title, body_text):
                combined = f"{section.title}\n{section.text}"
                drafts.append(
                    self._draft(
                        title=section.title,
                        body_text=section.text,
                        published_at=published_at,
                        official_url=self.public_url.format(cid=cid),
                        article_id=cid,
                        official_id=explicit_pool_id(combined),
                        verified_at=verified_at,
                        revision=f"{revision}:{section.title}",
                        cancelled=explicit_cancellation(combined),
                        related=[f"{self.source_key}:article:{cid}"],
                    )
                )
            if len(drafts) >= MAX_HYPERGRYPH_ARTICLES:
                break
        return drafts


class ArknightsSource(BaseBannerSource):
    game = "arknights"
    source_key = "arknights"
    authoritative_url = "https://ak.hypergryph.com/news/1457"
    list_url = "https://ak.hypergryph.com/news"
    detail_url = "https://ak.hypergryph.com/news/{cid}"

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        verified_at: str,
    ) -> list[ObservationDraft]:
        list_response = await self._request(client, self.list_url)
        rsc_text = _next_rsc_text(list_response.text)
        try:
            initial_data = _json_value_after_marker(
                rsc_text,
                '"initialData":',
            )
        except (ValueError, json.JSONDecodeError) as error:
            raise BannerSourceError(
                "arknights: news list payload is missing"
            ) from error

        candidates: dict[str, dict[str, Any]] = {}
        for item in _walk_mappings(initial_data):
            cid = item.get("cid")
            title = item.get("title")
            if cid is None or not isinstance(title, str):
                continue
            cid_text = str(cid)
            if not is_banner_text(f"{title}\n{item.get('brief') or ''}"):
                continue
            current = candidates.get(cid_text)
            if current is None or len(str(item.get("brief") or "")) > len(
                str(current.get("brief") or "")
            ):
                candidates[cid_text] = item

        drafts: list[ObservationDraft] = []
        for cid, candidate in list(candidates.items())[:MAX_HYPERGRYPH_ARTICLES]:
            detail_response = await self._request(
                client,
                self.detail_url.format(cid=cid),
            )
            detail_rsc = _next_rsc_text(detail_response.text)
            try:
                article = _json_value_after_marker(
                    detail_rsc,
                    '"articleData":',
                )
            except (ValueError, json.JSONDecodeError) as error:
                raise BannerSourceError(
                    f"arknights: detail payload is missing for {cid}"
                ) from error
            title = str(article.get("title") or candidate.get("title") or "")
            body_text = html_to_text(article.get("brief")) or html_to_text(
                candidate.get("brief")
            )
            published_at = datetime_from_epoch(
                article.get("displayTime") or candidate.get("displayTime")
            )
            revision = stable_digest(
                cid,
                title,
                body_text,
                published_at.isoformat() if published_at is not None else None,
            )
            for section in split_pool_sections(title, body_text):
                combined = f"{section.title}\n{section.text}"
                drafts.append(
                    self._draft(
                        title=section.title,
                        body_text=section.text,
                        published_at=published_at,
                        official_url=self.detail_url.format(cid=cid),
                        article_id=cid,
                        official_id=explicit_pool_id(combined),
                        verified_at=verified_at,
                        revision=f"{revision}:{section.title}",
                        cancelled=explicit_cancellation(combined),
                        related=[f"{self.source_key}:article:{cid}"],
                    )
                )
        return drafts
