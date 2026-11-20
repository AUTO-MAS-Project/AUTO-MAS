"""Shared HTTP, normalization, and observation helpers for banner sources."""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any, Literal, Protocol, TypedDict

import httpx

UTC8 = timezone(timedelta(hours=8))
UTC = timezone.utc
RECENT_DISCOVERY_DAYS = 270
DEFAULT_HEADERS = {
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0 Safari/537.36 AUTO-MAS-banner-watch/1.0"
    ),
}

StartMode = Literal["scheduled", "after_maintenance", "tbd"]
EndKind = Literal["known", "permanent", "unknown"]


class BannerObservation(TypedDict):
    game: str
    server: str
    title: str
    kind: str
    start_mode: StartMode
    starts_at: str | None
    ends_at: str | None
    end_kind: EndKind
    confirmed_open_at: str | None
    official_url: str
    verified_at: str
    published_at: str | None
    official_id: str | None
    article_id: str | None
    source_anchor: str
    revision: str
    cancelled: bool
    replaces: list[str]
    related: list[str]
    publication_order: int


class BannerSource(Protocol):
    async def fetch(self) -> list[BannerObservation]: ...


class BannerSourceError(RuntimeError):
    """An official source could not be fetched or verified."""


@dataclass(frozen=True, slots=True)
class ObservationDraft:
    published_at: datetime | None
    data: BannerObservation


@dataclass(frozen=True, slots=True)
class PoolSection:
    title: str
    text: str


class _VisibleTextParser(HTMLParser):
    block_tags = {
        "br",
        "div",
        "li",
        "ol",
        "p",
        "section",
        "table",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: object) -> str:
    """Return readable text without making HTML structure part of the contract."""

    if not isinstance(value, str):
        return ""
    parser = _VisibleTextParser()
    parser.feed(unescape(value))
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC8).astimezone(UTC)
    return value.astimezone(UTC)


def utc_iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def datetime_from_epoch(value: object) -> datetime | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


_DATE_LITERAL = re.compile(
    r"(?:(?P<year>20\d{2})\s*[/.-]\s*)?"
    r"(?P<month>\d{1,2})\s*[/.-]\s*(?P<day>\d{1,2})"
    r"(?:\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2}))?)?"
)
_EXPLICIT_MAINTENANCE = re.compile(
    r"(?:版本(?:更新|开启|上线)|更新|维护|开服)(?:维护)?"
    r"(?:结束)?后|停服维护后"
)
_CONFIRMED_OPEN = re.compile(
    r"现已开启|已经开启|目前已开启|现已开放|已经开放|"
    r"(?<!将)(?:正式开启|正式登场)|同步开展中|现已更新"
)
_PERMANENT_END = re.compile(
    r"长期开放|永久开放|常驻开放|永久加入|永久回归|常驻新增|"
    r"不设结束时间|无结束时间"
)
_POOL_ID = re.compile(
    r"(?:卡池|活动|寻访|招募|采购)(?:ID|编号)\s*[:：]\s*([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_QUOTED_LABEL = re.compile(r"[「【\[]([^」】\]]{1,80})[」】\]]|“([^”]{1,80})”")
_GENERIC_LABELS = {
    "活动内容",
    "活动时间",
    "注意事项",
    "卡池相关",
    "招募时间",
    "更新内容",
    "维护时间",
    "下载方式",
}


def _normalize_date_literals(value: str) -> str:
    value = re.sub(
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        r"\1/\2/\3",
        value,
    )
    return re.sub(
        r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        r"\1/\2",
        value,
    )


def _date_match_datetime(
    match: re.Match[str],
    *,
    published_at: datetime | None,
) -> datetime | None:
    if match.group("hour") is None:
        return None
    published_local = (
        _as_utc(published_at).astimezone(UTC8)
        if published_at is not None
        else datetime.now(tz=UTC8)
    )
    year_text = match.group("year")
    year = int(year_text) if year_text is not None else published_local.year
    month = int(match.group("month"))
    day = int(match.group("day"))
    if year_text is None and month < published_local.month - 6:
        year += 1
    try:
        return datetime(
            year=year,
            month=month,
            day=day,
            hour=int(match.group("hour")),
            minute=int(match.group("minute")),
            second=int(match.group("second") or 0),
            tzinfo=UTC8,
        )
    except ValueError:
        return None


