from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .schema import BrowserMode
from .validation import validate_browser_url, validate_launch_arguments


ReusePolicy = Literal["error", "reuse"]
AutomationEngine = Literal["none", "m7a", "sra"]


class BrowserPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    browser_mode: BrowserMode | None = None
    browser_version: str | None = Field(default=None, min_length=1, max_length=64)


class BrowserOpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_instance_id: str = Field(
        default="manual",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    )
    namespace: str = Field(
        default="default",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
    )
    profile_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
    )
    initial_url: str | None = None
    browser_mode: BrowserMode | None = None
    browser_version: str | None = Field(default=None, min_length=1, max_length=64)
    headless: bool | None = None
    app_mode: bool | None = None
    window_width: int | None = Field(default=None, ge=640, le=7680)
    window_height: int | None = Field(default=None, ge=480, le=4320)
    page_load_timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    preferences: dict[str, Any] = Field(default_factory=dict)
    extra_arguments: list[str] = Field(default_factory=list)
    reuse_policy: ReusePolicy = "error"
    session_token: str | None = Field(default=None, min_length=32, max_length=256)
    automation_engine: AutomationEngine = "none"

    @field_validator("initial_url")
    @classmethod
    def validate_initial_url(cls, value: str | None) -> str | None:
        return validate_browser_url(value) if value is not None else None

    @field_validator("extra_arguments")
    @classmethod
    def validate_extra_arguments(cls, values: list[str]) -> list[str]:
        return validate_launch_arguments(values)


class BrowserOpenOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_instance_id: str
    namespace: str
    profile_id: str
    initial_url: str
    browser_mode: BrowserMode
    browser_version: str
    headless: bool
    app_mode: bool
    window_width: int
    window_height: int
    page_load_timeout_seconds: int
    preferences: dict[str, Any]
    extra_arguments: list[str]
    reuse_policy: ReusePolicy
    session_token: str | None
    automation_engine: AutomationEngine

    @property
    def profile_key(self) -> tuple[str, str, str]:
        return self.owner_instance_id, self.namespace, self.profile_id
