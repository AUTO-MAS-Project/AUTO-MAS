"""Blue Archive Bilibili account and official TapTap discovery."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from .base import (
    UTC8,
    BannerSourceError,
    BaseBannerSource,
    ObservationDraft,
    PoolSection,
    datetime_from_epoch,
    explicit_cancellation,
    explicit_pool_id,
    stable_digest,
)
from .taptap import (
    TapTapRecord,
    collect_taptap_records,
)

BLUEARCHIVE_BILIBILI_UID = "3493265644980448"
BLUEARCHIVE_TAPTAP_APP_ID = "316964"
BLUEARCHIVE_OPUS_ID = "1168392597461270533"

_BA_POOL_HEADING = re.compile(
    r"^(?:•\s*)?(?:(?:\d+|[一二三四五六七八九十]+)[、.]\s*)?"
    r"(?:更新)?(?P<label>"
    r"(?:限时)?(?:限定)?复刻招募|限时招募|复刻招募|限定招募|常驻招募"
    r")【(?P<name>[^】]+)】"
)
_MAINTENANCE_DATE = re.compile(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日\s*维护结束")
_MAINTENANCE_COMPLETE = re.compile(r"维护(?:更新)?(?:已|已经)?结束|正式开服")
_BA_EVENT_ALIASES = {
    "片雨让白昼": "骤雨让白昼",
    "春阴映白浪": "花阴映白浪",
}


def _module_map(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(module.get("module_type")): module
        for module in item.get("modules", [])
        if isinstance(module, dict)
    }


def _module_text(modules: dict[str, dict[str, Any]]) -> str:
    dynamic = modules.get("MODULE_TYPE_DYNAMIC") or {}
    desc = dynamic.get("desc")
    if isinstance(desc, dict) and isinstance(desc.get("text"), str):
        return desc["text"]

    content = modules.get("MODULE_TYPE_CONTENT") or {}
    module_content = content.get("module_content") or {}
    lines: list[str] = []
    for paragraph in module_content.get("paragraphs") or []:
        if not isinstance(paragraph, dict):
            continue
        paragraph_text = paragraph.get("text")
        if not isinstance(paragraph_text, dict):
            continue
        for node in paragraph_text.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            word = node.get("word")
            rich = node.get("rich")
            if isinstance(word, dict):
                lines.append(str(word.get("words") or ""))
            elif isinstance(rich, dict):
                lines.append(str(rich.get("text") or ""))
    return "".join(lines)


def _bluearchive_sections(title: str, body_text: str) -> list[PoolSection]:
    del title
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    schedule: list[str] = []
    for index, line in enumerate(lines):
        if "招募时间" in line:
            schedule = [value for value in lines[index : index + 3] if value]
            break

    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = _BA_POOL_HEADING.match(line)
        if match is None:
            continue
        headings.append(
            (
                index,
                f"{match.group('label')}【{match.group('name').strip()}】",
            )
        )
    sections: list[PoolSection] = []
    for position, (heading_index, heading) in enumerate(headings):
        next_index = (
            headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        )
        end_index = next_index
        for index in range(heading_index + 1, next_index):
            if re.match(r"^(?:\d+[、.])", lines[index]):
                end_index = index
                break
        content = lines[heading_index:end_index]
        while content and content[-1].startswith("#"):
            content.pop()
        sections.append(
            PoolSection(
                title=heading,
                text="\n".join((*schedule, *content)),
            )
        )
    return list(
        {(section.title, section.text): section for section in sections}.values()
    )


def _local_date(value: datetime) -> tuple[int, int]:
    local = value.astimezone(UTC8)
    return local.month, local.day


def _confirmation_points(
    records: list[TapTapRecord],
) -> dict[tuple[int, int], TapTapRecord]:
    confirmations: dict[tuple[int, int], TapTapRecord] = {}
    for record in records:
        if (
            record.published_at is None
            or _MAINTENANCE_COMPLETE.search(record.body_text) is None
        ):
            continue
        key = _local_date(record.published_at)
        current = confirmations.get(key)
        if (
            current is None
            or current.published_at is None
            or record.published_at < current.published_at
        ):
            confirmations[key] = record
    return confirmations


def _scheduled_maintenance_date(
    section: PoolSection,
) -> tuple[int, int] | None:
    match = _MAINTENANCE_DATE.search(section.text)
    if match is None:
        return None
    return int(match.group("month")), int(match.group("day"))


def _bluearchive_event(section: PoolSection) -> str:
    bracket = re.search(r"【([^】]+)】", section.title)
    return bracket.group(1).strip() if bracket else section.title


def _bluearchive_identity(
    section: PoolSection,
) -> str:
    event = _bluearchive_event(section)
    canonical = _BA_EVENT_ALIASES.get(event, event)
    return f"event:{canonical}"


def _bluearchive_anchor_title(identity: str) -> str:
    return f"招募｜{identity}"


def _bluearchive_candidate(moment: dict[str, Any]) -> bool:
    topic = moment.get("topic")
    topic = topic if isinstance(topic, dict) else {}
    text = f"{topic.get('title') or ''}\n{topic.get('summary') or ''}"
    return any(
        term in text
        for term in (
            "招募",
            "维护更新说明",
            "维护更新已结束",
            "介绍PV",
            "现已开启",
        )
    )


class BlueArchiveBilibiliSource(BaseBannerSource):
    game = "bluearchive"
    source_key = "bluearchive"
    authoritative_url = f"https://www.bilibili.com/opus/{BLUEARCHIVE_OPUS_ID}"
    space_url = f"https://space.bilibili.com/{BLUEARCHIVE_BILIBILI_UID}/dynamic"
    feed_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
    opus_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail"

    def _verify_official(self, item: dict[str, Any]) -> None:
        basic = item.get("basic")
        uid = basic.get("uid") if isinstance(basic, dict) else None
        modules = _module_map(item)
        author = modules.get("MODULE_TYPE_AUTHOR") or {}
        module_author = author.get("module_author") or {}
        if str(uid or module_author.get("mid") or "") != BLUEARCHIVE_BILIBILI_UID:
            raise BannerSourceError(
                "bluearchive: Bilibili item is outside the official account"
            )
        official = module_author.get("official")
        if not isinstance(official, dict) or official.get("role") not in {3, "3"}:
            raise BannerSourceError("bluearchive: Bilibili author is not verified")

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        verified_at: str,
    ) -> list[ObservationDraft]:
        drafts: list[ObservationDraft] = []
        try:
            # The public page supplies anonymous cookies required by the feed.
            await self._request(client, self.authoritative_url)
            feed_response = await self._request(
                client,
                self.feed_url,
                params={
                    "host_mid": BLUEARCHIVE_BILIBILI_UID,
                    "timezone_offset": "-480",
                    "features": "itemOpusStyle",
                },
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Referer": self.space_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            payload = feed_response.json()
            if isinstance(payload, dict) and payload.get("code") == 0:
                items = (payload.get("data") or {}).get("items") or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("id_str") or "").strip()
                    if not item_id:
                        continue
                    drafts.extend(
                        self._draft_items(
                            item=item,
                            verified_at=verified_at,
                            public_url=f"https://www.bilibili.com/opus/{item_id}",
                        )
                    )
        except (BannerSourceError, ValueError):
            pass

        record_error: Exception | None = None
        records: list[TapTapRecord] = []
        try:
            records = await collect_taptap_records(
                owner=self,
                client=client,
                app_id=BLUEARCHIVE_TAPTAP_APP_ID,
                candidate=_bluearchive_candidate,
            )
            drafts.extend(
                self._draft_taptap_records(
                    records=records,
                    verified_at=verified_at,
                )
            )
        except (BannerSourceError, ValueError) as error:
            record_error = error

        if record_error is not None:
            if isinstance(record_error, BannerSourceError):
                raise record_error
            raise BannerSourceError(
                "bluearchive: required TapTap discovery failed"
            ) from record_error
        if drafts:
            return drafts

        anchor_response = await self._request(
            client,
            self.opus_url,
            params={
                "timezone_offset": "-480",
                "id": BLUEARCHIVE_OPUS_ID,
            },
            headers={"Referer": self.authoritative_url},
        )
        anchor_payload = anchor_response.json()
        item = (
            (anchor_payload.get("data") or {}).get("item")
            if isinstance(anchor_payload, dict)
            else None
        )
        if not isinstance(item, dict):
            raise BannerSourceError(
                "bluearchive: Bilibili and TapTap discovery both failed"
            )
        return self._draft_items(
            item=item,
            verified_at=verified_at,
            public_url=self.authoritative_url,
        )

    def _draft_taptap_records(
        self,
        *,
        records: list[TapTapRecord],
        verified_at: str,
    ) -> list[ObservationDraft]:
        confirmations = _confirmation_points(records)
        specific = [record for record in records if "维护更新说明" not in record.title]
        maintenance = [record for record in records if "维护更新说明" in record.title]
        section_cache: dict[str, list[PoolSection]] = {}
        for record in records:
            sections = _bluearchive_sections(
                record.title,
                record.body_text,
            )
            section_cache[record.article_id] = sections

        maintenance_links: dict[str, list[str]] = {}
        maintenance_sections: list[tuple[TapTapRecord, PoolSection]] = []
        for record in maintenance:
            for section in section_cache[record.article_id]:
                identity = _bluearchive_identity(section)
                maintenance_sections.append((record, section))
                maintenance_links.setdefault(identity, []).append(record.article_id)
        drafts: list[ObservationDraft] = []
        seen_identities: set[str] = set()
        for record in specific:
            for section in section_cache[record.article_id]:
                identity = _bluearchive_identity(section)
                if identity in seen_identities:
                    continue
                seen_identities.add(identity)
                maintenance_date = _scheduled_maintenance_date(section)
                confirmation = (
                    confirmations.get(maintenance_date)
                    if maintenance_date is not None
                    else None
                )
                related = [f"{self.source_key}:article:{record.article_id}"]
                related.extend(
                    f"{self.source_key}:maintenance:{article_id}"
                    for article_id in maintenance_links.get(identity, [])
                )
                if confirmation is not None:
                    related.append(
                        f"{self.source_key}:maintenance:{confirmation.article_id}"
                    )
                combined = f"{section.title}\n{section.text}"
                drafts.append(
                    self._draft(
                        title=section.title,
                        body_text=section.text,
                        published_at=record.published_at,
                        official_url=record.detail_url,
                        article_id=record.article_id,
                        official_id=explicit_pool_id(combined),
                        verified_at=verified_at,
                        revision=f"{record.revision}:{section.title}",
                        cancelled=explicit_cancellation(combined),
                        related=related,
                        confirmed_open_at_override=(
                            confirmation.published_at
                            if confirmation is not None
                            else None
                        ),
                        anchor_title=_bluearchive_anchor_title(identity),
                    )
                )
        for record, section in maintenance_sections:
            identity = _bluearchive_identity(section)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            combined = f"{section.title}\n{section.text}"
            drafts.append(
                self._draft(
                    title=section.title,
                    body_text=section.text,
                    published_at=record.published_at,
                    official_url=record.detail_url,
                    article_id=record.article_id,
                    official_id=explicit_pool_id(combined),
                    verified_at=verified_at,
                    revision=f"{record.revision}:{section.title}",
                    cancelled=explicit_cancellation(combined),
                    related=[f"{self.source_key}:article:{record.article_id}"],
                    anchor_title=_bluearchive_anchor_title(identity),
                )
            )
        return drafts

    def _draft_items(
        self,
        *,
        item: dict[str, Any],
        verified_at: str,
        public_url: str,
    ) -> list[ObservationDraft]:
        basic = item.get("basic") or {}
        item_id = str(item.get("id_str") or basic.get("rid_str") or "").strip()
        if not item_id:
            raise BannerSourceError("bluearchive: Bilibili item has no id")
        modules = _module_map(item)
        text = _module_text(modules)
        self._verify_official(item)
        author = modules.get("MODULE_TYPE_AUTHOR") or {}
        module_author = author.get("module_author") or {}
        published_at = datetime_from_epoch(
            module_author.get("pub_ts")
            or module_author.get("ptime")
            or item.get("pub_ts")
        )
        drafts: list[ObservationDraft] = []
        for section in _bluearchive_sections("", text):
            identity = _bluearchive_identity(section)
            combined = f"{section.title}\n{section.text}"
            revision = stable_digest(
                item_id,
                text,
                published_at.isoformat() if published_at is not None else None,
            )
            drafts.append(
                self._draft(
                    title=section.title,
                    body_text=section.text,
                    published_at=published_at,
                    official_url=public_url,
                    article_id=item_id,
                    official_id=explicit_pool_id(combined),
                    verified_at=verified_at,
                    revision=f"{revision}:{section.title}",
                    cancelled=explicit_cancellation(combined),
                    related=[f"{self.source_key}:article:{item_id}"],
                    anchor_title=_bluearchive_anchor_title(identity),
                )
            )
        return drafts
