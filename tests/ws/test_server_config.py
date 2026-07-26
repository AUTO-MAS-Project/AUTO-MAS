from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import main as main_module
from main import (
    UVICORN_WS_MAX_MESSAGE_BYTES,
    UVICORN_WS_MAX_QUEUE_MESSAGES,
    UVICORN_WS_PING_INTERVAL_SECONDS,
    UVICORN_WS_PING_TIMEOUT_SECONDS,
    build_uvicorn_config,
)
from app.core.ws.protocol import DEFAULT_MAX_MESSAGE_BYTES
from app.utils.ws_limits import (
    DEFAULT_WS_MAX_MESSAGE_BYTES,
    DEFAULT_WS_QUEUE_MESSAGES,
)


class FakeConfig:
    def __init__(self, app: object, **kwargs: object) -> None:
        self.app = app
        self.kwargs = kwargs


class TestServerConfig(TestCase):
    def test_protocol_ping_is_explicit(self) -> None:
        app = object()
        config = build_uvicorn_config(SimpleNamespace(Config=FakeConfig), app)

        self.assertIs(config.app, app)
        self.assertEqual(config.kwargs["host"], "127.0.0.1")
        self.assertEqual(config.kwargs["port"], 36163)
        self.assertEqual(
            config.kwargs["ws_max_size"],
            UVICORN_WS_MAX_MESSAGE_BYTES,
        )
        self.assertEqual(
            config.kwargs["ws_max_queue"],
            UVICORN_WS_MAX_QUEUE_MESSAGES,
        )
        self.assertEqual(
            config.kwargs["ws_ping_interval"],
            UVICORN_WS_PING_INTERVAL_SECONDS,
        )
        self.assertEqual(
            config.kwargs["ws_ping_timeout"],
            UVICORN_WS_PING_TIMEOUT_SECONDS,
        )
        self.assertEqual(UVICORN_WS_MAX_MESSAGE_BYTES, DEFAULT_MAX_MESSAGE_BYTES)
        self.assertEqual(UVICORN_WS_MAX_MESSAGE_BYTES, DEFAULT_WS_MAX_MESSAGE_BYTES)
        self.assertEqual(UVICORN_WS_MAX_QUEUE_MESSAGES, DEFAULT_WS_QUEUE_MESSAGES)
        self.assertEqual(UVICORN_WS_PING_INTERVAL_SECONDS, 20.0)
        self.assertEqual(UVICORN_WS_PING_TIMEOUT_SECONDS, 20.0)

    def test_default_startup_does_not_self_elevate(self) -> None:
        """默认(未设 AUTO_MAS_SELF_ELEVATE)非提升启动不得触发 UAC 重启。

        自提权会丢失 Electron 的进程句柄/stdio/env/PID 归属,是绿色包
        普通用户启动失败的直接根因;提权统一由前端重启整个应用完成。
        """

        class _StopAfterElevationGate(Exception):
            pass

        shell_execute = Mock(return_value=42)
        fake_windll = SimpleNamespace(
            shell32=SimpleNamespace(ShellExecuteW=shell_execute)
        )

        with (
            patch.object(main_module, "is_admin", return_value=False),
            patch.object(main_module.ctypes, "windll", fake_windll),
            patch.dict(main_module.os.environ, {}, clear=False),
            patch.object(
                main_module,
                "assert_port_available",
                side_effect=_StopAfterElevationGate,
            ),
            self.assertRaises(_StopAfterElevationGate),
        ):
            main_module.os.environ.pop("AUTO_MAS_SELF_ELEVATE", None)
            main_module.main()

        shell_execute.assert_not_called()

    def test_opt_in_uac_relaunch_preserves_original_working_directory(self) -> None:
        shell_execute = Mock(return_value=42)
        fake_windll = SimpleNamespace(
            shell32=SimpleNamespace(ShellExecuteW=shell_execute)
        )

        with (
            patch.object(main_module, "is_admin", return_value=False),
            patch.object(main_module.ctypes, "windll", fake_windll),
            patch.dict(
                main_module.os.environ, {"AUTO_MAS_SELF_ELEVATE": "1"}, clear=False
            ),
            patch.object(main_module.os, "getcwd", return_value=r"D:\isolated-profile"),
            patch.object(
                main_module.os.path,
                "realpath",
                return_value=r"D:\portable app\main.py",
            ),
            # pytest 自身的 argv 不得混入重启参数行
            patch.object(main_module.sys, "argv", [r"D:\portable app\main.py"]),
            patch.object(main_module.sys, "exit", side_effect=SystemExit(0)),
            self.assertRaises(SystemExit),
        ):
            main_module.main()

        self.assertEqual(shell_execute.call_args.args[3], r'"D:\portable app\main.py"')
        self.assertEqual(shell_execute.call_args.args[4], r"D:\isolated-profile")

    def test_opt_in_uac_relaunch_failure_is_not_reported_as_success(self) -> None:
        shell_execute = Mock(return_value=5)
        fake_windll = SimpleNamespace(
            shell32=SimpleNamespace(ShellExecuteW=shell_execute)
        )

        with (
            patch.object(main_module, "is_admin", return_value=False),
            patch.object(main_module.ctypes, "windll", fake_windll),
            patch.dict(
                main_module.os.environ, {"AUTO_MAS_SELF_ELEVATE": "1"}, clear=False
            ),
            patch.object(main_module.sys, "argv", [r"D:\portable app\main.py"]),
            self.assertRaisesRegex(RuntimeError, r"ShellExecuteW=5"),
        ):
            main_module.main()

    def test_relaunch_command_line_preserves_script_arguments(self) -> None:
        with (
            patch.object(
                main_module.os.path,
                "realpath",
                return_value=r"D:\portable app\main.py",
            ),
            patch.object(
                main_module.sys,
                "argv",
                [r"D:\portable app\main.py", "--flag", "value with space"],
            ),
        ):
            command_line = main_module._relaunch_command_line()

        self.assertEqual(
            command_line,
            r'"D:\portable app\main.py" --flag "value with space"',
        )
