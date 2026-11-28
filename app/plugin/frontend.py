"""插件界面声明及其启用期间的静态资源快照。"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote
from uuid import uuid4

from starlette.responses import Response

from app.models.schema import FrontendSurfaceMount, PanelArtifactInfo, PanelBinding

if TYPE_CHECKING:
    from starlette.requests import Request

    from .calls import CallGate

_MIME_TYPES = {
    ".qml": "application/octet-stream",
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


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


class MountedFrontend:
    """一次启用的面板声明和资源字节；HTTP 请求不再访问包目录。"""

    def __init__(self, gate: CallGate) -> None:
        self.gate = gate
        self.activation_id = uuid4().hex
        self.pages: dict[str, dict[str, PanelArtifactInfo]] = {}
        self.bindings: list[PanelBinding] = []
        self.block_pages: frozenset[str] = frozenset()
        self.diagnostics: list[str] = []
        self._assets: dict[str, tuple[str, bytes]] = {}

    @classmethod
    def load(
        cls,
        package: Path,
        name: str,
        script_key: str | None,
        plan_type: str | None,
        gate: CallGate,
        block_pages: Collection[str] = (),
    ) -> MountedFrontend | None:
        root = package / "ui"
        manifest = root / "manifest.json"
        self = cls(gate)
        digest = sha256()
        try:
            if _linked(package) or _linked(root) or _linked(manifest):
                raise ValueError("UI 目录和清单不能使用链接")
            if not manifest.exists() and not block_pages:
                return None
            raw = manifest.read_bytes()
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
            data = json.loads(raw)
            if (
                not isinstance(data, dict)
                or type(data.get("manifestVersion")) is not int
                or data["manifestVersion"] != 1
            ):
                raise ValueError("不支持的 manifestVersion")
            self._read_assets(root)
            self._read_pages(data.get("pages"))
            self._read_bindings(data.get("bindings"), name, script_key, plan_type)
        except (OSError, ValueError, RecursionError) as error:
            self.diagnostics.append(f"manifest.json: {error}")

        requested_pages = frozenset(block_pages)
        self.block_pages = requested_pages.intersection(self.pages)
        for page in sorted(requested_pages - self.block_pages):
            self.diagnostics.append(f"block_pages.{page}: 引用了不可用页面")

        for path, (_, content) in sorted(self._assets.items()):
            encoded = path.encode()
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        self.revision = digest.hexdigest()[:16]
        return self

    def _read_assets(self, root: Path) -> None:
        def unavailable(error: OSError) -> None:
            self.diagnostics.append(f"资源读取失败: {error.filename}")

        static_root = root.resolve(strict=True)
        for directory, dirs, files in root.walk(on_error=unavailable):
            dirs[:] = sorted(d for d in dirs if not _linked(directory / d))
            for filename in sorted(files):
                file = directory / filename
                path = file.relative_to(root).as_posix()
                mime = _MIME_TYPES.get(file.suffix.lower())
                if (
                    not mime
                    or path.casefold() == "manifest.json"
                    or not _relative_path(path)
                ):
                    continue
                try:
                    if (
                        not _linked(file)
                        and file.is_file()
                        and file.resolve(strict=True) == static_root / path
                    ):
                        self._assets[path] = (mime, file.read_bytes())
                except OSError as error:
                    unavailable(error)

    def _read_pages(self, pages: object) -> None:
        if not isinstance(pages, dict):
            raise ValueError("pages 必须是对象")
        for page, clients in pages.items():
            if not page or not isinstance(clients, dict) or not clients:
                self.diagnostics.append(f"pages.{page}: 缺少页面 ID 或产物")
                continue
            for client, raw in clients.items():
                try:
                    artifact = PanelArtifactInfo.model_validate(raw)
                    entry = artifact.entry
                    suffix = {"web": ".html", "qt-quick": ".qml"}.get(client)
                    if (
                        not client
                        or entry not in self._assets
                        or (suffix and not entry.endswith(suffix))
                    ):
                        raise ValueError("入口不可用")
                except ValueError as error:
                    self.diagnostics.append(f"pages.{page}.{client}: {error}")
                    continue
                self.pages.setdefault(page, {})[client] = artifact

    def _read_bindings(
        self, bindings: object, name: str, script_key: str | None, plan_type: str | None
    ) -> None:
        if not isinstance(bindings, list):
            raise ValueError("bindings 必须是数组")
        targets = {"settings": [{}], "extra": [{}], "notification": [{"channel": name}]}
        if script_key is not None:
            script = {"scriptType": script_key}
            for surface in ("script", "setup", "user"):
                targets[surface] = [script]
            targets["extra"].append(script)
        if plan_type is not None:
            plan = {"planType": plan_type}
            targets["plan"] = [plan]
            targets["extra"].append(plan)

        seen = set()
        for index, raw in enumerate(bindings):
            try:
                if isinstance(raw, dict) and "page" not in raw:
                    raw = {**raw, "page": raw.get("surface")}
                binding = PanelBinding.model_validate(raw)
                if binding.page not in self.pages:
                    raise ValueError("引用了不可用页面")
                surface = binding.surface
                claim = binding.model_dump(
                    exclude={"surface", "page"}, exclude_none=True
                )
                if claim not in targets.get(surface, []):
                    raise ValueError("目标未登记到本插件")
                target = (
                    surface,
                    binding.scriptType,
                    binding.planType,
                    binding.channel,
                    binding.page if surface == "extra" else None,
                )
                if target in seen:
                    raise ValueError("重复的入口绑定")
                seen.add(target)
                self.bindings.append(binding)
            except ValueError as error:
                self.diagnostics.append(f"bindings[{index}]: {error}")

    def surface_mount(self, *, name: str, page: str) -> FrontendSurfaceMount:
        """提供已通过校验的页面产物及其启用身份。"""
        return FrontendSurfaceMount(
            pluginName=name,
            pageId=page,
            revision=self.revision,
            activationId=self.activation_id,
            artifacts=self.pages[page],
        )

    def asset_response(
        self, *, revision: str, asset: str, prefix: str, request: Request
    ) -> Response:
        """仅返回当前修订的规范 URL，按资源类型附加隔离策略。"""
        if (
            not (self.bindings or self.block_pages)
            or revision != self.revision
            or asset not in self._assets
        ):
            return Response(status_code=404)
        raw_path = request.scope.get("raw_path")
        canonical = f"{quote(prefix)}/ui/{revision}/{quote(asset)}".encode("ascii")
        if raw_path is not None and raw_path not in (
            canonical,
            quote(request.scope.get("root_path", "")).encode("ascii") + canonical,
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
                "sandbox allow-scripts allow-forms",
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
