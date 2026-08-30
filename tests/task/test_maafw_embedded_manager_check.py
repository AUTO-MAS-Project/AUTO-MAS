"""`MaaFWEmbeddedManager.check()` 的整装回归。

装配层（脚本配置 / 用户配置 / 模拟器实例 → AutoProxy 任务）是本次移植新写的
代码，插件侧对应物 `adapter.py` 依赖 `app.plugins` 未移植。本文件用真实的
`MaaFWConfig` + `MaaFWUserConfig` + 临时项目把 check() 从头走一遍。

不联网、不起子进程、不实例化 `Tasker`/`Controller`、不碰设备。
"""

import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.core.task_manager import TaskInfo
from app.models.task import ScriptItem
from app.task.MaaFW.embedded_manager import MaaFWEmbeddedManager

REPO_ROOT = Path(__file__).resolve().parents[2]

INTERFACE = {
    "interface_version": 2,
    "name": "Demo",
    "version": "v1.0.0",
    "controller": [
        {"name": "桌面端", "type": "Win32", "win32": {"window_regex": "Demo"}},
        {"name": "安卓端", "type": "Adb"},
    ],
    "resource": [{"name": "简中", "path": ["{PROJECT_DIR}/resource/base"]}],
    "task": [
        {"name": "启动游戏", "entry": "StartUp", "default_check": True},
        {"name": "日常", "entry": "Daily", "default_check": True},
    ],
}


def make_project(root: Path) -> Path:
    (root / "resource" / "base").mkdir(parents=True, exist_ok=True)
    (root / "interface.json").write_text(
        json.dumps(INTERFACE, ensure_ascii=False), encoding="utf-8"
    )
    return root


async def build_manager(
    project: Path,
    *,
    emulator_id: str = "",
) -> tuple[MaaFWEmbeddedManager, uuid.UUID, MaaFWConfig]:
    script_uid = uuid.uuid4()
    script_config = MaaFWConfig()
    await script_config.update(
        {
            "Info": {
                "Name": "测试 MaaFW",
                "Path": str(project),
                "Controller": "桌面端",
                "Resource": "简中",
            },
        }
    )
    if emulator_id:
        await script_config.update({"Emulator": {"Id": emulator_id}})

    _, user_cfg = await script_config.UserData.add(MaaFWUserConfig)
    tasks = ["启动游戏"]
    await user_cfg.update(
        {
            "Info": {"Name": "用户A", "Status": True, "RemainedDay": -1},
            "Task": {
                "SelectedPreset": "",
                "TaskSnapshot": json.dumps(
                    {
                        "taskOrder": tasks,
                        "taskChecked": {name: True for name in tasks},
                        "taskOptions": {},
                    },
                    ensure_ascii=False,
                ),
            },
        }
    )

    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-id",
        queue_id=None,
        script_id=str(script_uid),
        user_id=None,
    )
    script_item = ScriptItem(
        script_id=str(script_uid), name="测试 MaaFW", status="运行"
    )
    task_info.script_list = [script_item]
    return MaaFWEmbeddedManager(script_item), script_uid, script_config


class EmbeddedManagerCheckIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = make_project(Path(self._tmp.name) / "project")

    def _run_check(
        self, project: Path | None = None, **kwargs
    ) -> tuple[str, MaaFWEmbeddedManager]:
        async def go():
            manager, script_uid, config = await build_manager(
                project if project is not None else self.project, **kwargs
            )
            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ):
                return await manager.check(), manager

        return asyncio.run(go())

    def test_a_well_formed_script_passes_the_gate(self) -> None:
        result, manager = self._run_check()
        self.assertEqual(result, "Pass")
        self.assertIsNotNone(manager.script_config)
        self.assertIsNotNone(manager.user_config)
        self.assertEqual(len(manager.user_config.data), 1)
        self.assertEqual(len(manager.runnable_user_uids), 1)

    def test_disabled_user_is_not_runnable(self) -> None:
        async def go():
            manager, script_uid, config = await build_manager(self.project)
            users = config.UserData
            for uid in list(users.data):
                await users[uid].set("Info", "Status", False)
            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ):
                return await manager.check()

        result = asyncio.run(go())
        self.assertNotEqual(result, "Pass")
        self.assertIn("可运行的用户", result)

    def test_expired_user_is_not_runnable(self) -> None:
        async def go():
            manager, script_uid, config = await build_manager(self.project)
            users = config.UserData
            for uid in list(users.data):
                await users[uid].set("Info", "RemainedDay", 0)
            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ):
                return await manager.check()

        result = asyncio.run(go())
        self.assertNotEqual(result, "Pass")
        self.assertIn("可运行的用户", result)

    def test_missing_project_directory_is_refused(self) -> None:
        async def go():
            manager, script_uid, config = await build_manager(self.project)
            await config.update({"Info": {"Path": str(self.project / "nope")}})
            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ):
                return await manager.check()

        result = asyncio.run(go())
        self.assertNotEqual(result, "Pass")
        self.assertIn("interface.json", result)

    def test_no_emulator_configured_yields_none_not_a_failure(self) -> None:
        """Win32 项目不需要模拟器，缺模拟器不得在装配层就拦下。"""

        result, manager = self._run_check()
        self.assertEqual(result, "Pass")
        self.assertIsNone(manager.emulator_manager)

    def test_unresolvable_emulator_degrades_instead_of_failing(self) -> None:
        """取模拟器实例失败只记 warning，由运行编排层给可读错误。"""

        async def go():
            manager, script_uid, config = await build_manager(
                self.project, emulator_id="no-such-emulator"
            )
            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ):
                return await manager.check(), manager

        result, manager = asyncio.run(go())
        self.assertEqual(result, "Pass")
        self.assertIsNone(manager.emulator_manager)

    def test_inner_task_is_only_built_after_a_passing_check(self) -> None:
        _, manager = self._run_check(project=self.project / "nope")
        self.assertIsNone(manager.inner_task)

    def test_final_task_is_safe_before_any_run(self) -> None:
        _, manager = self._run_check(project=self.project / "nope")
        asyncio.run(manager.final_task())  # 不得抛

    def test_on_crash_without_inner_task_marks_the_script(self) -> None:
        _, manager = self._run_check(project=self.project / "nope")
        asyncio.run(manager.on_crash(RuntimeError("boom")))
        self.assertEqual(manager.script_info.status, "异常")


