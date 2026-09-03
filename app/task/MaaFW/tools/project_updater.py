#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright (C) 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import asyncio
import hashlib
import ipaddress
import json
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse, urlsplit

import aiofiles
import httpx
from packaging import version

from app.utils import get_logger
from app.utils.constants import MIRROR_ERROR_INFO
from app.utils.security import sanitize_log_message

from .async_operation import run_blocking_to_completion
from .core.automas_maafw_interface.models import MaaFWInterface
from .core.automas_maafw_project_update.updater import (
    detect_maafw_project_shell_hint,
)

logger = get_logger("MaaFW 项目更新")

UPDATE_WORK_DIR = ".mas-update"
DOWNLOAD_FILE_NAME = "download.zip"
DOWNLOAD_TEMP_NAME = "download.tmp"
DOWNLOAD_MAX_BYTES = 4 * 1024 * 1024 * 1024
DOWNLOAD_REDIRECT_LIMIT = 5
ZIP_MAX_ENTRIES = 100_000
ZIP_MAX_EXPANDED_BYTES = 8 * 1024 * 1024 * 1024


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

    def __init__(self, message: str, *, unsafe_to_continue: bool = False) -> None:
        super().__init__(message)
        self.unsafe_to_continue = unsafe_to_continue


async def update_maafw_project_if_needed(
    project_path: Path,
    interface_model: MaaFWInterface,
    *,
    source: str = "MirrorChyan",
    mirror_cdk: str = "",
    channel: str = "stable",
    github_repo: str = "",
    github_tag: str = "",
    github_asset_pattern: str = "",
    proxy: httpx.Proxy | None,
    send_log: Callable[[str], None] | None = None,
) -> MaaFWProjectUpdateResult:
    """Check and apply MaaFW project updates before MaaFW resources are loaded."""

    resolved_project_path = project_path.resolve()
    send_update_log = send_log or (lambda _: None)
    current_version = interface_model.version or ""

    if not current_version:
        message = "interface 未声明版本，跳过 MaaFW 项目更新"
        send_update_log(message)
        return MaaFWProjectUpdateResult(
            checked=False,
            updated=False,
            current_version=current_version,
            message=message,
        )

    candidate: MaaFWProjectUpdateCandidate | None = None
    update_source = source if source in {"MirrorChyan", "GitHub"} else "MirrorChyan"

    if update_source == "MirrorChyan":
        if interface_model.mirrorchyan_rid:
            try:
                candidate = await _check_mirrorchyan_update(
                    interface_model,
                    current_version=current_version,
                    mirror_cdk=mirror_cdk,
                    channel=channel,
                    proxy=proxy,
                )
            except Exception as exc:
                send_update_log(f"MirrorChyan 更新检查失败: {exc}")

        if candidate is None and (github_repo or interface_model.github):
            send_update_log("MirrorChyan 更新源不可用，尝试 GitHub 公共 release")
            try:
                candidate = await _check_github_update(
                    interface_model,
                    current_version=current_version,
                    channel=channel,
                    github_repo=github_repo,
                    github_tag=github_tag,
                    github_asset_pattern=github_asset_pattern,
                    proxy=proxy,
                )
            except Exception as exc:
                send_update_log(f"GitHub 更新检查失败: {exc}")

    if update_source == "GitHub" and (github_repo or interface_model.github):
        try:
            candidate = await _check_github_update(
                interface_model,
                current_version=current_version,
                channel=channel,
                github_repo=github_repo,
                github_tag=github_tag,
                github_asset_pattern=github_asset_pattern,
                proxy=proxy,
            )
        except Exception as exc:
            send_update_log(f"GitHub 更新检查失败: {exc}")

    if candidate is None:
        message = "MaaFW 项目已是最新或未配置可用更新源"
        send_update_log(message)
        return MaaFWProjectUpdateResult(
            checked=True,
            updated=False,
            current_version=current_version,
            message=message,
        )

    send_update_log(
        f"发现 MaaFW 项目更新: {current_version} -> {candidate.version} ({candidate.source})"
    )
    download_url = candidate.download_url
    if (
        not download_url
        and candidate.source == "MirrorChyan"
        and (github_repo or interface_model.github)
    ):
        send_update_log("MirrorChyan 未返回下载链接，尝试从 GitHub release 下载")
        download_url = await _find_github_release_asset(
            interface_model,
            target_version=candidate.version,
            channel=channel,
            github_repo=github_repo,
            github_asset_pattern=github_asset_pattern,
            proxy=proxy,
        )

    if not download_url:
        raise MaaFWProjectUpdateError(f"{candidate.source} 未返回可用下载链接")

    package_path = await _download_update_package(
        resolved_project_path,
        download_url,
        expected_sha256=candidate.sha256,
        proxy=proxy,
        send_log=send_update_log,
    )
    await run_blocking_to_completion(
        _apply_update_package, resolved_project_path, package_path, send_update_log
    )

    message = f"MaaFW 项目更新完成: {candidate.version}"
    send_update_log(message)
    return MaaFWProjectUpdateResult(
        checked=True,
        updated=True,
        current_version=current_version,
        latest_version=candidate.version,
        source=candidate.source,
        message=message,
    )


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
    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=False, timeout=30.0
    ) as client:
        response = await client.get(url, params=params)

    result = _load_response_json(response)
    if response.status_code != 200 or result.get("code", 0) != 0:
        error_code = result.get("code")
        if error_code in MIRROR_ERROR_INFO:
            raise MaaFWProjectUpdateError(MIRROR_ERROR_INFO[error_code])
        raise MaaFWProjectUpdateError(
            f"MirrorChyan 返回异常: HTTP {response.status_code}"
        )

    data = result.get("data")
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("MirrorChyan 未返回版本数据")

    latest_version = str(
        data.get("version_name") or data.get("version") or data.get("name") or ""
    ).strip()
    if not latest_version:
        raise MaaFWProjectUpdateError("MirrorChyan 未返回版本号")
    if not _is_remote_newer(latest_version, current_version):
        return None

    return MaaFWProjectUpdateCandidate(
        source="MirrorChyan",
        version=latest_version,
        download_url=str(data.get("url") or "").strip() or None,
        sha256=str(data.get("sha256") or "").strip() or None,
    )


