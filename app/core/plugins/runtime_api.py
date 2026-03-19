#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class RuntimeAPI:
    """插件运行时门面：高能力、最小限制、统一审计。"""

    def __init__(
        self,
        *,
        plugin_name: str,
        instance_id: str,
        config: Dict[str, Any],
        logger,
        runtime_capabilities: Optional[Dict[str, Callable[..., Any]]] = None,
    ) -> None:
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.config = config or {}
        self.logger = logger
        self.runtime_capabilities = runtime_capabilities or {}
        self._cached_runtime_info: Optional[Dict[str, Any]] = None

    def _runtime_options(self) -> Dict[str, Any]:
        runtime = self.config.get("runtime")
        if isinstance(runtime, dict):
            return runtime
        return {}

    def _audit(self, action: str, status: str, detail: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "plugin": self.plugin_name,
            "instance": self.instance_id,
            "action": action,
            "status": status,
        }
        if detail:
            payload.update(detail)
        self.logger.info(f"[runtime] {json.dumps(payload, ensure_ascii=False)}")

    def _resolve_interpreter(self, override: Optional[str] = None) -> str:
        runtime_options = self._runtime_options()

        candidates = [
            override,
            runtime_options.get("python_executable"),
            self.config.get("python_executable"),
            sys.executable,
        ]

        for item in candidates:
            if isinstance(item, str) and item.strip():
                return item.strip()

        return sys.executable

    def _resolve_timeout(self, override: Optional[int] = None, default: int = 15) -> int:
        runtime_options = self._runtime_options()

        value = override
        if value is None:
            value = runtime_options.get("python_timeout_seconds")
        if value is None:
            value = self.config.get("python_timeout_seconds")
        if value is None:
            value = default

        try:
            timeout = int(value)
        except Exception:
            timeout = default

        return max(1, min(timeout, 300))

    def get_runtime_info(self, force_refresh: bool = False) -> Dict[str, Any]:
        if self._cached_runtime_info is not None and not force_refresh:
            return self._cached_runtime_info

        interpreter_path = self._resolve_interpreter()
        interpreter_check = self.check_interpreter(interpreter_path)

        info = {
            "plugin": self.plugin_name,
            "instance": self.instance_id,
            "host_python": sys.executable,
            "selected_python": interpreter_path,
            "interpreter_check": interpreter_check,
        }
        self._cached_runtime_info = info
        return info

    def check_interpreter(self, python_executable: Optional[str] = None) -> Dict[str, Any]:
        target = self._resolve_interpreter(python_executable)
        timeout = self._resolve_timeout(default=8)

        if not Path(target).exists():
            result = {
                "ok": False,
                "python": target,
                "reason": "解释器路径不存在",
            }
            self._audit("check_interpreter", "error", result)
            return result

        try:
            completed = subprocess.run(
                [target, "-c", "import sys; print(sys.version)"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            result = {
                "ok": False,
                "python": target,
                "reason": "解释器检查超时",
            }
            self._audit("check_interpreter", "error", result)
            return result
        except Exception as e:
            result = {
                "ok": False,
                "python": target,
                "reason": f"解释器检查异常: {type(e).__name__}: {e}",
            }
            self._audit("check_interpreter", "error", result)
            return result

        if completed.returncode != 0:
            result = {
                "ok": False,
                "python": target,
                "reason": (completed.stderr or completed.stdout or "解释器不可用").strip(),
            }
            self._audit("check_interpreter", "error", result)
            return result

        result = {
            "ok": True,
            "python": target,
            "version": (completed.stdout or "").strip(),
        }
        self._audit("check_interpreter", "ok", {"python": target})
        return result

    def list_scripts(self) -> Any:
        func = self.runtime_capabilities.get("list_scripts")
        if not callable(func):
            self._audit("list_scripts", "ok", {"source": "empty"})
            return []

        try:
            data = func()
            self._audit("list_scripts", "ok", {"source": "capability"})
            return data
        except Exception as e:
            self._audit("list_scripts", "error", {"reason": f"{type(e).__name__}: {e}"})
            raise

    def get_script_log(self, script_id: str, limit: int = 200) -> Any:
        func = self.runtime_capabilities.get("get_script_log")
        if not callable(func):
            self._audit("get_script_log", "ok", {"source": "empty", "script_id": script_id})
            return ""

        try:
            data = func(script_id, limit)
            self._audit("get_script_log", "ok", {"script_id": script_id, "limit": limit})
            return data
        except Exception as e:
            self._audit(
                "get_script_log",
                "error",
                {"script_id": script_id, "reason": f"{type(e).__name__}: {e}"},
            )
            raise

    def run_python_snippet(
        self,
        code: str,
        *,
        python_executable: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        target = self._resolve_interpreter(python_executable)
        timeout = self._resolve_timeout(timeout_seconds)

        try:
            completed = subprocess.run(
                [target, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            result = {
                "ok": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "Python 代码执行超时",
                "python": target,
            }
            self._audit("run_python_snippet", "error", {"python": target, "timeout": timeout})
            return result
        except Exception as e:
            result = {
                "ok": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Python 代码执行异常: {type(e).__name__}: {e}",
                "python": target,
            }
            self._audit("run_python_snippet", "error", {"python": target, "reason": str(e)})
            return result

        result = {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "python": target,
        }

        self._audit(
            "run_python_snippet",
            "ok" if completed.returncode == 0 else "error",
            {"python": target, "returncode": completed.returncode},
        )
        return result
