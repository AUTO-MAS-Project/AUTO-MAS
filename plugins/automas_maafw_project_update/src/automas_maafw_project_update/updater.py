from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import aiofiles
import httpx
from automas_maafw_interface.models import MaaFWInterface
from packaging import version


UPDATE_WORK_DIR = ".mas-update"
DOWNLOAD_FILE_NAME = "download.zip"
DOWNLOAD_TEMP_NAME = "download.tmp"
DOWNLOAD_RETRY_TIMES = 3
HTTP_HEADERS = {"User-Agent": "AutoMasGui"}

MIRROR_ERROR_INFO = {
    1001: "MirrorChyan URL parameters are invalid",
    7001: "MirrorChyan CDK is expired",
    7002: "MirrorChyan CDK is invalid",
    7003: "MirrorChyan CDK download limit reached today",
    7004: "MirrorChyan CDK type does not match the resource",
    7005: "MirrorChyan CDK has been banned",
    8001: "MirrorChyan resource is not available for this platform",
    8002: "MirrorChyan OS parameter is invalid",
    8003: "MirrorChyan arch parameter is invalid",
    8004: "MirrorChyan channel parameter is invalid",
    1: "MirrorChyan returned unknown error",
}


@dataclass
class MaaFWUpdateProviderInfo:
    name: str
    label: str
    description: str = ""


@dataclass
class MaaFWProjectUpdateCandidate:
    source: str
    version: str
    download_url: str | None = None
    sha256: str | None = None


@dataclass
class MaaFWProjectUpdateResult:
    checked: bool
    updated: bool
    current_version: str
    latest_version: str | None = None
    source: str | None = None
    message: str = ""


class MaaFWProjectUpdateError(RuntimeError):
    """Raised when a MaaFW project package cannot be checked or applied."""


def list_update_providers() -> list[MaaFWUpdateProviderInfo]:
    return [
        MaaFWUpdateProviderInfo(
            name="mirrorchyan",
            label="MirrorChyan",
            description="Use MirrorChyan resource latest API.",
        ),
        MaaFWUpdateProviderInfo(
            name="github_release",
            label="GitHub Release",
            description="Use GitHub Releases and zip assets.",
        ),
    ]


async def update_maafw_project_if_needed(
    project_path: Path,
    interface_model: MaaFWInterface,
    *,
    mirror_cdk: str = "",
    channel: str = "stable",
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
    source_config: dict[str, Any] | None = None,
) -> MaaFWProjectUpdateResult:
    send_update_log = send_log or (lambda _: None)
    current_version = interface_model.version or ""
    update_channel = channel or "stable"

    if not current_version:
        message = "interface does not declare version, skip MaaFW project update"
        send_update_log(message)
        return MaaFWProjectUpdateResult(
            checked=False,
            updated=False,
            current_version=current_version,
            message=message,
        )

    send_update_log("start checking MaaFW project update")
    send_update_log(f"current version: {current_version}")
    send_update_log(f"update channel: {update_channel}")

    merged_source_config = dict(source_config or {})
    merged_source_config.setdefault("mirror_cdk", mirror_cdk)
    merged_source_config.setdefault("channel", update_channel)
    candidate = await check_maafw_project_update(
        interface_model,
        current_version=current_version,
        source_config=merged_source_config,
        proxy=proxy,
        send_log=send_update_log,
    )

    if candidate is None:
        message = f"MaaFW project is up to date: {current_version}"
        send_update_log(message)
        return MaaFWProjectUpdateResult(
            checked=True,
            updated=False,
            current_version=current_version,
            message=message,
        )

    send_update_log(
        f"found MaaFW project update: {current_version} -> {candidate.version} ({candidate.source})"
    )
    await apply_maafw_project_update(
        project_path.resolve(),
        candidate,
        proxy=proxy,
        send_log=send_update_log,
    )

    message = f"MaaFW project update applied: {candidate.version}"
    send_update_log(message)
    return MaaFWProjectUpdateResult(
        checked=True,
        updated=True,
        current_version=current_version,
        latest_version=candidate.version,
        source=candidate.source,
        message=message,
    )


