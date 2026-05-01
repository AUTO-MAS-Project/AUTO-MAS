#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

import json
import asyncio
import subprocess
import sys
from contextlib import suppress
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
        logger: Any,
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

    def set_runtime_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """更新 runtime 配置并返回最新配置。"""
        if not isinstance(options, dict):
            raise ValueError("runtime options 必须是字典")

        runtime = self.config.get("runtime")
        if not isinstance(runtime, dict):
            runtime = {}
            self.config["runtime"] = runtime

        for key, value in options.items():
            runtime[key] = value

        # runtime 配置变更后清理缓存，确保 info 结果反映最新参数。
        self._cached_runtime_info = None
        self._audit("set_runtime_options", "ok", {"keys": list(options.keys())})
        return dict(runtime)

    def _audit(self, action: str, status: str, detail: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "plugin": self.plugin_name,
            "instance": self.instance_id,
            "action": action,
            "status": status,
        }
        if detail:
            payload.update(detail)
        self.logger.debug(f"[runtime] {json.dumps(payload, ensure_ascii=False, indent=2)}")

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
        """
        获取当前插件实例的运行时环境信息。

        Args:
            force_refresh (bool): 是否强制刷新缓存信息，默认为 False。

        Returns:
            Dict[str, Any]: 运行时信息字典，包含解释器路径及检查结果。
        """
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
        """
        校验目标 Python 解释器是否可用。

        Args:
            python_executable (Optional[str]): 指定解释器路径；为 None 时按配置与默认值解析。

        Returns:
            Dict[str, Any]: 检查结果字典，包含是否可用、路径及失败原因/版本信息。
        """
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
        """
        获取宿主暴露的脚本列表。

        Returns:
            Any: 脚本列表数据；当能力未注册时返回空列表。

        Raises:
            Exception: 调用宿主能力函数失败时透传异常。
        """
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
        """
        获取指定脚本的日志文本。

        Args:
            script_id (str): 脚本唯一标识。
            limit (int): 返回的最大行数限制，默认为 200。

        Returns:
            Any: 脚本日志数据；当能力未注册时返回空字符串。

        Raises:
            Exception: 调用宿主能力函数失败时透传异常。
        """
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

    async def run_python_snippet(
        self,
        code: str,
        *,
        python_executable: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        使用指定解释器执行一段 Python 代码并返回执行结果。

        Args:
            code (str): 待执行的 Python 代码片段。
            python_executable (Optional[str]): 可选解释器路径；为 None 时按配置解析。
            timeout_seconds (Optional[int]): 可选超时时间（秒）；为 None 时使用默认策略。

        Returns:
            Dict[str, Any]: 执行结果字典，包含成功状态、返回码、标准输出、标准错误和解释器路径。
        """
        target = self._resolve_interpreter(python_executable)
        timeout = self._resolve_timeout(timeout_seconds)

        try:
            process = await asyncio.create_subprocess_exec(
                target,
                "-c",
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_raw, stderr_raw = await asyncio.wait_for(process.communicate(), timeout=timeout)
            stdout = stdout_raw.decode("utf-8", errors="replace")
            stderr = stderr_raw.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            with suppress(Exception):
                process.kill()
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
            "ok": process.returncode == 0,
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "python": target,
        }

        self._audit(
            "run_python_snippet",
            "ok" if process.returncode == 0 else "error",
            {"python": target, "returncode": process.returncode},
        )
        return result
