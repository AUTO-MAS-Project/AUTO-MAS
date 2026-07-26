"""Standalone legacy data upgrade (v1.7 -> v1.11) without legacy Config.

``AppConfig.check_data`` is unreachable in authoritative mode because the
production chain never constructs the legacy configuration graph.  This module
re-implements the same on-disk upgrade steps as pure file transforms so
``main.py`` can run them *before* ``ensure_legacy_original_snapshot`` freezes
the roots, keeping the snapshot's v1.11 fail-closed contract intact.

Ordering contract (main.py):
    1. ``upgrade_legacy_data``      -- this module, idempotent
    2. ``ensure_legacy_original_snapshot``  -- still fail-closed on < v1.11
    3. ``Config.init_config``       -- authoritative Config v2

The version table in ``data/data.db`` is the resume marker: each step commits
its version bump only after its file transforms complete, so a crash mid
upgrade resumes at the failed step on the next start (same semantics as the
legacy upgrader).

The module runs synchronously: it executes before the event loop exists and
before any ``app.core``/``app.models`` import, and must never construct the
legacy ``AppConfig`` graph.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

SNAPSHOT_DIRECTORY_NAME = ".config-v2-original"
AUTHORITATIVE_STORE_DIRECTORY_NAME = ".config-v2-authoritative"

_KNOWN_VERSIONS = ("v1.7", "v1.8", "v1.9", "v1.10", "v1.11")
_TARGET_VERSION = "v1.11"


class LegacyDataUpgradeError(RuntimeError):
    """The legacy data upgrade cannot proceed safely."""


class LegacyDataUpgradeConflictError(LegacyDataUpgradeError):
    """Pre-v1.11 data coexists with an already-frozen original snapshot.

    An immutable original snapshot exists, so an earlier (pre fail-closed)
    build froze pre-upgrade bytes.  Upgrading the live files now would make
    the frozen "original" disagree with the migrated state, so this refuses
    instead of silently desyncing.  Recovery requires an explicit operator
    decision (restore the r6 profile or remove the stale snapshot state).
    """


@dataclass(frozen=True)
class LegacyDataUpgradeResult:
    """Outcome of one ``upgrade_legacy_data`` call."""

    performed: bool
    from_version: str | None
    to_version: str | None
    steps: tuple[str, ...] = field(default_factory=tuple)


def _read_version(database_path: Path) -> str:
    try:
        with closing(sqlite3.connect(database_path)) as database:
            rows = database.execute("SELECT v FROM version").fetchall()
    except sqlite3.DatabaseError as exc:
        raise LegacyDataUpgradeError(
            f"legacy data.db cannot be read for upgrade: {type(exc).__name__}: {exc}"
        ) from exc

    versions = [row[0] for row in rows if len(row) == 1 and isinstance(row[0], str)]
    if len(versions) != 1:
        raise LegacyDataUpgradeError(
            "legacy data.db version table is ambiguous: "
            f"expected one row, found {versions!r}"
        )
    if versions[0] not in _KNOWN_VERSIONS:
        raise LegacyDataUpgradeError(
            f"legacy data.db version {versions[0]!r} is not upgradable; "
            f"supported: {', '.join(_KNOWN_VERSIONS)}"
        )
    return versions[0]


def _bump_version(database_path: Path, old: str, new: str) -> None:
    with closing(sqlite3.connect(database_path)) as database:
        database.execute("DELETE FROM version WHERE v = ?", (old,))
        database.execute("INSERT INTO version VALUES(?)", (new,))
        database.commit()


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyDataUpgradeError(
            f"legacy config file cannot be parsed during upgrade: {path.name}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise LegacyDataUpgradeError(
            f"legacy config file has unexpected shape during upgrade: {path.name}"
        )
    return data


def _dump_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def _upgrade_v1_7_to_v1_8(base_dir: Path) -> None:
    """Mirror legacy v1.7->v1.8: per-queue JSON field aliasing."""

    queue_dir = base_dir / "config" / "QueueConfig"
    if queue_dir.exists():
        for queue_path in sorted(queue_dir.glob("*.json")):
            queue_config = _load_json(queue_path)
            queue_config["QueueSet"]["TimeEnabled"] = queue_config["QueueSet"][
                "Enabled"
            ]
            for i in range(10):
                queue_config["Queue"][f"Script_{i}"] = queue_config["Queue"][
                    f"Member_{i + 1}"
                ]
                queue_config["Time"][f"Enabled_{i}"] = queue_config["Time"][
                    f"TimeEnabled_{i}"
                ]
                queue_config["Time"][f"Set_{i}"] = queue_config["Time"][
                    f"TimeSet_{i}"
                ]
            _dump_json(queue_path, queue_config)


def _upgrade_v1_8_to_v1_9(base_dir: Path) -> None:
    """Mirror legacy v1.8->v1.9: directory layouts -> merged JSON roots.

    Implemented in ``_v1_8_layout.py`` (filled from the serialized
    ``MultipleConfig`` shape); see that module for the format contract.
    """

    from app.configuration.compat._legacy_v1_8_layout import (
        migrate_v1_8_directories,
    )

    migrate_v1_8_directories(base_dir)


# Config.json 白名单: 只有这些 group/field 会被带入升级产物。产物直接被
# fail-closed 的 Config v2 导入链消费, 未经 legacy 归一化的旧键
# (IfSkipMumuSplashAds、Data.Stage 等) 必须在这里裁掉; Data/Update 组是
# 运行时缓存或含加密字段, 丢弃后由 v2 默认值再生。
_CONFIG_BOOL_FIELDS: dict[str, tuple[str, ...]] = {
    "Function": ("IfAllowSleep", "IfSilence", "IfAgreeBilibili", "IfBlockAd"),
    "Start": ("IfSelfStart", "IfMinimizeDirectly"),
    "UI": ("IfShowTray", "IfToTray", "IfHideCloseButton"),
    "Notify": (
        "IfSendStatistic",
        "IfSendSixStar",
        "IfPushPlyer",
        "IfSendMail",
        "IfServerChan",
        "IfKoishiSupport",
    ),
    "Voice": ("Enabled",),
}
_CONFIG_INT_FIELDS: dict[str, tuple[str, ...]] = {
    "Function": ("HistoryRetentionTime",),
}
_CONFIG_STR_FIELDS: dict[str, tuple[str, ...]] = {
    "Notify": (
        "SMTPServerAddress",
        "FromAddress",
        "ToAddress",
        "KoishiServerAddress",
    ),
}


def _sanitize_config_json(base_dir: Path) -> None:
    """按白名单重建 Config.json (含 IfSkipMumuSplashAds -> IfBlockAd 映射)。"""

    config_path = base_dir / "config" / "Config.json"
    if not config_path.exists():
        return
    data = _load_json(config_path)

    sanitized: dict = {}
    for group_name, fields in _CONFIG_BOOL_FIELDS.items():
        source = data.get(group_name)
        if not isinstance(source, dict):
            continue
        group: dict = {}
        for field in fields:
            value = source.get(field)
            if isinstance(value, bool):
                group[field] = value
        for field in _CONFIG_INT_FIELDS.get(group_name, ()):
            value = source.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                group[field] = value
        for field in _CONFIG_STR_FIELDS.get(group_name, ()):
            value = source.get(field)
            if isinstance(value, str):
                group[field] = value
        if group:
            sanitized[group_name] = group

    # legacy v1.9->v1.10 的语义: IfBlockAd 继承旧的 IfSkipMumuSplashAds。
    function_source = data.get("Function")
    if isinstance(function_source, dict) and "IfBlockAd" not in sanitized.get(
        "Function", {}
    ):
        old_value = function_source.get("IfSkipMumuSplashAds")
        if isinstance(old_value, bool):
            sanitized.setdefault("Function", {})["IfBlockAd"] = old_value

    _dump_json(config_path, sanitized)


def _upgrade_v1_9_to_v1_10(base_dir: Path) -> None:
    """Legacy v1.9->v1.10 的等效: Config.json 白名单化 + IfBlockAd 映射。

    Legacy 只是就地追加 IfBlockAd 并重置 stage 缓存, 未知旧键交给随后的
    ``ConfigBase.load`` 归一化丢弃; 本升级器的产物不经过 legacy 归一化,
    所以在这里直接按 v2 可接受形状重建 (缓存类 Data 组丢弃后由默认值再生)。
    """

    _sanitize_config_json(base_dir)


def _upgrade_v1_10_to_v1_11(base_dir: Path) -> None:
    """v1.10->v1.11: structured rename of user ``Task`` keys.

    The legacy upgrader called ``str.replace`` without assigning the result,
    so its announced renames (IfWakeUp->IfStartUp etc.) never touched disk.
    Legacy ``ConfigBase.load`` then silently dropped the unknown old keys and
    reset those toggles to defaults on first run.  This upgrader's output is
    consumed directly by the fail-closed Config v2 import instead, so the old
    keys must not survive; applying the intended rename both satisfies v2 and
    preserves the user's toggle values (strictly better than legacy's drop).

    ``Config.json`` is also re-sanitized here: profiles entering directly at
    v1.10 kept era keys (e.g. ``IfSkipMumuSplashAds``) that legacy retained
    on disk and only dropped at load time.  Other roots are carried
    best-effort; anything the v2 import cannot accept stays fail-closed with
    a clear error.
    """

    _sanitize_config_json(base_dir)

    from app.configuration.compat._legacy_v1_8_layout import _TASK_FIELD_ALIASES

    script_path = base_dir / "config" / "ScriptConfig.json"
    if not script_path.exists():
        return
    root = _load_json(script_path)
    instances = root.get("instances")
    if not isinstance(instances, list):
        return

    changed = False
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        payload = root.get(instance.get("uid"))
        if not isinstance(payload, dict):
            continue
        sub_configs = payload.get("SubConfigsInfo")
        if not isinstance(sub_configs, dict):
            continue
        user_data = sub_configs.get("UserData")
        if not isinstance(user_data, dict):
            continue
        for user_instance in user_data.get("instances") or []:
            if not isinstance(user_instance, dict):
                continue
            user_payload = user_data.get(user_instance.get("uid"))
            if not isinstance(user_payload, dict):
                continue
            task = user_payload.get("Task")
            if not isinstance(task, dict):
                continue
            renamed: dict = {}
            for name, value in task.items():
                new_name = _TASK_FIELD_ALIASES.get(name)
                if new_name is not None and new_name not in renamed:
                    renamed[new_name] = value
            if renamed != task:
                user_payload["Task"] = renamed
                changed = True

    if changed:
        _dump_json(script_path, root)


_UPGRADE_STEPS: tuple[tuple[str, str, object], ...] = (
    ("v1.7", "v1.8", _upgrade_v1_7_to_v1_8),
    ("v1.8", "v1.9", _upgrade_v1_8_to_v1_9),
    ("v1.9", "v1.10", _upgrade_v1_9_to_v1_10),
    ("v1.10", "v1.11", _upgrade_v1_10_to_v1_11),
)


def upgrade_legacy_data(base_dir: Path) -> LegacyDataUpgradeResult:
    """Idempotently bring pre-v1.11 legacy data to v1.11.

    Args:
        base_dir: Installation root (the directory containing ``config`` and
            ``data``); the legacy upgrader assumed ``Path.cwd()``.

    Returns:
        What was done; ``performed`` is False when no upgrade was needed.

    Raises:
        LegacyDataUpgradeConflictError: Pre-v1.11 data found but an original
            snapshot generation is already frozen (pre fail-closed build).
        LegacyDataUpgradeError: The version table or a legacy file is not in
            an upgradable state.  Nothing is partially hidden: completed steps
            have committed their version bump and will not re-run.
    """

    base_dir = Path(base_dir)
    database_path = base_dir / "data" / "data.db"
    if not database_path.exists():
        # Fresh profile: nothing legacy to upgrade.  Snapshot layer treats a
        # missing data.db as "no legacy data" as well.
        return LegacyDataUpgradeResult(
            performed=False, from_version=None, to_version=None
        )

    version = _read_version(database_path)
    if version == _TARGET_VERSION:
        return LegacyDataUpgradeResult(
            performed=False, from_version=version, to_version=version
        )

    snapshot_current = (
        base_dir / "config" / SNAPSHOT_DIRECTORY_NAME / "CURRENT"
    )
    if snapshot_current.exists():
        raise LegacyDataUpgradeConflictError(
            "pre-v1.11 legacy data found, but an immutable original snapshot "
            f"already exists ({snapshot_current}); an earlier build froze "
            "pre-upgrade bytes.  Refusing to upgrade to avoid desyncing the "
            "frozen original.  Restore the r6 profile or remove the stale "
            "Config v2 state directories after backing them up."
        )

    steps: list[str] = []
    from_version = version
    for old, new, transform in _UPGRADE_STEPS:
        if version != old:
            continue
        transform(base_dir)  # type: ignore[operator]
        _bump_version(database_path, old, new)
        steps.append(f"{old}->{new}")
        version = new

    if version != _TARGET_VERSION:
        raise LegacyDataUpgradeError(
            f"legacy data upgrade stopped at {version}; target {_TARGET_VERSION}"
        )

    return LegacyDataUpgradeResult(
        performed=True,
        from_version=from_version,
        to_version=version,
        steps=tuple(steps),
    )
