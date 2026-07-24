from __future__ import annotations

from typing import TYPE_CHECKING, Any

from auto_mas_core import BROWSER_RUNTIME_SERVICE
from pydantic import ValidationError

from .errors import BrowserRuntimeError
from .schema import Config
from .service import BrowserRuntime

if TYPE_CHECKING:
    from auto_mas_core import PluginContext, PluginHttpRequest


DEFAULT_INSTANCE = {
    "id": "browser:system",
    "name": "浏览器能力",
    "enabled": True,
    "config": Config().model_dump(mode="json"),
    "system": True,
    "locked": True,
}


class Plugin:
    """AUTO-MAS 内置 Chromium 浏览器能力。"""

    provides = (BROWSER_RUNTIME_SERVICE,)

    def __init__(self, ctx: "PluginContext") -> None:
        self.ctx = ctx
        self.runtime: BrowserRuntime | None = None
        self.config: Config | None = None
        self._manual_session_id = ""
        self._manual_session_token = ""

    async def on_start(self) -> None:
        try:
            config = Config.model_validate(self.ctx.config.to_dict())
        except ValidationError as exc:
            raise RuntimeError(f"浏览器插件配置无效，共 {exc.error_count()} 项") from exc

        runtime = BrowserRuntime(
            config=config,
            data_dir=self.ctx.data_dir / "browser",
            logger=self.ctx.logger,
        )
        self.config = config
        self.runtime = runtime
        try:
            # 路由全部就绪后再发布服务，避免消费者拿到半初始化运行时。
            self._register_routes()
            self.ctx.service.set(BROWSER_RUNTIME_SERVICE, runtime)
        except BaseException:
            await runtime.shutdown()
            self.runtime = None
            self.config = None
            raise
        self.ctx.logger.info("[browser] 浏览器运行时已加载")

    async def on_stop(self, reason: str) -> None:
        if self.runtime is None:
            return
        results = await self.runtime.shutdown()
        failures = [item for item in results if not item.get("closed")]
        if failures:
            self.ctx.logger.warning(
                f"[browser] 插件停止时有 {len(failures)} 个浏览器会话未能正常关闭"
            )
        self.runtime = None
        self.config = None
        self._manual_session_id = ""
        self._manual_session_token = ""
        self.ctx.logger.info(f"[browser] 浏览器运行时已停止, reason={reason}")

    def _register_routes(self) -> None:
        self.ctx.server.http(
            "/browser/capabilities",
            self._capabilities,
            methods=("GET",),
        )
        self.ctx.server.http(
            "/browser/open-default",
            self._open_default,
            methods=("POST",),
            action={"id": "browser.open-default", "label": "打开默认页面"},
        )
        self.ctx.server.http(
            "/browser/close-default",
            self._close_default,
            methods=("POST",),
            action={"id": "browser.close-default", "label": "关闭默认页面"},
        )

    async def _capabilities(self, _request: "PluginHttpRequest") -> dict[str, Any]:
        return self._success(self._runtime().snapshot())

    async def _open_default(self, _request: "PluginHttpRequest") -> dict[str, Any]:
        config = self._config()
        try:
            result = await self._runtime().open_session(
                {
                    "owner_instance_id": self.ctx.instance_id,
                    "namespace": "manual",
                    "profile_id": config.default_profile_id,
                    "initial_url": config.home_url,
                    "reuse_policy": "reuse",
                    "session_token": self._manual_session_token or None,
                }
            )
            self._manual_session_id = str(result["session_id"])
            self._manual_session_token = str(result["session_token"])
            return self._success(
                {
                    "state": result.get("state"),
                    "browser_mode": result.get("browser_mode"),
                    "headless": result.get("headless"),
                },
                message="默认页面已打开",
            )
        except BrowserRuntimeError as exc:
            return self._error_response(exc)
        except Exception as exc:
            return self._internal_error(exc)

    async def _close_default(self, _request: "PluginHttpRequest") -> dict[str, Any]:
        if not self._manual_session_id or not self._manual_session_token:
            return self._success(
                {"closed": True, "already_closed": True},
                message="默认页面已关闭",
            )
        try:
            result = await self._runtime().close_session(
                self._manual_session_id,
                session_token=self._manual_session_token,
            )
            self._manual_session_id = ""
            self._manual_session_token = ""
            return self._success(
                {
                    "closed": bool(result.get("closed")),
                    "already_closed": bool(result.get("already_closed")),
                },
                message="默认页面已关闭",
            )
        except BrowserRuntimeError as exc:
            return self._error_response(exc)
        except Exception as exc:
            return self._internal_error(exc)

    @staticmethod
    def _error_response(exc: BrowserRuntimeError) -> dict[str, Any]:
        status_code = {
            "INVALID_REQUEST": 400,
            "SESSION_FORBIDDEN": 403,
            "PROFILE_BUSY": 409,
            "PROFILE_CORRUPT": 409,
            "PROFILE_ENGINE_MISMATCH": 409,
            "SESSION_CLOSED": 404,
            "UNAVAILABLE": 503,
            "RUNTIME_STOPPING": 503,
            "PREPARE_TIMEOUT": 504,
            "LAUNCH_TIMEOUT": 504,
            "OPERATION_TIMEOUT": 504,
            "CLOSE_TIMEOUT": 504,
            "SHUTDOWN_TIMEOUT": 504,
        }.get(exc.code, 500)
        return {
            "code": status_code,
            "status": "error",
            "message": exc.message,
            "error": exc.to_dict(),
            "data": None,
        }

    def _internal_error(self, exc: Exception) -> dict[str, Any]:
        self.ctx.logger.exception(
            f"[browser] 插件动作失败: error={type(exc).__name__}"
        )
        return {
            "code": 500,
            "status": "error",
            "message": "浏览器插件动作执行失败",
            "error": {"code": "INTERNAL_ERROR", "retryable": False},
            "data": None,
        }

    def _runtime(self) -> BrowserRuntime:
        if self.runtime is None:
            raise RuntimeError("浏览器运行时尚未启动")
        return self.runtime

    def _config(self) -> Config:
        if self.config is None:
            raise RuntimeError("浏览器插件配置尚未加载")
        return self.config

    @staticmethod
    def _success(data: Any, *, message: str = "操作成功") -> dict[str, Any]:
        return {
            "code": 200,
            "status": "success",
            "message": message,
            "data": data,
        }
