from __future__ import annotations

from typing import Literal

from app.plugins.fields import PluginField
from pydantic import BaseModel, ConfigDict, field_validator

from .validation import validate_browser_url, validate_launch_arguments


BrowserMode = Literal["auto", "managed", "chrome", "edge", "custom"]


class Config(BaseModel):
    """浏览器系统插件配置。"""

    model_config = ConfigDict(extra="ignore")

    browser_mode: BrowserMode = PluginField(
        default="managed",
        title="浏览器模式",
        description="managed 使用插件准备的 Chrome for Testing；auto 优先使用系统 Edge/Chrome。",
        size="half",
        option_labels={
            "auto": "自动选择",
            "managed": "内置 Chrome for Testing",
            "chrome": "系统 Chrome",
            "edge": "系统 Edge",
            "custom": "自定义 Chromium",
        },
    )
    managed_browser_version: str = PluginField(
        default="stable",
        title="内置浏览器版本",
        description="支持 stable、beta、dev、canary 或具体 Chrome for Testing 版本。",
        min_length=1,
        max_length=64,
        size="half",
    )
    browser_path: str = PluginField(
        default="",
        title="浏览器路径",
        description="custom 模式必填；chrome/edge 模式留空时自动查找。",
        size="large",
        ui_type="path",
        path_kind="file",
    )
    driver_path: str = PluginField(
        default="",
        title="WebDriver 路径",
        description="留空时由 Selenium Manager 准备匹配的驱动。",
        size="large",
        ui_type="path",
        path_kind="file",
    )
    home_url: str = PluginField(
        default="about:blank",
        title="默认页面",
        description="插件页“打开默认页面”动作使用；HSR 会通过服务传入云星铁地址。",
        size="large",
        format="url",
    )
    default_profile_id: str = PluginField(
        default="default",
        title="默认 Profile",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
        size="half",
    )
    headless: bool = PluginField(
        default=False,
        title="默认无窗口运行",
        description="首次登录建议关闭；同一持久 profile 登录后可切换为无窗口模式。",
        size="half",
    )
    app_mode: bool = PluginField(
        default=True,
        title="应用窗口模式",
        description="隐藏常规浏览器工具栏，以独立应用窗口打开目标页面。",
        size="half",
    )
    window_width: int = PluginField(
        default=1920,
        title="窗口宽度",
        ge=640,
        le=7680,
        size="half",
    )
    window_height: int = PluginField(
        default=1080,
        title="窗口高度",
        ge=480,
        le=4320,
        size="half",
    )
    page_load_timeout_seconds: int = PluginField(
        default=60,
        title="页面加载超时（秒）",
        ge=5,
        le=600,
        size="half",
    )
    manager_timeout_seconds: int = PluginField(
        default=300,
        title="浏览器准备超时（秒）",
        ge=10,
        le=1800,
        size="half",
    )
    language: str = PluginField(
        default="zh-CN",
        title="浏览器语言",
        min_length=2,
        max_length=32,
        size="half",
    )
    browser_mirror_url: str = PluginField(
        default="",
        title="浏览器镜像地址",
        description="可选，仅传给 Selenium Manager；不填写时使用官方源。",
        size="large",
        format="url",
    )
    driver_mirror_url: str = PluginField(
        default="",
        title="驱动镜像地址",
        description="可选，仅传给 Selenium Manager；不填写时使用官方源。",
        size="large",
        format="url",
    )
    extra_arguments: list[str] = PluginField(
        default_factory=list,
        title="额外启动参数",
        description="每项一个 Chromium 参数；profile 与远程调试参数由插件保留。",
        size="large",
        ui_type="json",
        json_type="array",
    )

    @field_validator("home_url")
    @classmethod
    def validate_home_url(cls, value: str) -> str:
        return validate_browser_url(value)

    @field_validator("browser_mirror_url", "driver_mirror_url")
    @classmethod
    def validate_optional_url(cls, value: str) -> str:
        url = str(value or "").strip()
        return validate_browser_url(url) if url else ""

    @field_validator("extra_arguments")
    @classmethod
    def validate_extra_arguments(cls, values: list[str]) -> list[str]:
        return validate_launch_arguments(values)