class EmbeddedManagerUserLoopTest(unittest.TestCase):
    """逐用户循环 —— 移植期间漏掉过，是会直接炸运行期的那类缺陷。

    `task_manager` 给每个 ScriptItem 只放一个「暂未加载」占位 UserItem；
    真实用户列表必须由 manager 自己填。AutoProxy 按 `current_index` 取
    `user_list[i]` 并用它的 user_id 去查 user_config，不填就会拿占位项的
    随机 uid 去查，必然 KeyError。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = make_project(Path(self._tmp.name) / "project")

    def _run_main_task(self, user_names: list[str]):
        built: list[mock.Mock] = []
        seen_indexes: list[int] = []
        seen_user_ids: list[str] = []

        async def go():
            script_uid = uuid.uuid4()
            config = MaaFWConfig()
            await config.update(
                {
                    "Info": {
                        "Name": "测试 MaaFW",
                        "Path": str(self.project),
                        "Controller": "桌面端",
                        "Resource": "简中",
                    },
                                    }
            )
            for name in user_names:
                _, user_cfg = await config.UserData.add(MaaFWUserConfig)
                await user_cfg.update(
                    {"Info": {"Name": name, "Status": True, "RemainedDay": -1}}
                )
            task_info = TaskInfo(
                mode="AutoProxy",
                task_id="task-id",
                queue_id=None,
                script_id=str(script_uid),
                user_id=None,
            )
            item = ScriptItem(
                script_id=str(script_uid),
                name="测试 MaaFW",
                status="运行",
                user_list=[],
            )
            task_info.script_list = [item]
            manager = MaaFWEmbeddedManager(item)

            def fake_build():
                # 构造时按 AutoProxy 的真实契约取当前用户
                index = manager.script_info.current_index
                current = manager.script_info.user_list[index]
                seen_indexes.append(index)
                seen_user_ids.append(current.user_id)
                # 关键断言：这个 uid 必须能在 user_config 里查到
                assert uuid.UUID(current.user_id) in manager.user_config.data
                task = mock.Mock()
                task.main_task = mock.AsyncMock()
                task.final_task = mock.AsyncMock()
                task.on_crash = mock.AsyncMock()
                built.append(task)
                return task

            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ), mock.patch.object(manager, "_build_inner_task", fake_build):
                await manager.main_task()
            return manager

        manager = asyncio.run(go())
        return manager, built, seen_indexes, seen_user_ids

    def test_placeholder_user_list_is_replaced_with_real_users(self) -> None:
        manager, _, _, _ = self._run_main_task(["用户A", "用户B"])
        self.assertEqual(
            [user.name for user in manager.script_info.user_list],
            ["用户A", "用户B"],
        )
        for user in manager.script_info.user_list:
            self.assertIn(uuid.UUID(user.user_id), manager.user_config.data)

    def test_one_autoproxy_task_per_user_with_advancing_index(self) -> None:
        _, built, indexes, user_ids = self._run_main_task(["用户A", "用户B", "用户C"])
        self.assertEqual(len(built), 3)
        self.assertEqual(indexes, [0, 1, 2])
        self.assertEqual(len(set(user_ids)), 3)
        for task in built:
            task.main_task.assert_awaited_once()
            # final_task 是按用户结算的，每个用户都必须收尾
            task.final_task.assert_awaited_once()

    def test_a_crashing_user_does_not_stop_the_rest(self) -> None:
        built: list[mock.Mock] = []

        async def go():
            script_uid = uuid.uuid4()
            config = MaaFWConfig()
            await config.update(
                {
                    "Info": {
                        "Name": "测试 MaaFW",
                        "Path": str(self.project),
                        "Controller": "桌面端",
                        "Resource": "简中",
                    },
                                    }
            )
            for name in ("用户A", "用户B"):
                _, user_cfg = await config.UserData.add(MaaFWUserConfig)
                await user_cfg.update(
                    {"Info": {"Name": name, "Status": True, "RemainedDay": -1}}
                )
            task_info = TaskInfo(
                mode="AutoProxy",
                task_id="task-id",
                queue_id=None,
                script_id=str(script_uid),
                user_id=None,
            )
            item = ScriptItem(
                script_id=str(script_uid), name="测试 MaaFW", status="运行", user_list=[]
            )
            task_info.script_list = [item]
            manager = MaaFWEmbeddedManager(item)

            def fake_build():
                task = mock.Mock()
                task.main_task = mock.AsyncMock(
                    side_effect=RuntimeError("boom") if not built else None
                )
                task.final_task = mock.AsyncMock()
                task.on_crash = mock.AsyncMock()
                built.append(task)
                return task

            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ), mock.patch.object(manager, "_build_inner_task", fake_build):
                await manager.main_task()

        asyncio.run(go())
        self.assertEqual(len(built), 2)
        built[0].on_crash.assert_awaited_once()
        built[0].final_task.assert_awaited_once()
        built[1].main_task.assert_awaited_once()
        built[1].final_task.assert_awaited_once()

    def _finalize_with_statuses(self, manager, statuses: list[str]) -> None:
        """在同一个事件循环里改用户状态并收尾。

        直接在循环外改 UserItem.status 会触发 TaskItem.schedule_on_change，
        它要 create_task，没有运行中的循环就抛 RuntimeError。
        """

        async def go():
            for user, status in zip(manager.script_info.user_list, statuses):
                user.status = status
            # 内层任务已在用户循环里收过尾，这里只验脚本终态
            manager._inner_finalized = True
            await manager.final_task()

        asyncio.run(go())

    def test_script_status_becomes_done_when_all_users_succeed(self) -> None:
        manager, *_ = self._run_main_task(["用户A", "用户B"])
        self._finalize_with_statuses(manager, ["完成", "完成"])
        # 不置终态的话任务结束后脚本行会一直停在「运行」
        self.assertEqual(manager.script_info.status, "完成")

    def test_script_status_becomes_error_when_a_user_failed(self) -> None:
        manager, *_ = self._run_main_task(["用户A", "用户B"])
        self._finalize_with_statuses(manager, ["完成", "异常"])
        self.assertEqual(manager.script_info.status, "异常")

    def test_users_left_running_are_marked_error_and_fail_the_script(self) -> None:
        manager, *_ = self._run_main_task(["用户A"])
        self._finalize_with_statuses(manager, ["运行"])
        self.assertEqual(manager.script_info.user_list[0].status, "异常")
        self.assertEqual(manager.script_info.status, "异常")

    def test_final_task_does_not_finalize_twice(self) -> None:
        manager, built, _, _ = self._run_main_task(["用户A"])
        asyncio.run(manager.final_task())
        built[-1].final_task.assert_awaited_once()


class RuntimePoolRouteInjectionTest(unittest.TestCase):
    """Runtime Pool 路由注入 —— 不注入 `_run_maafw` 会直接拒绝运行。

    插件形态下由 `adapter.py` 查 `maafw.runtime_pool.v1` 服务契约后注入；
    该文件依赖 app.plugins 未移植，树内改为直接实例化服务。移植期间漏过这一步，
    表现为运行时报「缺少由 maafw.runtime_pool.v1 注入的 root/poolId」。
    """

    def test_route_resolves_to_a_root_and_pool_id(self) -> None:
        route = MaaFWEmbeddedManager._resolve_runtime_pool_route()
        self.assertTrue(str(route.root))
        self.assertTrue(str(route.pool_id).strip())

    def test_build_inner_task_injects_the_route(self) -> None:
        captured = {}

        class FakeAutoProxy:
            def __init__(self, script_info, script_config, user_config, emulator):
                captured["args"] = (script_info, script_config, user_config, emulator)
                self.maafw_runtime_pool_root = None
                self.maafw_runtime_pool_id = None

        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp) / "project")

            async def go():
                manager, script_uid, config = await build_manager(project)
                with mock.patch.object(
                    app.core.Config, "ScriptConfig", {script_uid: config}
                ):
                    self.assertEqual(await manager.check(), "Pass")
                with mock.patch(
                    "app.task.MaaFW.tools.embedded.runner_task."
                    "MaaFWPluginAutoProxyTask",
                    FakeAutoProxy,
                ):
                    return manager._build_inner_task()

            task = asyncio.run(go())

        self.assertIsNotNone(task.maafw_runtime_pool_root)
        self.assertTrue(str(task.maafw_runtime_pool_id or "").strip())
        # 装配层传给 AutoProxy 的四个位置参数
        self.assertEqual(len(captured["args"]), 4)

    def test_run_maafw_guard_still_reads_both_fields(self) -> None:
        """守卫还在，说明这条注入是必需的而不是可选的。"""

        source = (
            REPO_ROOT
            / "app/task/MaaFW/tools/embedded/runner_task.py"
        ).read_text(encoding="utf-8")
        self.assertIn("runtime_pool_root = self.maafw_runtime_pool_root", source)
        self.assertIn("maafw.runtime_pool.v1", source)


class EmbeddedManagerAgainstRealProjectTest(unittest.TestCase):
    """对真实项目做一次装配（若本机备有靶子，否则跳过）。"""

    TARGET = Path("D:/MAS/tmp/maafw-embedded-target/M9A-win-x86_64-v4.7.1-MFAA")

    def setUp(self) -> None:
        if not (self.TARGET / "interface.json").is_file():
            self.skipTest(f"本机没有靶子：{self.TARGET}")

    def test_check_passes_against_a_real_project(self) -> None:
        async def go():
            script_uid = uuid.uuid4()
            config = MaaFWConfig()
            await config.update(
                {
                    "Info": {
                        "Name": "M9A",
                        "Path": str(self.TARGET),
                        "Controller": "PC",
                        "Resource": "官服",
                    },
                                    }
            )
            _, user_cfg = await config.UserData.add(MaaFWUserConfig)
            tasks = ["收取荒原"]
            await user_cfg.update(
                {
                    "Info": {"Name": "用户A", "Status": True, "RemainedDay": -1},
                    "Task": {
                        "TaskSnapshot": json.dumps(
                            {
                                "taskOrder": tasks,
                                "taskChecked": {name: True for name in tasks},
                                "taskOptions": {},
                            },
                            ensure_ascii=False,
                        )
                    },
                }
            )
            task_info = TaskInfo(
                mode="AutoProxy",
                task_id="task-id",
                queue_id=None,
                script_id=str(script_uid),
                user_id=None,
            )
            item = ScriptItem(script_id=str(script_uid), name="M9A", status="运行")
            task_info.script_list = [item]
            manager = MaaFWEmbeddedManager(item)
            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ):
                return await manager.check()

        self.assertEqual(asyncio.run(go()), "Pass")


if __name__ == "__main__":
    unittest.main()