async def check_maafw_project_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str | None = None,
    source_config: dict[str, Any] | None = None,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
) -> MaaFWProjectUpdateCandidate | None:
    config = dict(source_config or {})
    provider = str(config.get("source") or "").strip().lower()
    if not provider:
        provider = "mirrorchyan" if interface_model.mirrorchyan_rid else "github_release"

    current = current_version if current_version is not None else (interface_model.version or "")
    send_update_log = send_log or (lambda _: None)

    if provider == "mirrorchyan":
        if not interface_model.mirrorchyan_rid:
            send_update_log("MirrorChyan RID is not configured, skip update")
            return None
        send_update_log(f"MirrorChyan RID: {interface_model.mirrorchyan_rid}")
        if interface_model.mirrorchyan_multiplatform:
            send_update_log("MirrorChyan platform: win/x64")
        return await _check_mirrorchyan_update(
            interface_model,
            current_version=current,
            mirror_cdk=str(config.get("mirror_cdk") or config.get("cdk") or ""),
            channel=str(config.get("channel") or "stable"),
            proxy=proxy,
        )

    if provider == "github_release":
        return await _check_github_release_update(
            interface_model,
            current_version=current,
            source_config=config,
            proxy=proxy,
        )

    raise MaaFWProjectUpdateError(f"unsupported MaaFW project update provider: {provider}")


async def apply_maafw_project_update(
    project_path: Path,
    candidate: MaaFWProjectUpdateCandidate,
    *,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
) -> None:
    send_update_log = send_log or (lambda _: None)
    if not candidate.download_url:
        raise MaaFWProjectUpdateError("update provider did not return a download URL")

    package_path = await _download_update_package(
        project_path.resolve(),
        candidate.download_url,
        expected_sha256=candidate.sha256,
        proxy=proxy,
        send_log=send_update_log,
    )
    await _apply_update_package(project_path.resolve(), package_path, send_update_log)


async def _check_mirrorchyan_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str,
    mirror_cdk: str,
    channel: str,
    proxy: httpx.Proxy | None,
) -> MaaFWProjectUpdateCandidate | None:
    rid = interface_model.mirrorchyan_rid
    if not rid:
        return None

    params: dict[str, str] = {
        "user_agent": "AutoMasGui",
        "current_version": current_version,
        "cdk": mirror_cdk or "",
        "channel": channel or "stable",
    }
    if interface_model.mirrorchyan_multiplatform:
        params["os"] = "win"
        params["arch"] = "x64"

    url = f"https://mirrorchyan.com/api/resources/{rid}/latest"
    try:
        async with httpx.AsyncClient(proxy=proxy, follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url, params=params, headers=HTTP_HEADERS)
    except httpx.HTTPError as exc:
        raise MaaFWProjectUpdateError(
            f"MirrorChyan update check failed: {_sanitize_log_message(str(exc))}"
        ) from None

    result = _load_response_json(response)
    if response.status_code != 200 or result.get("code", 0) != 0:
        error_code = result.get("code")
        if error_code in MIRROR_ERROR_INFO:
            raise MaaFWProjectUpdateError(MIRROR_ERROR_INFO[error_code])
        raise MaaFWProjectUpdateError(f"MirrorChyan returned HTTP {response.status_code}")

    data = result.get("data")
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("MirrorChyan did not return version data")

    latest_version = str(
        data.get("version_name") or data.get("version") or data.get("name") or ""
    ).strip()
    if not latest_version:
        raise MaaFWProjectUpdateError("MirrorChyan did not return version")
    if not _is_remote_newer(latest_version, current_version):
        return None

    return MaaFWProjectUpdateCandidate(
        source="mirrorchyan",
        version=latest_version,
        download_url=str(data.get("url") or "").strip() or None,
        sha256=str(data.get("sha256") or "").strip() or None,
    )


async def _check_github_release_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str,
    source_config: dict[str, Any],
    proxy: httpx.Proxy | None,
) -> MaaFWProjectUpdateCandidate | None:
    repo = _normalize_github_repo(str(source_config.get("repo") or interface_model.github or ""))
    if not repo:
        return None

    tag = str(source_config.get("tag") or "").strip()
    api_url = (
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        if tag
        else f"https://api.github.com/repos/{repo}/releases/latest"
    )
    token = str(source_config.get("token") or "").strip()
    headers = dict(HTTP_HEADERS)
    headers["Accept"] = "application/vnd.github+json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(proxy=proxy, follow_redirects=True, timeout=30.0) as client:
        response = await client.get(api_url, headers=headers)

    if response.status_code == 404:
        return None
    data = _load_response_json(response)
    if response.status_code >= 400:
        message = str(data.get("message") or "").strip()
        raise MaaFWProjectUpdateError(
            f"GitHub release check failed: HTTP {response.status_code} {message}"
        )

    latest_version = str(data.get("tag_name") or data.get("name") or "").strip()
    if not latest_version:
        raise MaaFWProjectUpdateError("GitHub release did not return version")
    if not _is_remote_newer(latest_version, current_version):
        return None

    asset_pattern = str(source_config.get("asset_pattern") or r"\.zip$").strip()
    download_url = _select_github_release_asset(data, asset_pattern)
    if not download_url:
        download_url = str(data.get("zipball_url") or "").strip() or None

    return MaaFWProjectUpdateCandidate(
        source="github_release",
        version=latest_version,
        download_url=download_url,
        sha256=str(source_config.get("sha256") or "").strip() or None,
    )