async def _check_github_update(
    interface_model: MaaFWInterface,
    *,
    current_version: str,
    channel: str,
    github_repo: str = "",
    github_tag: str = "",
    github_asset_pattern: str = "",
    proxy: httpx.Proxy | None,
) -> MaaFWProjectUpdateCandidate | None:
    releases = await _fetch_github_releases(
        interface_model, github_repo=github_repo, proxy=proxy
    )
    release = _select_github_release(releases, channel=channel, tag=github_tag)
    if release is None:
        return None

    latest_version = str(release.get("tag_name") or release.get("name") or "").strip()
    if not latest_version:
        raise MaaFWProjectUpdateError("GitHub release 未返回版本号")
    if not _is_remote_newer(latest_version, current_version):
        return None

    asset = _select_github_asset(
        release.get("assets"),
        interface_model.name,
        pattern=github_asset_pattern,
    )
    if asset is None:
        raise MaaFWProjectUpdateError("GitHub release 未找到可下载的 zip 资源包")

    return MaaFWProjectUpdateCandidate(
        source="GitHub",
        version=latest_version,
        download_url=asset,
    )


async def _fetch_github_releases(
    interface_model: MaaFWInterface,
    *,
    github_repo: str = "",
    proxy: httpx.Proxy | None,
) -> list[dict[str, Any]]:
    repo = _parse_github_repo(github_repo or interface_model.github or "")
    if repo is None:
        raise MaaFWProjectUpdateError("GitHub 地址格式不支持")

    owner, name = repo
    url = f"https://api.github.com/repos/{owner}/{name}/releases"
    headers = {"User-Agent": "AutoMasGui"}
    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=False, timeout=30.0
    ) as client:
        response = await client.get(url, headers=headers)

    if response.status_code != 200:
        raise MaaFWProjectUpdateError(f"GitHub 返回异常: HTTP {response.status_code}")

    return _load_response_json_list(response)