def extract_time_window(
    *,
    title: str,
    text: str,
    published_at: datetime | None,
) -> tuple[StartMode, datetime | None, datetime | None, datetime | None]:
    """Extract the first verified schedule without inventing maintenance times."""

    combined = _normalize_date_literals(f"{title}\n{text}")
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    schedule_lines: list[str] = []
    for index, line in enumerate(lines):
        if re.search(
            r"(?:活动|开放|起止|招募|开展|持续|进行)时间|期间",
            line,
        ):
            schedule_lines.append(line)
            schedule_lines.extend(lines[index + 1 : index + 3])
    schedule_text = (
        "\n".join(dict.fromkeys(schedule_lines)) if schedule_lines else combined
    )
    if _PERMANENT_END.search(combined):
        confirmed = (
            _as_utc(published_at)
            if published_at is not None and _CONFIRMED_OPEN.search(combined)
            else None
        )
        start_mode: StartMode = (
            "after_maintenance" if _EXPLICIT_MAINTENANCE.search(combined) else "tbd"
        )
        return start_mode, None, None, confirmed
    timed_matches = [
        match for match in _DATE_LITERAL.finditer(schedule_text) if match.group("hour")
    ]
    if not timed_matches:
        prefix = schedule_text[:400]
        start_mode = (
            "after_maintenance" if _EXPLICIT_MAINTENANCE.search(prefix) else "tbd"
        )
        confirmed = (
            _as_utc(published_at)
            if published_at is not None and _CONFIRMED_OPEN.search(combined)
            else None
        )
        return start_mode, None, None, confirmed

    first = timed_matches[0]
    context = schedule_text[max(0, first.start() - 100) : first.end() + 160]
    context_matches = [
        match for match in _DATE_LITERAL.finditer(context) if match.group("hour")
    ]
    dates = [
        value
        for match in context_matches
        if (value := _date_match_datetime(match, published_at=published_at)) is not None
    ]
    if not dates:
        return "tbd", None, None, None

    maintenance_prefix = context[: context_matches[0].start()]
    after_maintenance = _EXPLICIT_MAINTENANCE.search(maintenance_prefix) is not None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    if after_maintenance:
        if len(dates) >= 2:
            starts_at = dates[0]
            ends_at = dates[1]
        else:
            ends_at = dates[0]
    elif len(dates) >= 2:
        starts_at = dates[0]
        ends_at = dates[1]
    else:
        starts_at = dates[0]

    if starts_at is not None and ends_at is not None and ends_at < starts_at:
        try:
            ends_at = ends_at.replace(year=ends_at.year + 1)
        except ValueError:
            ends_at = None

    confirmed_at = None
    if _CONFIRMED_OPEN.search(combined):
        confirmed_at = starts_at or published_at
    start_mode = "after_maintenance" if after_maintenance else "scheduled"
    return (
        start_mode,
        _as_utc(starts_at) if starts_at is not None else None,
        _as_utc(ends_at) if ends_at is not None else None,
        _as_utc(confirmed_at) if confirmed_at is not None else None,
    )


def classify_kind(value: str) -> str:
    if any(term in value for term in ("常驻", "常规", "标准")):
        return "standard"
    has_character = any(
        term in value
        for term in ("角色", "干员", "人形", "舰船", "共鸣者", "成员", "✦", "⭐")
    )
    has_weapon = any(term in value for term in ("武器", "装备", "军备", "申领"))
    if has_character and has_weapon:
        return "mixed"
    if has_weapon:
        return "weapon"
    if has_character or any(
        term in value for term in ("招募", "寻访", "唤取", "扭蛋", "建造", "采购")
    ):
        return "character"
    return "banner"


