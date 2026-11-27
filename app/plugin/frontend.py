"""插件界面声明及其启用期间的静态资源快照。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote
from uuid import uuid4

from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.requests import Request

    from .calls import CallGate

FrontendSurfaceKind = Literal["script", "user", "plan", "setup"]
type SurfaceClaim = tuple[str | None, str, FrontendSurfaceKind]

_MIME_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}
_CSP_TYPES = {
    "script-src": "text/javascript",
    "style-src": "text/css",
    "img-src": "image/",
    "font-src": "font/",
    "connect-src": "",
}
_BASE_URL = re.compile(
    r"https?://(?:[a-zA-Z0-9._-]+|\[[0-9a-fA-F:.]+\])(?::[0-9]+)?(?:/[a-zA-Z0-9._~/%-]*)?"
)


def _relative_path(path: str) -> bool:
    return not re.search(r'[\\:%?#*"<>|\x00-\x1f\x7f]', path) and all(
        part not in ("", ".", "..") and not part.endswith((" ", "."))
        for part in path.split("/")
    )


@dataclass(frozen=True)
class FrontendSurface:
    mode: Literal["declarative", "wheel"]
    entry: str | None = None

    def __post_init__(self) -> None:
        if self.mode == "wheel" and (
            self.entry is None or not self.entry.endswith(".html")
        ):
            raise ValueError("wheel 界面必须声明 .html 入口")
        if self.mode == "declarative" and self.entry is not None:
            raise ValueError("声明式界面不能指定入口")


@dataclass(frozen=True)
class FrontendRouteAlias:
    surface: FrontendSurfaceKind
    path: str

    def __post_init__(self) -> None:
        if ".." in self.path or not re.fullmatch(
            r"/?(?:[\w~-][\w.~-]*|:[\w-]+|\{[\w-]+\})"
            r"(?:/(?:[\w~-][\w.~-]*|:[\w-]+|\{[\w-]+\}))*",
            self.path,
        ):
            raise ValueError(f"无效的宿主路由模板: {self.path!r}")


@dataclass(frozen=True)
class FrontendPlanCreation:
    key: str
    requires_parent_script: bool = False


@dataclass(frozen=True)
class FrontendTarget:
    script_key: str
    script_config_type: str
    user_config_type: str | None = None
    plan_config_type: str | None = None
    display_name: str | None = None
    icon_asset: str | None = None
    surfaces: Mapping[FrontendSurfaceKind, FrontendSurface] = field(kw_only=True)
    aliases: tuple[FrontendRouteAlias, ...] = ()
    plan_creation: FrontendPlanCreation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "surfaces", MappingProxyType(dict(self.surfaces)))
        object.__setattr__(self, "aliases", tuple(self.aliases))


@dataclass(frozen=True, kw_only=True)
class FrontendManifest:
    protocol_version: Literal[1] = 1
    static_dir: str
    assets: tuple[str, ...]
    targets: tuple[FrontendTarget, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "assets", tuple(sorted(set(self.assets))))
        object.__setattr__(self, "targets", tuple(self.targets))


class MountedFrontend:
    """只在启用时读取资源，HTTP 请求始终使用同一份字节快照。"""

    def __init__(
        self,
        *,
        manifest: FrontendManifest,
        package_root: Path,
        plugin_version: str,
        plan_types: Mapping[str, tuple[str, bool]],
        gate: CallGate,
    ) -> None:
        if manifest.protocol_version != 1:
            raise ValueError(f"不支持的界面协议版本: {manifest.protocol_version}")
        if not _relative_path(manifest.static_dir):
            raise ValueError(f"无效的界面静态目录: {manifest.static_dir!r}")
        package_root = package_root.resolve()
        static_root = (package_root / manifest.static_dir).resolve()
        if not static_root.is_relative_to(package_root) or not static_root.is_dir():
            raise ValueError(f"界面静态目录不存在或越界: {manifest.static_dir!r}")

        assets: dict[str, tuple[str, bytes]] = {}
        for asset in manifest.assets:
            mime = _MIME_TYPES.get(PurePosixPath(asset).suffix.lower())
            if not _relative_path(asset) or mime is None:
                raise ValueError(f"无效的界面资源路径或扩展名: {asset!r}")
            file = (static_root / asset).resolve()
            if not file.is_relative_to(static_root) or not file.is_file():
                raise ValueError(f"界面资源不存在或越界: {asset!r}")
            assets[asset] = (mime, file.read_bytes())

        claims: dict[SurfaceClaim, FrontendSurface] = {}
        for target in manifest.targets:
            icon = target.icon_asset
            if icon is not None and (
                icon not in assets or not assets[icon][0].startswith("image/")
            ):
                raise ValueError(f"界面图标必须是已声明的图片: {icon!r}")
            creation = target.plan_creation
            if creation is not None:
                plan = plan_types.get(creation.key)
                if plan is None or plan[0] != target.plan_config_type:
                    raise ValueError(
                        f"界面计划创建标识未指向声明的计划类型: {creation.key!r}"
                    )
                if creation.requires_parent_script and not plan[1]:
                    raise ValueError(f"计划类型不支持保存所属托管: {creation.key!r}")
            for kind, surface in target.surfaces.items():
                if surface.mode == "wheel" and surface.entry not in assets:
                    raise ValueError(
                        f"wheel 入口必须是已声明的 HTML: {surface.entry!r}"
                    )
                config_type = {
                    "script": target.script_config_type,
                    "setup": target.script_config_type,
                    "user": target.user_config_type,
                    "plan": target.plan_config_type,
                }[kind]
                if config_type is None:
                    raise ValueError(
                        f"{target.script_key} 未声明 {kind} 界面的配置类型"
                    )
                # 账号类型可以跨托管复用。独立计划的详情只按计划类型定位。
                parent_type = target.script_config_type if kind == "user" else None
                claim = (parent_type, config_type, kind)
                if claim in claims:
                    raise ValueError(f"重复声明界面: {claim}")
                claims[claim] = surface

        digest = sha256(
            json.dumps(
                (plugin_version, manifest),
                default=lambda value: (
                    dict(value) if isinstance(value, Mapping) else vars(value)
                ),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        for path, (_, content) in assets.items():
            encoded = path.encode()
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        self.manifest = manifest
        self.revision = digest.hexdigest()[:16]
        self.activation_id = uuid4().hex
        self.gate = gate
        self.claims = MappingProxyType(claims)
        self._assets = assets

    def asset_response(
        self, *, revision: str, asset: str, prefix: str, request: Request
    ) -> Response:
        """仅返回当前修订的规范 URL，按资源类型附加隔离策略。"""
        if revision != self.revision or asset not in self._assets:
            return Response(status_code=404)
        raw_path = request.scope.get("raw_path")
        if raw_path is not None and not raw_path.endswith(
            f"/ui/{revision}/{quote(asset)}".encode("ascii")
        ):
            return Response(status_code=404)

        mime, content = self._assets[asset]
        headers = {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        }
        if mime == "text/html":
            base = str(request.base_url).rstrip("/")
            if not _BASE_URL.fullmatch(base):
                return Response(status_code=404)
            root = f"{base}{quote(prefix)}/ui/{self.revision}/"
            policy = [
                "sandbox allow-scripts",
                "default-src 'none'",
                "base-uri 'none'",
                "form-action 'none'",
                "object-src 'none'",
                "frame-src 'none'",
                "worker-src 'none'",
            ]
            for directive, mime_prefix in _CSP_TYPES.items():
                sources = " ".join(
                    root + quote(path)
                    for path, (asset_mime, _) in self._assets.items()
                    if asset_mime.startswith(mime_prefix)
                )
                policy.append(directive + " " + (sources or "'none'"))
            headers["Content-Security-Policy"] = "; ".join(policy)
        elif mime == "image/svg+xml":
            headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return Response(content, media_type=mime, headers=headers)
