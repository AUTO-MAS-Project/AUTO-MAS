from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils import get_logger


logger = get_logger("页面注册")

PageSection = Literal["main", "bottom", "dev"]
PageRenderer = Literal["component", "iframe", "custom-element"]


class PageDeclaration(BaseModel):
    """前端页面声明。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    menu_label: str = Field(..., min_length=1)
    icon: str = Field(default="app")
    component: str = Field(default="PluginPage", min_length=1)
    renderer: PageRenderer = Field(default="component")
    url: str | None = Field(default=None)
    frontend_plugin: str | None = Field(default=None)
    element_tag: str | None = Field(default=None)
    entry_asset_url: str | None = Field(default=None)
    style_asset_urls: list[str] = Field(default_factory=list)
    manifest_version: int | None = Field(default=None)
    section: PageSection = Field(default="main")
    order: int = Field(default=1000)
    visible: bool = Field(default=True)
    dev_only: bool = Field(default=False)
    source: str = Field(default="host:core")

    @field_validator(
        "id",
        "title",
        "menu_label",
        "icon",
        "component",
        "source",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, raw: Any) -> str:
        text = str(raw or "").strip()
        if not text:
            raise ValueError("页面声明字段不能为空")
        return text

    @field_validator("path", mode="before")
    @classmethod
    def _normalize_path(cls, raw: Any) -> str:
        text = str(raw or "").strip()
        if not text:
            raise ValueError("页面路径不能为空")
        text = "/" + text.lstrip("/")
        while "//" in text:
            text = text.replace("//", "/")
        if text != "/" and text.endswith("/"):
            text = text[:-1]
        return text

    @field_validator("section", mode="before")
    @classmethod
    def _normalize_section(cls, raw: Any) -> PageSection:
        text = str(raw or "main").strip().lower()
        if text not in {"main", "bottom", "dev"}:
            raise ValueError("页面 section 仅支持 main、bottom 或 dev")
        return text  # type: ignore[return-value]

    @field_validator("renderer", mode="before")
    @classmethod
    def _normalize_renderer(cls, raw: Any) -> PageRenderer:
        text = str(raw or "component").strip().lower()
        if text not in {"component", "iframe", "custom-element"}:
            raise ValueError("页面 renderer 仅支持 component、iframe 或 custom-element")
        return text  # type: ignore[return-value]

    @field_validator("url", "frontend_plugin", "element_tag", "entry_asset_url", mode="before")
    @classmethod
    def _strip_optional_text(cls, raw: Any) -> str | None:
        if raw is None:
            return None
        text = str(raw or "").strip()
        return text or None

    @field_validator("style_asset_urls", mode="before")
    @classmethod
    def _normalize_style_asset_urls(cls, raw: Any) -> list[str]:
        if raw is None:
            return []
        items = raw if isinstance(raw, list) else [raw]
        result: list[str] = []
        for item in items:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result


class PageRegistry:
    """管理主程序和插件声明的前端页面。"""

    def __init__(self) -> None:
        self._pages: dict[str, PageDeclaration] = {}
        self._path_index: dict[str, str] = {}
        self._warnings: list[str] = []

    def clear(self) -> None:
        self._pages.clear()
        self._path_index.clear()
        self._warnings.clear()

    def register(
        self,
        declaration: PageDeclaration | dict[str, Any],
        *,
        source: str | None = None,
        frontend_plugin: str | None = None,
    ) -> PageDeclaration:
        payload = (
            declaration.model_dump()
            if isinstance(declaration, PageDeclaration)
            else deepcopy(declaration)
        )
        if source is not None:
            payload["source"] = source
        if frontend_plugin and not payload.get("frontend_plugin"):
            payload["frontend_plugin"] = frontend_plugin
        page = PageDeclaration.model_validate(payload)

        existing_id = self._pages.get(page.id)
        if existing_id is not None and not self._should_replace(page, existing_id):
            self._warn(
                f"页面 id 冲突，已保留既有声明: id={page.id}, source={page.source}, existing={existing_id.source}"
            )
            return existing_id

        existing_path_id = self._path_index.get(page.path)
        if existing_path_id and existing_path_id != page.id:
            existing_path = self._pages.get(existing_path_id)
            if existing_path is not None and not self._should_replace(page, existing_path):
                self._warn(
                    f"页面路径冲突，已保留既有声明: path={page.path}, source={page.source}, existing={existing_path.source}"
                )
                return existing_path
            if existing_path is not None:
                self._pages.pop(existing_path.id, None)
                self._path_index.pop(existing_path.path, None)

        if existing_id is not None:
            self._path_index.pop(existing_id.path, None)
        self._pages[page.id] = page
        self._path_index[page.path] = page.id
        return page

    def register_many(
        self,
        declarations: list[Any] | tuple[Any, ...],
        *,
        source: str,
        frontend_plugin: str | None = None,
    ) -> None:
        for declaration in declarations:
            try:
                self.register(
                    declaration,
                    source=source,
                    frontend_plugin=frontend_plugin,
                )
            except Exception as exc:
                self._warn(
                    f"页面声明无效，已跳过: source={source}, error={type(exc).__name__}: {exc}"
                )

    def unregister_source(self, source: str) -> None:
        normalized = str(source or "").strip()
        if not normalized:
            return
        for page_id, page in list(self._pages.items()):
            if page.source != normalized:
                continue
            self._pages.pop(page_id, None)
            self._path_index.pop(page.path, None)

    def list_pages(self) -> list[PageDeclaration]:
        return sorted(
            self._pages.values(),
            key=lambda item: (
                self._section_rank(item.section),
                int(item.order),
                item.menu_label,
                item.id,
            ),
        )

    def snapshot(self) -> list[dict[str, Any]]:
        return [page.model_dump() for page in self.list_pages()]

    def warnings(self) -> list[str]:
        return list(self._warnings)

    @staticmethod
    def _priority(page: PageDeclaration) -> tuple[int, int, str]:
        source = page.source
        if source == "host:core":
            rank = 0
        elif source.startswith("host:"):
            rank = 1
        elif source.startswith("module:"):
            rank = 2
        else:
            rank = 3
        return rank, int(page.order), source

    @staticmethod
    def _section_rank(section: str) -> int:
        if section == "main":
            return 0
        if section == "bottom":
            return 1
        if section == "dev":
            return 2
        return 3

    def _should_replace(self, incoming: PageDeclaration, existing: PageDeclaration) -> bool:
        return self._priority(incoming) < self._priority(existing)

    def _warn(self, message: str) -> None:
        self._warnings.append(message)
        logger.warning(message)


class PageFacade:
    """插件上下文中的页面声明门面。"""

    def __init__(
        self,
        *,
        instance_id: str,
        plugin_name: str | None,
        registry: PageRegistry,
    ) -> None:
        self._source = f"plugin:{instance_id}"
        self._frontend_plugin = str(plugin_name or "").strip() or None
        self._registry = registry

    def register(
        self,
        *,
        id: str,
        path: str,
        title: str,
        menu_label: str,
        icon: str = "app",
        component: str = "PluginPage",
        renderer: PageRenderer = "component",
        url: str | None = None,
        frontend_plugin: str | None = None,
        element_tag: str | None = None,
        entry_asset_url: str | None = None,
        style_asset_urls: list[str] | None = None,
        manifest_version: int | None = None,
        section: PageSection = "main",
        order: int = 1000,
        visible: bool = True,
        dev_only: bool = False,
    ) -> PageDeclaration:
        """Register a frontend page exposed by the current plugin."""
        return self._registry.register(
            {
                "id": id,
                "path": path,
                "title": title,
                "menu_label": menu_label,
                "icon": icon,
                "component": component,
                "renderer": renderer,
                "url": url,
                "frontend_plugin": frontend_plugin,
                "element_tag": element_tag,
                "entry_asset_url": entry_asset_url,
                "style_asset_urls": style_asset_urls or [],
                "manifest_version": manifest_version,
                "section": section,
                "order": order,
                "visible": visible,
                "dev_only": dev_only,
            },
            source=self._source,
            frontend_plugin=self._frontend_plugin,
        )

    def register_many(self, pages: list[Any] | tuple[Any, ...]) -> None:
        self._registry.register_many(
            pages,
            source=self._source,
            frontend_plugin=self._frontend_plugin,
        )

    def unregister_all(self) -> None:
        self._registry.unregister_source(self._source)


page_registry = PageRegistry()


BUILTIN_PAGES: list[dict[str, Any]] = [
    {
        "id": "home",
        "path": "/home",
        "title": "主页",
        "menu_label": "主页",
        "icon": "home",
        "component": "Home",
        "section": "main",
        "order": 10,
    },
    {
        "id": "scripts",
        "path": "/scripts",
        "title": "脚本管理",
        "menu_label": "脚本管理",
        "icon": "script",
        "component": "Scripts",
        "section": "main",
        "order": 20,
    },
    {
        "id": "plans",
        "path": "/plans",
        "title": "计划管理",
        "menu_label": "计划管理",
        "icon": "plan",
        "component": "Plans",
        "section": "main",
        "order": 30,
    },
    {
        "id": "emulators",
        "path": "/emulators",
        "title": "模拟器管理",
        "menu_label": "模拟器管理",
        "icon": "emulator",
        "component": "Emulators",
        "section": "main",
        "order": 40,
    },
    {
        "id": "plugins",
        "path": "/plugins",
        "title": "插件管理",
        "menu_label": "插件管理",
        "icon": "plugin",
        "component": "Plugin",
        "section": "main",
        "order": 50,
    },
    {
        "id": "plugins-market",
        "path": "/plugins-market",
        "title": "插件市场",
        "menu_label": "插件市场",
        "icon": "market",
        "component": "PluginMarket",
        "section": "main",
        "order": 60,
    },
    {
        "id": "queue",
        "path": "/queue",
        "title": "调度队列",
        "menu_label": "调度队列",
        "icon": "queue",
        "component": "Queue",
        "section": "main",
        "order": 70,
    },
    {
        "id": "scheduler",
        "path": "/scheduler",
        "title": "调度中心",
        "menu_label": "调度中心",
        "icon": "scheduler",
        "component": "Scheduler",
        "section": "main",
        "order": 80,
    },
    {
        "id": "history",
        "path": "/history",
        "title": "历史记录",
        "menu_label": "历史记录",
        "icon": "history",
        "component": "History",
        "section": "bottom",
        "order": 10,
    },
    {
        "id": "tools",
        "path": "/tools",
        "title": "工具",
        "menu_label": "工具",
        "icon": "tool",
        "component": "Tools",
        "section": "bottom",
        "order": 20,
    },
    {
        "id": "settings",
        "path": "/settings",
        "title": "设置",
        "menu_label": "设置",
        "icon": "settings",
        "component": "Settings",
        "section": "bottom",
        "order": 30,
    },
    {
        "id": "test-router",
        "path": "/TestRouter",
        "title": "测试路由",
        "menu_label": "测试路由",
        "icon": "dev",
        "component": "TestRouter",
        "section": "dev",
        "order": 10,
        "dev_only": True,
    },
    {
        "id": "ocr-dev",
        "path": "/OCRdev",
        "title": "OCR 测试",
        "menu_label": "OCR测试",
        "icon": "dev",
        "component": "OCRdev",
        "section": "dev",
        "order": 20,
        "dev_only": True,
    },
    {
        "id": "ws-dev",
        "path": "/WSdev",
        "title": "WebSocket 测试",
        "menu_label": "WebSocket测试",
        "icon": "api",
        "component": "WSdev",
        "section": "dev",
        "order": 30,
        "dev_only": True,
    },
    {
        "id": "overlay-mask-dev",
        "path": "/OverlayMaskDev",
        "title": "遮罩测试",
        "menu_label": "遮罩测试",
        "icon": "dev",
        "component": "OverlayMaskDev",
        "section": "dev",
        "order": 40,
        "dev_only": True,
    },
]


def register_builtin_pages() -> None:
    page_registry.unregister_source("host:core")
    page_registry.register_many(BUILTIN_PAGES, source="host:core")