def is_banner_text(value: str) -> bool:
    if any(
        term in value
        for term in (
            "概率公示",
            "标签强制刷新",
            "问题修复公告",
            "延迟开服公告",
        )
    ):
        return False
    return any(
        term in value
        for term in (
            "寻访说明",
            "特许寻访",
            "重构寻访",
            "限定寻访",
            "限时寻访",
            "标准寻访",
            "联合寻访",
            "联动寻访",
            "活动寻访",
            "招募活动",
            "活动招募",
            "复刻招募",
            "限定招募",
            "常驻招募",
            "特设招募",
            "专属招募",
            "专栏招募",
            "角色活动唤取",
            "武器活动唤取",
            "附赠扭蛋",
            "白金扭蛋",
            "扭蛋开展",
            "角色扭蛋",
            "精选扭蛋",
            "新手冲刺扭蛋",
            "限时建造",
            "常驻建造",
            "永久回归常规建造",
            "建造池常驻新增",
            "加入常规建造",
            "永久加入常规建造",
            "定向采购",
            "军备提升",
            "武器申领",
            "干员申领",
            "重构申领",
            "特许申领",
            "概率UP",
        )
    )


def explicit_cancellation(value: str) -> bool:
    return any(
        term in value
        for term in (
            "活动取消",
            "招募取消",
            "寻访取消",
            "卡池取消",
            "取消开放",
            "暂停开放",
            "终止开放",
        )
    )


def explicit_pool_id(value: str) -> str | None:
    match = _POOL_ID.search(value)
    return match.group(1) if match is not None else None


def _heading_label(line: str) -> str | None:
    stripped = line.strip()
    match = re.fullmatch(r"【([^】]+)】", stripped)
    if match is not None:
        label = match.group(1).strip()
        if any(term in label for term in ("招募", "寻访", "采购", "提升")):
            return label
    match = re.fullmatch(r"[◆◇■□]?([^◆◇■□]{1,30}建造)[◆◇■□]?", stripped)
    if match is not None:
        return match.group(1).strip()
    label = stripped.strip("◆◇■□ ")
    if label in {"定向采购", "军备提升"}:
        return label
    return None


def _section_title(
    *,
    heading: str,
    lines: list[str],
) -> str:
    labels: list[str] = []
    subject_line = ""
    for line in lines[1:]:
        if re.match(
            r"^(?:▌|【(?:下载方式|关注我们|特惠礼包|联系方式)】)",
            line,
        ):
            break
        for first, second in _QUOTED_LABEL.findall(line):
            label = first or second
            if (
                label not in _GENERIC_LABELS
                and not re.fullmatch(r"\d+", label)
                and "礼包" not in label
            ):
                labels.append(label)
        if not subject_line and re.match(
            r"^(?:SSR|UR|精英|标准|限定|角色|干员|武器|舰船|人形)",
            line,
        ):
            subject_line = re.split(r"\s+获得.*$", line, maxsplit=1)[0]
    subject = "、".join(dict.fromkeys(labels[:3]))
    if not subject and subject_line:
        subject = subject_line
    return f"{heading}｜{subject}" if subject else heading


def _schedule_prefix(lines: list[str]) -> list[str]:
    selected: list[str] = []
    for index, line in enumerate(lines):
        if re.search(
            r"(?:活动|开放|起止|招募|开展|持续|进行)时间|期间",
            line,
        ):
            selected.append(line)
            selected.extend(lines[index + 1 : index + 3])
    return list(dict.fromkeys(selected))