async def _find_github_release_asset(
    interface_model: MaaFWInterface,
    *,
    target_version: str,
    channel: str,
    github_repo: str = "",
    github_asset_pattern: str = "",
    proxy: httpx.Proxy | None,
) -> str:
    releases = await _fetch_github_releases(
        interface_model, github_repo=github_repo, proxy=proxy
    )
    wants_prerelease = channel == "beta"
    normalized_target = _normalize_version(target_version)
    for release in releases:
        if bool(release.get("draft")):
            continue
        if bool(release.get("prerelease")) != wants_prerelease:
            continue
        release_version = str(release.get("tag_name") or release.get("name") or "")
        if _normalize_version(release_version) != normalized_target:
            continue
        asset = _select_github_asset(
            release.get("assets"),
            interface_model.name,
            pattern=github_asset_pattern,
        )
        if asset is None:
            break
        return asset

    raise MaaFWProjectUpdateError("GitHub release 未找到可下载的 zip 资源包")


def _validate_download_url(raw_url: str | None) -> str:
    url = str(raw_url or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme.casefold() != "https":
        raise MaaFWProjectUpdateError("MaaFW 远程更新包必须使用 HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise MaaFWProjectUpdateError("MaaFW 远程更新包 URL 无效")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise MaaFWProjectUpdateError("MaaFW 远程更新包不能指向本地或私有地址")
    return url


def _content_length(response: httpx.Response) -> int | None:
    raw_value = str(response.headers.get("content-length") or "").strip()
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        return None
    return value if value >= 0 else None


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

    current_url = _validate_download_url(download_url)
    send_log(f"开始下载 MaaFW 更新包: {sanitize_log_message(current_url)}")
    digest = hashlib.sha256()
    downloaded = 0
    try:
        async with httpx.AsyncClient(
            proxy=proxy, follow_redirects=False, timeout=30.0
        ) as client:
            for redirect_count in range(DOWNLOAD_REDIRECT_LIMIT + 1):
                async with client.stream("GET", current_url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = str(response.headers.get("location") or "").strip()
                        if not location or redirect_count >= DOWNLOAD_REDIRECT_LIMIT:
                            raise MaaFWProjectUpdateError(
                                "下载更新包重定向无效或次数过多"
                            )
                        current_url = _validate_download_url(
                            urljoin(current_url, location)
                        )
                        continue
                    if response.status_code not in (200, 206):
                        raise MaaFWProjectUpdateError(
                            f"下载更新包失败: HTTP {response.status_code}"
                        )
                    content_length = _content_length(response)
                    if (
                        content_length is not None
                        and content_length > DOWNLOAD_MAX_BYTES
                    ):
                        raise MaaFWProjectUpdateError("MaaFW 更新包超过下载大小限制")
                    async with aiofiles.open(temp_path, "wb") as file:
                        async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            downloaded += len(chunk)
                            if downloaded > DOWNLOAD_MAX_BYTES:
                                raise MaaFWProjectUpdateError(
                                    "MaaFW 更新包超过下载大小限制"
                                )
                            digest.update(chunk)
                            await file.write(chunk)
                    break
            else:
                raise MaaFWProjectUpdateError("下载更新包重定向失败")
    except BaseException:
        _remove_path(temp_path)
        raise

    try:
        if not downloaded:
            raise MaaFWProjectUpdateError("MaaFW 更新包为空")
        if (
            expected_sha256
            and digest.hexdigest().casefold() != expected_sha256.casefold()
        ):
            raise MaaFWProjectUpdateError("MaaFW 更新包 SHA256 校验失败")
        temp_path.replace(package_path)
    except BaseException:
        _remove_path(temp_path)
        raise
    return package_path


def _apply_update_package(
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
            send_log("正在应用 MaaFW 全量更新包")
            _apply_full_package(project_path, package_root, backup_dir)
        else:
            send_log("正在应用 MaaFW 增量更新包")
            _apply_incremental_package(
                project_path,
                package_root,
                changes_path,
                backup_dir,
                extract_dir,
            )
    finally:
        _remove_path(extract_dir)
        _remove_path(package_path)


def _apply_full_package(
    project_path: Path, package_root: Path, backup_dir: Path
) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        for child in project_path.iterdir():
            if child.name == UPDATE_WORK_DIR:
                continue
            target = backup_dir / child.name
            shutil.move(str(child), str(target))

        for child in package_root.iterdir():
            if child.name in {UPDATE_WORK_DIR, "changes.json"}:
                continue
            _copy_path(child, project_path / child.name)
    except Exception:
        try:
            _restore_full_backup(project_path, backup_dir)
        except Exception as restore_error:
            raise MaaFWProjectUpdateError(
                "MaaFW 全量更新失败且无法完整恢复备份，已中止本次运行",
                unsafe_to_continue=True,
            ) from restore_error
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
            target = _resolve_project_relative_path(
                project_path, relative_path.as_posix()
            )
            touched_paths.add(target)
            _backup_target(project_path, target, backup_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    except Exception:
        try:
            _restore_incremental_backup(project_path, backup_dir, touched_paths)
        except Exception as restore_error:
            raise MaaFWProjectUpdateError(
                "MaaFW 增量更新失败且无法完整恢复备份，已中止本次运行",
                unsafe_to_continue=True,
            ) from restore_error
        raise
    else:
        _remove_path(backup_dir)


def _load_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise MaaFWProjectUpdateError("更新源返回的不是 JSON") from exc
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("更新源返回的数据格式不正确")
    return data


def _load_response_json_list(response: httpx.Response) -> list[dict[str, Any]]:
    try:
        data = response.json()
    except Exception as exc:
        raise MaaFWProjectUpdateError("更新源返回的不是 JSON") from exc
    if not isinstance(data, list):
        raise MaaFWProjectUpdateError("更新源返回的数据格式不正确")
    return [item for item in data if isinstance(item, dict)]


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


def _parse_github_repo(github_url: str) -> tuple[str, str] | None:
    raw_value = github_url.strip().removesuffix(".git")
    if "://" not in raw_value:
        parts = [item for item in raw_value.strip("/").split("/") if item]
        return (parts[0], parts[1]) if len(parts) == 2 else None
    parsed = urlparse(raw_value)
    if parsed.netloc.lower() != "github.com":
        return None

    parts = [item for item in parsed.path.strip("/").split("/") if item]
    if len(parts) < 2:
        return None

    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return parts[0], repo


def _select_github_release(
    releases: list[dict[str, Any]],
    *,
    channel: str,
    tag: str = "",
) -> dict[str, Any] | None:
    normalized_tag = _normalize_version(tag) if tag.strip() else ""
    wants_prerelease = channel == "beta"
    for release in releases:
        if bool(release.get("draft")):
            continue
        if normalized_tag:
            release_tag = str(release.get("tag_name") or release.get("name") or "")
            if _normalize_version(release_tag) != normalized_tag:
                continue
            return release
        if bool(release.get("prerelease")) == wants_prerelease:
            return release
    return None


def _select_github_asset(
    raw_assets: Any,
    project_name: str,
    *,
    pattern: str = "",
) -> str | None:
    if not isinstance(raw_assets, list):
        return None

    assets: list[tuple[int, str]] = []
    for asset in raw_assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").lower()
        url = str(asset.get("browser_download_url") or "").strip()
        if not name.endswith(".zip") or not url:
            continue
        if pattern and not fnmatch(name, pattern.casefold()):
            continue

        score = 0
        if project_name and project_name.lower() in name:
            score += 2
        if "win" in name or "windows" in name:
            score += 3
        if "x64" in name or "x86_64" in name or "amd64" in name:
            score += 2
        if "linux" in name or "mac" in name or "darwin" in name:
            score -= 6
        assets.append((score, url))

    if not assets:
        return None
    return sorted(assets, key=lambda item: item[0], reverse=True)[0][1]


def _safe_extract_zip(package_path: Path, extract_dir: Path) -> None:
    try:
        with zipfile.ZipFile(package_path, "r") as zip_ref:
            members = zip_ref.infolist()
            if len(members) > ZIP_MAX_ENTRIES:
                raise MaaFWProjectUpdateError(
                    f"更新包文件数超过 {ZIP_MAX_ENTRIES} 个限制"
                )
            expanded_bytes = sum(max(0, int(member.file_size)) for member in members)
            if expanded_bytes > ZIP_MAX_EXPANDED_BYTES:
                raise MaaFWProjectUpdateError("更新包解压后体积超过 8 GiB 限制")
            for member in members:
                target = (extract_dir / member.filename).resolve()
                if not _is_within_path(target, extract_dir):
                    raise MaaFWProjectUpdateError(
                        f"更新包包含越界路径: {member.filename}"
                    )
            zip_ref.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise MaaFWProjectUpdateError("更新包不是有效 zip 文件") from exc


def _find_package_root(extract_dir: Path) -> Path:
    for candidate in [extract_dir, *_direct_child_dirs(extract_dir)]:
        if _has_interface_file(candidate):
            return candidate

    for interface_file in extract_dir.rglob("interface.json*"):
        if interface_file.name in {"interface.json", "interface.jsonc"}:
            return interface_file.parent

    raise MaaFWProjectUpdateError("更新包中未找到 interface.json")


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
        raise MaaFWProjectUpdateError(f"无法解析 changes.json: {exc}") from exc
    if not isinstance(data, dict):
        raise MaaFWProjectUpdateError("changes.json 必须是 JSON 对象")
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
            raise MaaFWProjectUpdateError(f"changes.json {key} 路径越界: {raw_path}")
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


def _restore_full_backup(project_path: Path, backup_dir: Path) -> None:
    for child in project_path.iterdir():
        if child.name != UPDATE_WORK_DIR:
            _remove_path(child)

    if not backup_dir.exists():
        return
    for backup_child in backup_dir.iterdir():
        shutil.move(str(backup_child), str(project_path / backup_child.name))


def _restore_incremental_backup(
    project_path: Path,
    backup_dir: Path,
    touched_paths: set[Path],
) -> None:
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


def _resolve_project_relative_path(project_path: Path, raw_path: str) -> Path:
    normalized = raw_path.strip().replace("\\", "/")
    if not normalized:
        raise MaaFWProjectUpdateError("更新包包含空路径")

    candidate = Path(normalized)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise MaaFWProjectUpdateError(f"更新包包含绝对路径: {raw_path}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise MaaFWProjectUpdateError(f"更新包包含非法路径: {raw_path}")
    if candidate.parts[0] == UPDATE_WORK_DIR:
        raise MaaFWProjectUpdateError(f"更新包禁止写入 {UPDATE_WORK_DIR}: {raw_path}")

    target = (project_path / candidate).resolve()
    if not _is_within_path(target, project_path):
        raise MaaFWProjectUpdateError(f"更新包路径越界: {raw_path}")
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


# ---------------------------------------------------------------------------
# Compatibility facade
# ---------------------------------------------------------------------------
#
# ``manager.py`` historically imported this module directly.  Keep that
# import contract while making the split core implementation the sole
# implementation used by the host path.  The legacy helpers above remain
# available to old callers during the migration, but all public operations
# below deliberately route through the durable state/transport/apply modules.

from .core.automas_maafw_project_update import (  # noqa: E402  (compat facade)
    MaaFWDownloadedProjectPackage as _CoreDownloadedProjectPackage,
)
from .core.automas_maafw_project_update import (
    MaaFWProjectUpdateCandidate as _CoreCandidate,
)
from .core.automas_maafw_project_update import (
    MaaFWProjectUpdateDiscovery as _CoreDiscovery,
)
from .core.automas_maafw_project_update import (
    MaaFWProjectUpdateError as _CoreUpdateError,
)
from .core.automas_maafw_project_update import (
    MaaFWProjectUpdateResult as _CoreResult,
)
from .core.automas_maafw_project_update import (
    apply_maafw_project_update as _core_apply_update,
)
from .core.automas_maafw_project_update import (
    discover_maafw_project_update as _core_discover_update,
)
from .core.automas_maafw_project_update.apply import apply_package_transaction
from .core.automas_maafw_project_update.contracts import project_fingerprint
from .core.automas_maafw_project_update.state import (
    DEFAULT_OPERATION_ROOT,
    UpdateOperationStore,
)
from .core.automas_maafw_project_update.transport import download_resumable

MaaFWProjectUpdateCandidate = _CoreCandidate
MaaFWProjectUpdateDiscovery = _CoreDiscovery
MaaFWDownloadedProjectPackage = _CoreDownloadedProjectPackage
MaaFWProjectUpdateResult = _CoreResult
MaaFWProjectUpdateError = _CoreUpdateError


def _compat_source_config(
    source: str,
    *,
    mirror_cdk: str,
    channel: str,
    github_repo: str,
    github_tag: str,
    github_asset_pattern: str,
) -> dict[str, Any]:
    provider = str(source or "").strip().lower()
    if provider in {"github", "github_release", "github release"}:
        provider = "github_release"
    elif provider in {"mirrorchyan", "mirror_chyan", "mirror chyan"}:
        provider = "mirrorchyan"
    else:
        provider = "mirrorchyan"
    return {
        "source": provider,
        "package_source": provider,
        "mirror_cdk": str(mirror_cdk or "").strip(),
        "channel": str(channel or "stable").strip() or "stable",
        "repo": str(github_repo or "").strip(),
        "tag": str(github_tag or "").strip(),
        "asset_pattern": str(github_asset_pattern or "").strip(),
    }


async def update_maafw_project_if_needed(
    project_path: Path,
    interface_model: Any,
    *,
    source: str = "MirrorChyan",
    mirror_cdk: str = "",
    channel: str = "stable",
    github_repo: str = "",
    github_tag: str = "",
    github_asset_pattern: str = "",
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
    post_validate: Callable[[Path], Any] | None = None,
    project_lock_already_held: bool = False,
) -> MaaFWProjectUpdateResult:
    """Run the unmanaged-project update workflow through the durable core.

    The signature intentionally matches the historical manager call.  Source
    selection is normalized to the package provider names; the core always
    obtains the target version from MirrorChyan and only uses GitHub to fetch
    an exact matching release when selected as the package source.
    """

    root = Path(project_path).resolve()
    log = send_log or (lambda _: None)
    current_version = str(getattr(interface_model, "version", "") or "")
    if not current_version:
        message = "interface 未声明版本，跳过 MaaFW 项目更新"
        log(message)
        return MaaFWProjectUpdateResult(
            checked=False,
            updated=False,
            current_version=current_version,
            message=message,
        )

    source_config = _compat_source_config(
        source,
        mirror_cdk=mirror_cdk,
        channel=channel,
        github_repo=github_repo,
        github_tag=github_tag,
        github_asset_pattern=github_asset_pattern,
    )

    # GitHub 发行版常按 UI 外壳分包（M9A 同版本同时发 MFAA / MXU zip）。
    # 选包实现需要 project_shell_hint 才能在项目名/平台收窄后按外壳消歧；
    # 与 API 检查路径保持一致，按项目根目录识别外壳家族补上。
    if not source_config.get("project_shell_hint"):
        shell_hint = await asyncio.to_thread(detect_maafw_project_shell_hint, root)
        if shell_hint:
            source_config["project_shell_hint"] = shell_hint

    discovery: MaaFWProjectUpdateDiscovery | None = None
    try:
        discovery = await _core_discover_update(
            interface_model,
            current_version=current_version,
            source_config=source_config,
            proxy=proxy,
            send_log=log,
        )
    except Exception as exc:
        log(f"{source} 更新检查失败: {exc}")

    if discovery is None:
        message = "MaaFW 项目已是最新或未配置可用更新源"
        log(message)
        return MaaFWProjectUpdateResult(
            checked=True,
            updated=False,
            current_version=current_version,
            message=message,
        )

    if not discovery.installable or discovery.candidate is None:
        message = (
            f"发现 MaaFW 项目更新: {current_version} -> {discovery.version} "
            f"({source_config['source']})，但没有可安装的更新包"
        )
        log(message)
        return MaaFWProjectUpdateResult(
            checked=True,
            updated=False,
            current_version=current_version,
            latest_version=discovery.version,
            source=source_config["source"],
            update_available=True,
            installable=False,
            message=message,
        )

    candidate = discovery.candidate
    if not candidate.project_fingerprint:
        candidate.project_fingerprint = await asyncio.to_thread(
            project_fingerprint,
            root,
        )
    if not candidate.plan_id:
        candidate.plan_id = uuid.uuid4().hex

    log(
        f"发现 MaaFW 项目更新: {current_version} -> {candidate.version} "
        f"({candidate.source})"
    )
    result = await _core_apply_update(
        root,
        candidate,
        proxy=proxy,
        send_log=log,
        post_validate=post_validate,
        project_lock_already_held=project_lock_already_held,
    )
    message = f"MaaFW 项目更新完成: {candidate.version}"
    log(message)
    return MaaFWProjectUpdateResult(
        checked=True,
        updated=True,
        current_version=current_version,
        latest_version=candidate.version,
        source=candidate.source,
        update_available=True,
        installable=True,
        message=message,
        operation_id=str(result.get("operationId") or "") or None,
        plan_id=str(result.get("planId") or candidate.plan_id or "") or None,
        project_fingerprint=str(result.get("finalFingerprint") or "") or None,
        package_type=str(result.get("packageType") or candidate.package_type or "")
        or None,
        resumed_from=int(result.get("resumedFrom") or 0),
    )


async def _download_update_package(
    project_path: Path,
    download_url: str,
    *,
    expected_sha256: str | None,
    proxy: httpx.Proxy | None,
    send_log: Callable[[str], None] | None,
) -> Path:
    """Compatibility helper backed by the resumable core transport."""

    operation = UpdateOperationStore.create(
        root=DEFAULT_OPERATION_ROOT,
        source="compat",
        targetVersion="",
    )
    outcome = await download_resumable(
        source="compat",
        version="",
        download_url=download_url,
        expected_sha256=expected_sha256,
        cache_root=Path.cwd() / "data" / "maafw_update_cache",
        operation=operation,
        proxy=proxy,
        send_log=send_log,
    )
    return outcome.path


def _apply_update_package(
    project_path: Path,
    package_path: Path,
    send_log: Callable[[str], None] | None = None,
) -> None:
    """Compatibility helper applying a package through the transaction core."""

    root = Path(project_path).resolve()
    current = project_fingerprint(root)
    operation = UpdateOperationStore.create(
        root=DEFAULT_OPERATION_ROOT,
        source="compat",
        targetVersion="",
        projectPath=str(root),
        expectedFingerprint=current,
    )
    apply_package_transaction(
        root,
        Path(package_path).resolve(),
        operation=operation,
        plan_id=operation.operation_id,
        expected_fingerprint=current,
        send_log=send_log,
    )