async def _download_update_package(
    project_path: Path,
    download_url: str,
    *,
    expected_sha256: str | None = None,
    proxy: httpx.Proxy | None,
    send_log: Callable[[str], None],
) -> Path:
    update_dir = project_path / UPDATE_WORK_DIR
    update_dir.mkdir(parents=True, exist_ok=True)

    temp_path = update_dir / DOWNLOAD_TEMP_NAME
    package_path = update_dir / DOWNLOAD_FILE_NAME
    _remove_path(temp_path)
    _remove_path(package_path)

    send_log(f"start downloading MaaFW update package: {_sanitize_log_message(download_url)}")
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_RETRY_TIMES + 1):
        _remove_path(temp_path)
        try:
            await _stream_update_package(
                temp_path,
                download_url,
                proxy=proxy,
            )
            _ensure_downloaded_zip(temp_path)
            _ensure_expected_sha256(temp_path, expected_sha256)
            temp_path.replace(package_path)
            send_log(f"MaaFW update package downloaded: {package_path.stat().st_size} bytes")
            return package_path
        except Exception as exc:
            last_error = exc
            _remove_path(temp_path)
            if attempt >= DOWNLOAD_RETRY_TIMES:
                break
            send_log(
                "download failed, retrying "
                f"({attempt}/{DOWNLOAD_RETRY_TIMES}): {_sanitize_log_message(str(exc))}"
            )
            await asyncio.sleep(1)

    if isinstance(last_error, MaaFWProjectUpdateError):
        raise MaaFWProjectUpdateError(_sanitize_log_message(str(last_error))) from None
    raise MaaFWProjectUpdateError(
        "download MaaFW update package failed: "
        f"{_sanitize_log_message(str(last_error))}"
    ) from None


async def _stream_update_package(
    temp_path: Path,
    download_url: str,
    *,
    proxy: httpx.Proxy | None,
) -> None:
    async with httpx.AsyncClient(proxy=proxy, follow_redirects=True, timeout=30.0) as client:
        async with client.stream("GET", download_url, headers=HTTP_HEADERS) as response:
            if response.status_code not in (200, 206):
                error_hint = await _read_download_error_hint(response)
                if error_hint:
                    raise MaaFWProjectUpdateError(
                        f"download update package failed: HTTP {response.status_code}, {error_hint}"
                    )
                raise MaaFWProjectUpdateError(
                    f"download update package failed: HTTP {response.status_code}"
                )

            async with aiofiles.open(temp_path, "wb") as file:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if chunk:
                        await file.write(chunk)


async def _read_download_error_hint(response: httpx.Response) -> str:
    try:
        content = await response.aread()
    except Exception:
        return ""
    return _build_download_error_hint(content)


def _ensure_downloaded_zip(package_path: Path) -> None:
    if not package_path.exists() or package_path.stat().st_size == 0:
        raise MaaFWProjectUpdateError("update source returned an empty file")
    if zipfile.is_zipfile(package_path):
        return

    error_hint = _read_local_download_error_hint(package_path)
    if error_hint:
        raise MaaFWProjectUpdateError(f"download update package failed: {error_hint}")
    raise MaaFWProjectUpdateError("update source did not return a valid zip file")


def _ensure_expected_sha256(package_path: Path, expected_sha256: str | None) -> None:
    expected = (expected_sha256 or "").strip().lower()
    if not expected:
        return

    actual = _calculate_sha256(package_path)
    if actual == expected:
        return

    raise MaaFWProjectUpdateError(
        f"sha256 mismatch, expected {expected[:12]}..., actual {actual[:12]}..."
    )


def _calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_local_download_error_hint(path: Path) -> str:
    try:
        content = path.read_bytes()[:4096]
    except Exception:
        return ""
    return _build_download_error_hint(content)


def _build_download_error_hint(content: bytes) -> str:
    if not content:
        return "update source returned empty response"

    text = _decode_download_error_text(content)
    if not text:
        return ""

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if text.lstrip().startswith("<"):
            return "update source returned an HTML page instead of zip"
        return ""

    if not isinstance(data, dict):
        return ""

    error_code = data.get("code")
    if error_code in MIRROR_ERROR_INFO:
        return MIRROR_ERROR_INFO[error_code]

    message = str(data.get("msg") or data.get("message") or "").strip()
    if not message:
        return ""
    return f"update source returned error: {_sanitize_log_message(message)}"