def split_pool_sections(title: str, body_text: str) -> list[PoolSection]:
    """Split verified multi-pool announcements into independent pool sections."""

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    bullet_indices = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^•\s*", line) and is_banner_text(line)
    ]
    if bullet_indices:
        prefix = _schedule_prefix(lines[: bullet_indices[0]])
        sections: list[PoolSection] = []
        for position, start in enumerate(bullet_indices):
            end = (
                bullet_indices[position + 1]
                if position + 1 < len(bullet_indices)
                else len(lines)
            )
            section_lines = lines[start:end]
            section_title = re.sub(r"^•\s*", "", section_lines[0]).rstrip("！!")
            sections.append(
                PoolSection(
                    title=section_title,
                    text="\n".join((*prefix, *section_lines)),
                )
            )
        return sections

    pool_line_indices = [
        index
        for index, line in enumerate(lines)
        if re.match(
            (
                r"^(?:限时|限定|复刻|特设|专栏|常驻|定向|"
                r"军备|[^：]{1,12}建造池常驻新增)"
            ),
            line,
        )
        and is_banner_text(line)
    ]
    if len(pool_line_indices) >= 2:
        prefix = _schedule_prefix(lines[: pool_line_indices[0]])
        sections = []
        for position, start in enumerate(pool_line_indices):
            end = (
                pool_line_indices[position + 1]
                if position + 1 < len(pool_line_indices)
                else len(lines)
            )
            section_lines = lines[start:end]
            sections.append(
                PoolSection(
                    title=section_lines[0].rstrip("！!"),
                    text="\n".join((*prefix, *section_lines)),
                )
            )
        return sections

    heading_indices = [
        index for index, line in enumerate(lines) if _heading_label(line) is not None
    ]
    if len(heading_indices) >= 2:
        prefix = _schedule_prefix(lines[: heading_indices[0]])
        sections = []
        for position, start in enumerate(heading_indices):
            end = (
                heading_indices[position + 1]
                if position + 1 < len(heading_indices)
                else len(lines)
            )
            section_lines = lines[start:end]
            heading = _heading_label(section_lines[0]) or section_lines[0]
            sections.append(
                PoolSection(
                    title=_section_title(
                        heading=heading,
                        lines=section_lines,
                    ),
                    text="\n".join((*prefix, *section_lines)),
                )
            )
        return sections

    compound = re.split(r"\s*(?:与|＆|&)\s*", title)
    if len(compound) >= 2 and all(is_banner_text(part) for part in compound):
        return [
            PoolSection(title=part, text=body_text) for part in compound if part.strip()
        ]
    return [PoolSection(title=title, text=body_text)]


def _pool_category(value: str) -> str:
    for term in (
        "寻访",
        "申领",
        "招募",
        "唤取",
        "采购",
        "提升",
        "建造",
        "扭蛋",
    ):
        if term in value:
            return term
    return "banner"


def pool_anchor_value(
    *,
    title: str,
    article_id: str | None,
    published_at: datetime | None,
    official_id: str | None,
) -> tuple[str, str | None]:
    """Return an identity stable across article corrections and extensions."""

    if official_id is not None:
        return f"official:{official_id}", official_id
    quoted = [
        first or second
        for first, second in _QUOTED_LABEL.findall(title)
        if (first or second) not in _GENERIC_LABELS
        and not re.fullmatch(r"\d+", first or second)
    ]
    identity = "|".join(dict.fromkeys(quoted)) or re.sub(
        (
            r"即将开启|现已开启|已经开启|概率提升|概率UP|说明|公告|"
            r"调整|延期|延长|更新公告|开放"
        ),
        "",
        title,
    )
    identity = re.sub(
        r"20\d{2}[/年.-]\d{1,2}[/月.-]\d{1,2}日?",
        "",
        identity,
    )
    identity = re.sub(r"\s+", "", identity)
    category = _pool_category(title)
    year = (
        _as_utc(published_at).astimezone(UTC8).year if published_at is not None else 0
    )
    digest = hashlib.sha256(f"{category}|{identity}".encode("utf-8")).hexdigest()[:24]
    return f"{year}:{digest}", official_id


def clean_title(value: object) -> str:
    if not isinstance(value, str):
        return ""
    title = re.sub(r"\s+", " ", unescape(value)).strip()
    title = re.sub(r"\s+-\s+(?:哔哩哔哩|TapTap).*$", "", title)
    return title


