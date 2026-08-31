"""`POST /api/scripts/maafw/agent-env/prepare` 的契约与失败路径。

项目引导读到 interface 后调用它把运行环境备好，免得首次运行时才付下载成本。
与 `/maafw/update` 一样是同步端点。

真实准备会联网建 venv，这里只覆盖不联网的分支：参数校验、项目锁冲突、
interface 读取失败，以及成功路径的响应装配（准备本身被 mock 掉）。
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.api.scripts import prepare_maafw_agent_env
from app.models.schema import MaaFWAgentEnvPrepareIn

INTERFACE = {
    "interface_version": 2,
    "name": "Demo",
    "version": "v1.0.0",
    "controller": [{"name": "桌面端", "type": "Win32"}],
    "resource": [{"name": "简中", "path": ["{PROJECT_DIR}/resource/base"]}],
    "task": [{"name": "启动游戏", "entry": "StartUp"}],
}

PREPARE_TARGET = (
    "app.task.MaaFW.tools.core.automas_maafw_runner.service"
    ".MaaFWRunnerService.prepare_project_environment"
)


def call(path: str, **kwargs):
    return asyncio.run(
        prepare_maafw_agent_env(MaaFWAgentEnvPrepareIn(path=path, **kwargs))
    )


class AgentEnvPrepareValidationTest(unittest.TestCase):
    def test_empty_path_is_rejected(self) -> None:
        out = call("   ")
        self.assertEqual(out.code, 400)
        self.assertEqual(out.status, "error")

    def test_non_directory_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = call(str(Path(tmp) / "nope"))
        self.assertEqual(out.code, 400)
        self.assertIn("目录", out.message)

    def test_unreadable_interface_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # 是目录但没有 interface.json
            out = call(tmp)
        self.assertEqual(out.code, 400)
        self.assertIn("interface", out.message)
        self.assertIsNotNone(out.data)
        self.assertEqual(out.data.path, str(Path(tmp).resolve()))


class AgentEnvPrepareLockTest(unittest.TestCase):
    def test_busy_project_returns_conflict(self) -> None:
        """与运行、更新共用同一把项目锁，占用时必须 409 而不是并发去建环境。"""

        from app.task.MaaFW.tools.embedded.project_path import (
            release_project_path,
            try_reserve_project_path,
        )

        async def go():
            with tempfile.TemporaryDirectory() as tmp:
                key = await try_reserve_project_path(tmp)
                try:
                    return await prepare_maafw_agent_env(
                        MaaFWAgentEnvPrepareIn(path=tmp)
                    )
                finally:
                    await release_project_path(key)

        out = asyncio.run(go())
        self.assertEqual(out.code, 409)
        self.assertIn("稍后重试", out.message)

    def test_lock_is_released_after_a_failure(self) -> None:
        """失败路径也要还锁，否则项目会被永久占住。"""

        from app.task.MaaFW.tools.embedded.project_path import (
            release_project_path,
            try_reserve_project_path,
        )

        async def go():
            with tempfile.TemporaryDirectory() as tmp:
                # 无 interface.json，必然失败
                await prepare_maafw_agent_env(MaaFWAgentEnvPrepareIn(path=tmp))
                key = await try_reserve_project_path(tmp)
                await release_project_path(key)
                return key

        self.assertIsNotNone(asyncio.run(go()))


class AgentEnvPrepareSuccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name) / "project"
        (self.project / "resource" / "base").mkdir(parents=True)
        (self.project / "interface.json").write_text(
            json.dumps(INTERFACE, ensure_ascii=False), encoding="utf-8"
        )

    def test_response_carries_runtime_and_agent_details(self) -> None:
        prepared = {
            "status": "ready",
            "runtime": {
                "runtimeId": "maafw-runtime-abc",
                "poolId": "pool-1",
                "pythonExecutable": r"C:\pool\env\Scripts\python.exe",
                "venvPath": r"C:\pool\env",
                "maafwVersion": "5.12.3",
            },
            "agents": {
                "plans": [
                    {
                        "childExec": "python/python.exe",
                        "executable": r"C:\proj\python\python.exe",
                        "runtimeKind": "project_python",
                        "isolatedVenvPath": None,
                        "fallbackReason": None,
                    }
                ]
            },
        }
        with mock.patch(PREPARE_TARGET, return_value=prepared):
            out = call(str(self.project))

        self.assertEqual(out.code, 200)
        self.assertEqual(out.status, "success")
        data = out.data
        self.assertEqual(data.runtimeId, "maafw-runtime-abc")
        self.assertEqual(data.poolId, "pool-1")
        self.assertEqual(data.maafwVersion, "5.12.3")
        self.assertEqual(data.agentCount, 1)
        self.assertEqual(data.agents[0].runtimeKind, "project_python")
        self.assertEqual(data.agents[0].childExec, "python/python.exe")

    def test_project_without_agents_still_succeeds(self) -> None:
        with mock.patch(
            PREPARE_TARGET,
            return_value={"runtime": {"runtimeId": "r"}, "agents": {"plans": []}},
        ):
            out = call(str(self.project))
        self.assertEqual(out.code, 200)
        self.assertEqual(out.data.agentCount, 0)

    def test_malformed_prepare_result_does_not_crash(self) -> None:
        """服务层返回形状异常时给出 200 + 空 agent，而不是 500。"""

        with mock.patch(PREPARE_TARGET, return_value={"runtime": None, "agents": None}):
            out = call(str(self.project))
        self.assertEqual(out.code, 200)
        self.assertEqual(out.data.agentCount, 0)
        self.assertIsNone(out.data.runtimeId)

    def test_prepare_failure_is_reported_as_500(self) -> None:
        with mock.patch(PREPARE_TARGET, side_effect=RuntimeError("uv 装不上")):
            out = call(str(self.project))
        self.assertEqual(out.code, 500)
        self.assertIn("uv 装不上", out.message)
        self.assertIsNotNone(out.data)

    def test_repo_root_is_passed_as_import_path(self) -> None:
        """worker 跑在隔离 venv 里，代码要靠 PYTHONPATH 找到本仓。"""

        with mock.patch(
            PREPARE_TARGET,
            return_value={"runtime": {}, "agents": {"plans": []}},
        ) as prepare:
            call(str(self.project))
        self.assertTrue(prepare.called)
        self.assertEqual(prepare.call_args.kwargs["import_paths"], [Path.cwd()])

    def test_runtime_pool_route_is_injected(self) -> None:
        with mock.patch(
            PREPARE_TARGET,
            return_value={"runtime": {}, "agents": {"plans": []}},
        ) as prepare:
            call(str(self.project))
        kwargs = prepare.call_args.kwargs
        self.assertIsNotNone(kwargs["runtime_pool_root"])
        self.assertTrue(str(kwargs["runtime_pool_id"]).strip())


if __name__ == "__main__":
    unittest.main()