def _decode_download_error_text(content: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return ""


async def _apply_update_package(
    project_path: Path,
    package_path: Path,
    send_log: Callable[[str], None],
) -> None:
    update_dir = project_path / UPDATE_WORK_DIR
    extract_dir = update_dir / "extract"
    backup_dir = update_dir / "backup"

    _remove_path(extract_dir)
    _remove_path(backup_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        _safe_extract_zip(package_path, extract_dir)
        package_root = _find_package_root(extract_dir)
        changes_path = _find_changes_file(package_root, extract_dir)

        if changes_path is None:
            send_log("applying full MaaFW update package")
            _apply_full_package(project_path, package_root, backup_dir)
        else:
            send_log("applying incremental MaaFW update package")
            _apply_incremental_package(
                project_path,
                package_root,
                changes_path,
                backup_dir,
                extract_dir,
            )
        send_log("MaaFW update package applied")
    finally:
        _remove_path(extract_dir)
        _remove_path(package_path)


def _apply_full_package(project_path: Path, package_root: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    touched_paths: set[Path] = set()

    try:
        for child in package_root.iterdir():
            if child.name in {UPDATE_WORK_DIR, "changes.json"}:
                continue

            target = _resolve_project_relative_path(project_path, child.name)
            touched_paths.add(target)
            _backup_target(project_path, target, backup_dir)
            _copy_path(child, target)
    except Exception:
        _restore_incremental_backup(project_path, backup_dir, touched_paths)
        raise
    else:
        _remove_path(backup_dir)


def _apply_incremental_package(
    project_path: Path,
    package_root: Path,
    changes_path: Path,
    backup_dir: Path,
    extract_dir: Path,
) -> None:
    changes = _load_changes(changes_path)
    payload_root = _resolve_payload_root(
        package_root,
        changes_path,
        changes,
        extract_dir,
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    touched_paths: set[Path] = set()

    try:
        for raw_path in _iter_deleted_paths(changes):
            target = _resolve_project_relative_path(project_path, raw_path)
            touched_paths.add(target)
            _backup_target(project_path, target, backup_dir)
            _remove_path(target)

        for source in payload_root.rglob("*"):
            if source.is_dir():
                continue
            if source == changes_path:
                continue
            if source.name == "changes.json":
                continue

            relative_path = source.relative_to(payload_root)
            target = _resolve_project_relative_path(project_path, relative_path.as_posix())
            touched_paths.add(target)
            _backup_target(project_path, target, backup_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    except Exception:
        _restore_incremental_backup(project_path, backup_dir, touched_paths)
        raise
    else:
        _remove_path(backup_dir)


def _load_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise MaaFWProjectUpdateError("update source did not return JSON") from exc
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("update source returned invalid JSON shape")
    return data


def _is_remote_newer(remote_version: str, current_version: str) -> bool:
    remote = remote_version.strip()
    current = current_version.strip()
    if not remote:
        return False
    if not current:
        return True

    try:
        return version.parse(_normalize_version(remote)) > version.parse(
            _normalize_version(current)
        )
    except version.InvalidVersion:
        return remote != current


def _normalize_version(raw_version: str) -> str:
    return raw_version.strip().lstrip("vV")


def _safe_extract_zip(package_path: Path, extract_dir: Path) -> None:
    try:
        with zipfile.ZipFile(package_path, "r") as zip_ref:
            for member in zip_ref.infolist():
                target = (extract_dir / member.filename).resolve()
                if not _is_within_path(target, extract_dir):
                    raise MaaFWProjectUpdateError(
                        f"update package contains unsafe path: {member.filename}"
                    )
            zip_ref.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise MaaFWProjectUpdateError("update package is not a valid zip file") from exc


def _find_package_root(extract_dir: Path) -> Path:
    for candidate in [extract_dir, *_direct_child_dirs(extract_dir)]:
        if _has_interface_file(candidate):
            return candidate

    for interface_file in extract_dir.rglob("interface.json*"):
        if interface_file.name in {"interface.json", "interface.jsonc"}:
            return interface_file.parent

    raise MaaFWProjectUpdateError("interface.json was not found in update package")


def _find_changes_file(package_root: Path, extract_dir: Path) -> Path | None:
    for candidate in (package_root / "changes.json", extract_dir / "changes.json"):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _has_interface_file(path: Path) -> bool:
    return (path / "interface.json").is_file() or (path / "interface.jsonc").is_file()


def _direct_child_dirs(path: Path) -> list[Path]:
    return [child for child in path.iterdir() if child.is_dir()]


def _load_changes(changes_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(changes_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MaaFWProjectUpdateError(f"cannot parse changes.json: {exc}") from exc
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("changes.json must be a JSON object")
    return data


def _resolve_payload_root(
    package_root: Path,
    changes_path: Path,
    changes: dict[str, Any],
    extract_dir: Path,
) -> Path:
    for key in ("payload", "files", "root"):
        raw_path = changes.get(key)
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        candidate = (changes_path.parent / raw_path).resolve()
        if not candidate.exists() or not candidate.is_dir():
            continue
        if not _is_within_path(candidate, extract_dir):
            raise MaaFWProjectUpdateError(f"changes.json {key} path is unsafe: {raw_path}")
        return candidate

    for folder_name in ("payload", "files"):
        candidate = package_root / folder_name
        if candidate.exists() and candidate.is_dir():
            return candidate

    return package_root


def _iter_deleted_paths(changes: dict[str, Any]) -> list[str]:
    deleted_paths: list[str] = []
    for key in (
        "delete",
        "deleted",
        "deleted_dir",
        "remove",
        "removed",
        "unlink",
        "unlinks",
    ):
        value = changes.get(key)
        if isinstance(value, list):
            deleted_paths.extend(item for item in value if isinstance(item, str))
        elif isinstance(value, dict):
            deleted_paths.extend(item for item in value if isinstance(item, str))
    return deleted_paths


def _backup_target(project_path: Path, target: Path, backup_dir: Path) -> None:
    if not target.exists():
        return

    relative_path = target.relative_to(project_path)
    backup_path = backup_dir / relative_path
    if backup_path.exists():
        return

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(backup_path))


def _restore_incremental_backup(
    project_path: Path,
    backup_dir: Path,
    touched_paths: set[Path],
) -> None:
    try:
        for target in sorted(touched_paths, key=lambda item: len(item.parts), reverse=True):
            _remove_path(target)

        if not backup_dir.exists():
            return
        for backup_child in sorted(backup_dir.rglob("*"), key=lambda item: len(item.parts)):
            if backup_child.is_dir():
                continue
            relative_path = backup_child.relative_to(backup_dir)
            target = project_path / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(backup_child), str(target))
    finally:
        _remove_path(backup_dir)


def _resolve_project_relative_path(project_path: Path, raw_path: str) -> Path:
    normalized = raw_path.strip().replace("\\", "/")
    if not normalized:
        raise MaaFWProjectUpdateError("update package contains empty path")

    candidate = Path(normalized)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise MaaFWProjectUpdateError(f"update package contains absolute path: {raw_path}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise MaaFWProjectUpdateError(f"update package contains invalid path: {raw_path}")
    if candidate.parts[0] == UPDATE_WORK_DIR:
        raise MaaFWProjectUpdateError(f"update package cannot write to {UPDATE_WORK_DIR}: {raw_path}")

    target = (project_path / candidate).resolve()
    if not _is_within_path(target, project_path):
        raise MaaFWProjectUpdateError(f"update package path escapes project root: {raw_path}")
    return target


def _copy_path(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _is_within_path(path: Path, base_dir: Path) -> bool:
    try:
        path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def _normalize_github_repo(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    value = value.removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.strip("/")
    parts = value.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return ""
    return f"{parts[0]}/{parts[1]}"


def _select_github_release_asset(data: dict[str, Any], asset_pattern: str) -> str | None:
    assets = data.get("assets")
    if not isinstance(assets, list):
        return None

    try:
        pattern = re.compile(asset_pattern)
    except re.error as exc:
        raise MaaFWProjectUpdateError(f"invalid GitHub asset pattern: {exc}") from exc

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if not pattern.search(name):
            continue
        url = str(asset.get("browser_download_url") or "").strip()
        if url:
            return url
    return None


def _sanitize_log_message(message: str) -> str:
    sensitive_patterns = [
        (r"(cdk=)[^&\s]+", r"\1***"),
        (r"(password=)[^&\s]+", r"\1***"),
        (r"(token=)[^&\s]+", r"\1***"),
        (r"(api_key=)[^&\s]+", r"\1***"),
        (r"(secret=)[^&\s]+", r"\1***"),
    ]
    sanitized_message = message
    for pattern, replacement in sensitive_patterns:
        sanitized_message = re.sub(
            pattern,
            replacement,
            sanitized_message,
            flags=re.IGNORECASE,
        )
    return sanitized_message