def stable_digest(*values: object) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class BaseBannerSource(ABC):
    game: str
    server = "cn"
    source_key: str
    authoritative_url: str

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client
        self._clock = clock

    @asynccontextmanager
    async def _http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(30.0),
        ) as client:
            yield client

    async def _request(
        self,
        client: httpx.AsyncClient,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = await client.request("GET", url, **kwargs)
        except httpx.HTTPError as error:
            raise BannerSourceError(
                f"{self.source_key}: request failed for {url}: {error}"
            ) from error
        if response.status_code >= 400:
            raise BannerSourceError(
                f"{self.source_key}: HTTP {response.status_code} from {url}"
            )
        return response

    def _draft(
        self,
        *,
        title: object,
        body_text: str,
        published_at: datetime | None,
        official_url: str,
        article_id: object | None,
        official_id: object | None = None,
        verified_at: str,
        revision: str | int | None = None,
        cancelled: bool = False,
        replaces: list[str] | None = None,
        related: list[str] | None = None,
        confirmed_open_at_override: datetime | None = None,
        anchor_title: object | None = None,
    ) -> ObservationDraft:
        normalized_title = clean_title(title)
        if not normalized_title:
            raise BannerSourceError(f"{self.source_key}: source item has no title")
        article_value = (
            str(article_id).strip()
            if article_id is not None and str(article_id).strip()
            else None
        )
        official_value = (
            str(official_id).strip()
            if official_id is not None and str(official_id).strip()
            else None
        )
        normalized_anchor = clean_title(anchor_title) or normalized_title
        anchor_key, official_value = pool_anchor_value(
            title=normalized_anchor,
            article_id=article_value,
            published_at=published_at,
            official_id=official_value,
        )
        revision_value = (
            f"source:{revision}"
            if revision is not None
            else stable_digest(
                normalized_title,
                body_text,
                official_url,
                published_at.isoformat() if published_at is not None else None,
            )
        )
        combined = f"{normalized_title}\n{body_text}"
        start_mode, starts_at, ends_at, confirmed_open_at = extract_time_window(
            title=normalized_title,
            text=body_text,
            published_at=published_at,
        )
        if confirmed_open_at_override is not None:
            confirmed_open_at = _as_utc(confirmed_open_at_override)
        if _PERMANENT_END.search(combined):
            end_kind: EndKind = "permanent"
        elif ends_at is not None:
            end_kind = "known"
        else:
            end_kind = "unknown"
        observation: BannerObservation = {
            "game": self.game,
            "server": self.server,
            "title": normalized_title,
            "kind": classify_kind(normalized_title),
            "start_mode": start_mode,
            "starts_at": utc_iso(starts_at) if starts_at is not None else None,
            "ends_at": utc_iso(ends_at) if ends_at is not None else None,
            "end_kind": end_kind,
            "confirmed_open_at": (
                utc_iso(confirmed_open_at) if confirmed_open_at is not None else None
            ),
            "official_url": official_url,
            "verified_at": verified_at,
            "published_at": (
                utc_iso(published_at) if published_at is not None else None
            ),
            "official_id": official_value,
            "article_id": article_value,
            "source_anchor": f"{self.source_key}:{anchor_key}",
            "revision": revision_value,
            "cancelled": bool(cancelled),
            "replaces": list(replaces or ()),
            "related": list(related or ()),
            "publication_order": (
                int(_as_utc(published_at).timestamp())
                if published_at is not None
                else 0
            ),
        }
        return ObservationDraft(
            published_at=_as_utc(published_at) if published_at is not None else None,
            data=observation,
        )

    async def fetch(self) -> list[BannerObservation]:
        now = _as_utc(self._clock())
        verified_at = utc_iso(now)
        async with self._http_client() as client:
            drafts = await self._fetch(client, verified_at)
        cutoff = now - timedelta(days=RECENT_DISCOVERY_DAYS)
        recent = [
            draft
            for draft in drafts
            if draft.published_at is None or draft.published_at >= cutoff
        ]
        return self._finish(recent)

    @staticmethod
    def _finish(drafts: list[ObservationDraft]) -> list[BannerObservation]:
        unique: dict[str, ObservationDraft] = {}
        for draft in drafts:
            anchor = draft.data["source_anchor"]
            current = unique.get(anchor)
            if current is None or (
                draft.published_at is not None
                and (
                    current.published_at is None
                    or draft.published_at > current.published_at
                )
            ):
                unique[anchor] = draft
        ordered = sorted(
            unique.values(),
            key=lambda draft: (
                draft.published_at is None,
                draft.published_at or datetime.min.replace(tzinfo=UTC),
                draft.data["source_anchor"],
            ),
        )
        return [draft.data for draft in ordered]

    @abstractmethod
    async def _fetch(
        self,
        client: httpx.AsyncClient,
        verified_at: str,
    ) -> list[ObservationDraft]: ...
