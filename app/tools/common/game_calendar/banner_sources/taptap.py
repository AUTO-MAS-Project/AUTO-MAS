"""TapTap official-topic adapters for Azur Lane and Resonance."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
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
    stable_digest,
)

MAX_TAPTAP_PAGES = 4
MAX_TAPTAP_DETAILS = 24
_NUXT_DATA = re.compile(
    r'<script[^>]+id="__NUXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class TapTapRecord:
    article_id: str
    title: str
    body_text: str
    published_at: datetime | None
    edited_time: object
    detail_url: str
    revision: str


def _nuxt_payload(html: str) -> list[Any]:
    match = _NUXT_DATA.search(html)
    if match is None:
        raise BannerSourceError("taptap: page has no __NUXT_DATA__ payload")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise BannerSourceError("taptap: __NUXT_DATA__ is not valid JSON") from error
    if not isinstance(payload, list):
        raise BannerSourceError("taptap: __NUXT_DATA__ root is invalid")
    return payload


def _resolve(payload: list[Any], reference: object) -> Any:
    if not isinstance(reference, int) or isinstance(reference, bool):
        return reference
    if reference < 0 or reference >= len(payload):
        return None
    value = payload[reference]
    if isinstance(value, dict):
        return {key: _resolve(payload, child) for key, child in value.items()}
    if isinstance(value, list):
        if value and value[0] in {
            "ShallowReactive",
            "Reactive",
            "Ref",
            "ShallowRef",
        }:
            return _resolve(payload, value[1])
        if value and value[0] == "Set":
            return {_resolve(payload, child) for child in value[1:]}
        return [_resolve(payload, child) for child in value]
    return value


def _resolved_moment(
    payload: list[Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id_str": str(_resolve(payload, raw.get("id_str")) or ""),
        "created_time": _resolve(payload, raw.get("created_time")),
        "edited_time": _resolve(payload, raw.get("edited_time")),
        "publish_time": _resolve(payload, raw.get("publish_time")),
        "is_official": _resolve(payload, raw.get("is_official")),
        "author": _resolve(payload, raw.get("author")) or {},
        "topic": _resolve(payload, raw.get("topic")) or {},
    }


def _taptap_moments(html: str) -> list[dict[str, Any]]:
    payload = _nuxt_payload(html)
    moments: dict[str, dict[str, Any]] = {}
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        if not {"id_str", "publish_time", "topic"} <= raw.keys():
            continue
        moment = _resolved_moment(payload, raw)
        if moment["id_str"].isdigit() and moment["is_official"] is True:
            moments[moment["id_str"]] = moment
    return list(moments.values())


def _tap_detail(html: str) -> tuple[dict[str, Any], list[str]]:
    payload = _nuxt_payload(html)
    for raw in payload:
        if (
            not isinstance(raw, dict)
            or not {
                "moment",
                "first_post",
            }
            <= raw.keys()
        ):
            continue
        moment_raw = _resolve(payload, raw.get("moment"))
        first_post = _resolve(payload, raw.get("first_post"))
        if not isinstance(moment_raw, dict) or not isinstance(first_post, dict):
            continue
        moment = moment_raw
        lines: list[str] = []
        contents = first_post.get("contents")
        if isinstance(contents, dict):
            for paragraph in contents.get("json") or []:
                if not isinstance(paragraph, dict):
                    continue
                text = "".join(
                    str(child.get("text") or "")
                    for child in paragraph.get("children") or []
                    if isinstance(child, dict)
                ).strip()
                if text:
                    lines.append(text)
        return moment, lines
    raise BannerSourceError("taptap: moment detail payload is missing")


def _app_id(moment: dict[str, Any]) -> str | None:
    author = moment.get("author")
    if not isinstance(author, dict):
        return None
    app = author.get("app")
    if not isinstance(app, dict):
        return None
    value = app.get("id")
    return str(value) if value is not None else None


def _topic_text(moment: dict[str, Any]) -> str:
    topic = moment.get("topic")
    topic = topic if isinstance(topic, dict) else {}
    return "\n".join(
        str(value) for value in (topic.get("title"), topic.get("summary")) if value
    )


def _record_from_detail(
    *,
    moment: dict[str, Any],
    lines: list[str],
    article_id: str,
) -> TapTapRecord:
    topic = moment.get("topic")
    topic = topic if isinstance(topic, dict) else {}
    title = str(topic.get("title") or "").strip()
    if not title:
        title = next(
            (line for line in lines if line and not line.startswith("#")),
            "",
        )
    body_text = "\n".join(lines)
    if not body_text:
        body_text = str(topic.get("summary") or "")
    published_at = datetime_from_epoch(moment.get("publish_time"))
    return TapTapRecord(
        article_id=article_id,
        title=title,
        body_text=body_text,
        published_at=published_at,
        edited_time=moment.get("edited_time"),
        detail_url=f"https://www.taptap.cn/moment/{article_id}",
        revision=stable_digest(
            article_id,
            title,
            body_text,
            moment.get("publish_time"),
            moment.get("edited_time"),
        ),
    )


async def collect_taptap_records(
    *,
    owner: BaseBannerSource,
    client: httpx.AsyncClient,
    app_id: str,
    candidate: Callable[[dict[str, Any]], bool],
) -> list[TapTapRecord]:
    """Collect recurring official moments without treating excerpts as body."""

    moments: dict[str, dict[str, Any]] = {}
    for page in range(1, MAX_TAPTAP_PAGES + 1):
        topic_url = f"https://www.taptap.cn/app/{app_id}/topic"
        params = {"type": "official"}
        if page > 1:
            params["page"] = str(page)
        topic_response = await owner._request(
            client,
            topic_url,
            params=params,
        )
        page_moments = _taptap_moments(topic_response.text)
        if not page_moments:
            break
        previous_count = len(moments)
        for moment in page_moments:
            moments[moment["id_str"]] = moment
        if len(moments) == previous_count:
            break

    selected = [moment for moment in moments.values() if candidate(moment)]
    selected.sort(
        key=lambda moment: int(moment.get("publish_time") or 0),
        reverse=True,
    )
    records: list[TapTapRecord] = []
    for list_moment in selected[:MAX_TAPTAP_DETAILS]:
        article_id = str(list_moment["id_str"])
        detail_response = await owner._request(
            client,
            f"https://www.taptap.cn/moment/{article_id}",
        )
        moment, lines = _tap_detail(detail_response.text)
        if _app_id(moment) != app_id:
            raise BannerSourceError(
                f"taptap: moment {article_id} is outside app {app_id}"
            )
        record = _record_from_detail(
            moment=moment,
            lines=lines,
            article_id=article_id,
        )
        if record.title and record.body_text and candidate(moment):
            records.append(record)
    return records


def _drafts_from_sections(
    *,
    owner: BaseBannerSource,
    records: list[TapTapRecord],
    verified_at: str,
    sectioner: Callable[[str, str], list[PoolSection]],
) -> list[ObservationDraft]:
    drafts: list[ObservationDraft] = []
    for record in records:
        for section in sectioner(record.title, record.body_text):
            combined = f"{section.title}\n{section.text}"
            drafts.append(
                owner._draft(
                    title=section.title,
                    body_text=section.text,
                    published_at=record.published_at,
                    official_url=record.detail_url,
                    article_id=record.article_id,
                    official_id=explicit_pool_id(combined),
                    verified_at=verified_at,
                    revision=f"{record.revision}:{section.title}",
                    cancelled=explicit_cancellation(combined),
                    related=[f"{owner.source_key}:article:{record.article_id}"],
                )
            )
    return drafts


def _azurlane_candidate(moment: dict[str, Any]) -> bool:
    text = _topic_text(moment)
    return any(
        term in text
        for term in (
            "港区改建",
            "限时建造",
            "永久加入常规建造",
            "建造池常驻新增",
        )
    )


_AZUR_SHIP = re.compile(
    r"^(?P<name>.+?)\s+(?:海上传奇|超稀有|精锐|稀有|普通)\s+\d+(?:\.\d+)?%$"
)
_AZUR_PERMANENT_BULLET = re.compile(r"^•\s*(?P<title>.+?建造池常驻新增\s*[:：]\s*.+)$")


def _azurlane_sections(title: str, body_text: str) -> list[PoolSection]:
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    sections: list[PoolSection] = []

    if "永久加入常规建造" in title:
        subject_match = re.search(r"「([^」]+)」", title)
        subject = subject_match.group(1) if subject_match is not None else ""
        sections.append(
            PoolSection(
                title=f"常驻建造｜{subject}" if subject else "常驻建造",
                text=body_text,
            )
        )

    try:
        build_start = next(
            index for index, line in enumerate(lines) if line.startswith("◆限时建造")
        )
    except StopIteration:
        build_start = -1
    if build_start >= 0:
        build_end = next(
            (
                index
                for index in range(build_start + 1, len(lines))
                if lines[index].startswith("◆")
            ),
            len(lines),
        )
        block = lines[build_start:build_end]
        ships = []
        for line in block[1:]:
            if line.startswith("※"):
                break
            match = _AZUR_SHIP.match(line)
            if match is not None:
                ships.append(match.group("name"))
        subject = "、".join(dict.fromkeys(ships))
        sections.append(
            PoolSection(
                title=f"限时建造｜{subject}" if subject else "限时建造",
                text="维护后\n" + "\n".join(block),
            )
        )

    permanent_context = next(
        (
            index
            for index, line in enumerate(lines)
            if "下列角色将永久回归常规建造" in line
        ),
        -1,
    )
    if permanent_context >= 0:
        for index in range(permanent_context + 1, len(lines)):
            match = _AZUR_PERMANENT_BULLET.match(lines[index])
            if match is None:
                if lines[index].startswith("•"):
                    continue
                break
            sections.append(
                PoolSection(
                    title=match.group("title"),
                    text=(
                        "维护后永久回归常规建造\n"
                        f"{lines[permanent_context]}\n{lines[index]}"
                    ),
                )
            )
    unique = {(section.title, section.text): section for section in sections}
    return list(unique.values())


def _resonance_candidate(moment: dict[str, Any]) -> bool:
    text = _topic_text(moment)
    return "卡池相关" in text or any(
        term in text for term in ("特设招募", "专列招募", "常驻招募")
    )


_RESONANCE_HEADING = re.compile(r"^【(?P<label>[^】]+招募)】$")


def _resonance_sections(title: str, body_text: str) -> list[PoolSection]:
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    try:
        start = (
            next(index for index, line in enumerate(lines) if line == "▌卡池相关") + 1
        )
    except StopIteration:
        return []
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("▌")),
        len(lines),
    )
    headings = [
        (index, match.group("label"))
        for index in range(start, end)
        if (match := _RESONANCE_HEADING.match(lines[index])) is not None
    ]
    sections: list[PoolSection] = []
    for position, (heading_index, heading) in enumerate(headings):
        next_index = headings[position + 1][0] if position + 1 < len(headings) else end
        block = lines[heading_index:next_index]
        subject = ""
        for line in block[1:]:
            if line.startswith("起止时间"):
                break
            if (
                len(line) <= 40
                and "招募说明" not in line
                and not re.match(r"^(?:SSR|UR|★\d)", line)
            ):
                subject = line
                break
        for line in block[1:]:
            if subject:
                break
            if "招募说明" in line:
                continue
            quoted = re.search(r"[“「]([^”」]+)[”」]", line)
            if quoted is not None:
                subject = quoted.group(1).strip()
                break
            unquoted = re.match(
                r"^(?:SSR|UR|★\d)?\s*(.+?)\s*获得概率提升",
                line,
            )
            if unquoted is not None:
                subject = unquoted.group(1).strip()
                break
        section_title = f"{heading}｜{subject}" if subject else heading
        sections.append(
            PoolSection(
                title=section_title,
                text="\n".join(block),
            )
        )
    return sections


class TaptapOfficialSource(BaseBannerSource):
    app_id: str
    candidate: Callable[[dict[str, Any]], bool]
    sectioner: Callable[[str, str], list[PoolSection]]

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        verified_at: str,
    ) -> list[ObservationDraft]:
        records = await collect_taptap_records(
            owner=self,
            client=client,
            app_id=self.app_id,
            candidate=self.candidate,
        )
        return _drafts_from_sections(
            owner=self,
            records=records,
            verified_at=verified_at,
            sectioner=self.sectioner,
        )


class AzurLaneSource(TaptapOfficialSource):
    game = "azurlane"
    source_key = "azurlane"
    app_id = "31597"
    authoritative_url = "https://www.taptap.cn/moment/861667880171735573"
    candidate = staticmethod(_azurlane_candidate)
    sectioner = staticmethod(_azurlane_sections)


class ResonanceSource(TaptapOfficialSource):
    game = "resonance"
    source_key = "resonance"
    app_id = "226568"
    authoritative_url = "https://www.taptap.cn/moment/872109359222491961"
    candidate = staticmethod(_resonance_candidate)
    sectioner = staticmethod(_resonance_sections)
