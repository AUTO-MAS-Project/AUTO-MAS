"""HSR 模块引擎归属的四级回落回归。

`get_assigned_script` 的第四级是「按 `effective_engines` 收敛」：分配到的引擎
没配置路径时，改取 `supported_scripts` 里第一个已配置的引擎。能力快照一直在
传这一级，`check()` 与自动代理队列却没传——于是编辑页徽章显示三月七、运行时
却按脚本级默认值 SRA 解析，只填 M7A 路径的用户被自己看不到的归属拦下。

本文件用真实 `HSRConfig` + `HSRUserConfig` 和临时脚本目录，把 UI 侧与运行时侧
的归属放在一起断言，不起子进程、不碰真实 M7A/SRA 安装。
"""

import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.core.task_manager import TaskInfo
from app.models.ConfigBase import MultipleConfig
from app.models.config import HSRConfig, HSRUserConfig
from app.models.task import ScriptItem, UserItem
from app.task.HSR.AutoProxy import HSRAutoProxyTask
from app.task.HSR.manager import HSRManager
from app.task.HSR.task_mapping import HSR_TASK_MODULE_MAP, get_assigned_script
from app.task.HSR.tools.api import build_managed_config
from app.task.HSR.tools.m7a_runtime import M7ARunner
from app.task.HSR.tools.native_control import resolve_configured_engines
from app.task.HSR.tools.run_model import HSRRuntimeState

DAILY = HSR_TASK_MODULE_MAP["Daily"]


def make_m7a_root(root: Path) -> Path:
    """造一份能过 check() 的最小 M7A 安装。"""

    root.mkdir(parents=True, exist_ok=True)
    (root / "March7th Assistant.exe").write_bytes(b"")
    (root / "config.yaml").write_text("instance_type: CalyxGolden\n", encoding="utf-8")
    return root


def make_sra_root(root: Path) -> Path:
    """造一份最小 SRA 安装。"""

    root.mkdir(parents=True, exist_ok=True)
    (root / "SRA-cli.exe").write_bytes(b"")
    return root


async def build_script(
    *,
    m7a_root: Path | None,
    sra_root: Path | None,
    game_exe: Path | None,
) -> tuple[HSRManager, uuid.UUID, HSRConfig, HSRUserConfig]:
    script_uid = uuid.uuid4()
    script_config = HSRConfig()
    await script_config.update(
        {
            "Info": {
                "Name": "测试 HSR",
                "M7APath": str(m7a_root) if m7a_root else "",
                "SRAPath": str(sra_root) if sra_root else "",
            },
            "Game": {
                "Enabled": bool(game_exe),
                "Path": str(game_exe) if game_exe else "",
            },
        }
    )

    _, user_cfg = await script_config.UserData.add(HSRUserConfig)
    await user_cfg.update(
        {"Info": {"Name": "hsr-m7a", "Status": True, "RemainedDay": -1}}
    )

    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-id",
        queue_id=None,
        script_id=str(script_uid),
        user_id=None,
    )
    script_item = ScriptItem(script_id=str(script_uid), name="测试 HSR", status="运行")
    task_info.script_list = [script_item]
    return HSRManager(script_item), script_uid, script_config, user_cfg


async def build_auto_proxy(
    manager: HSRManager, script_config: HSRConfig
) -> HSRAutoProxyTask:
    """按 HSRManager.prepare() 的形状装配单用户自动代理任务。"""

    user_config: MultipleConfig[HSRUserConfig] = MultipleConfig([HSRUserConfig])
    await user_config.load(await script_config.UserData.toDict(if_decrypt=False))
    uid = next(iter(user_config.data))
    user_item = UserItem(
        user_id=str(uid),
        name=user_config[uid].get("Info", "Name"),
        status="等待",
    )
    manager.script_info.user_list = [user_item]
    return HSRAutoProxyTask(
        manager.script_info,
        script_config,
        user_config,
        user_item,
        HSRRuntimeState(log_lines=[], completion_writebacks=[]),
    )


class HSREngineFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.m7a_root = make_m7a_root(root / "March7thAssistant")
        self.sra_root = make_sra_root(root / "StarRailAssistant")
        self.game_exe = root / "StarRail.exe"
        self.game_exe.write_bytes(b"")

    def _build(self, **kwargs):
        return asyncio.run(build_script(**kwargs))

    def _check(self, manager: HSRManager, script_uid: uuid.UUID, config: HSRConfig):
        async def go():
            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ):
                return await manager.check()

        return asyncio.run(go())

    def test_m7a_only_script_does_not_demand_an_sra_path(self) -> None:
        """只填三月七路径时，check() 不得因脚本级默认值 SRA 拦下用户。"""

        manager, script_uid, config, _ = self._build(
            m7a_root=self.m7a_root, sra_root=None, game_exe=self.game_exe
        )
        # 复现现场：脚本级 TaskMapping 保持出厂默认 SRA，用户没有任何覆盖。
        self.assertEqual(config.get("TaskMapping", "Daily"), "SRA")

        result = self._check(manager, script_uid, config)
        self.assertEqual(result, "Pass", result)

    def test_badge_and_runtime_resolve_to_the_same_engine(self) -> None:
        """编辑页徽章读的归属必须与运行时解析出的归属一致。"""

        _, _, config, user_cfg = self._build(
            m7a_root=self.m7a_root, sra_root=None, game_exe=self.game_exe
        )

        badge_engine = build_managed_config(config, user_cfg)["task_mapping"]["Daily"]
        runtime_engine = get_assigned_script(
            DAILY,
            config,
            user_config=user_cfg,
            effective_engines=resolve_configured_engines(config),
        )

        self.assertEqual(badge_engine, "M7A")
        self.assertEqual(runtime_engine, badge_engine)

    def test_auto_proxy_queue_targets_the_configured_engine(self) -> None:
        """队列构建同样要收敛，否则 check() 放行后仍会去跑不存在的 SRA-cli。"""

        async def go():
            manager, _, config, user_cfg = await build_script(
                m7a_root=self.m7a_root, sra_root=None, game_exe=self.game_exe
            )
            await user_cfg.set("TaskSwitch", "DivergentUniverse", True)
            task = await build_auto_proxy(manager, config)
            return task._build_phase_items(
                phase="weekly",
                user_item=task.cur_user_item,
                user_cfg=task.cur_user_config,
                user_name="hsr-m7a",
                uid=str(task.cur_user_uid),
                m7a_path=str(self.m7a_root),
                m7a_runner=M7ARunner(self.m7a_root),
                sra_exe_path=Path("") / "SRA-cli.exe",
                script_id="script-id",
                temp_files=[],
                daily_eow_enabled=False,
            )

        items = asyncio.run(go())
        self.assertEqual([item.module_key for item in items], ["DivergentUniverse"])
        self.assertEqual(items[0].script, "M7A")

    def test_sra_only_script_falls_back_from_a_stored_m7a_mapping(self) -> None:
        """反向同理：只填 SRA 路径时，分配到 M7A 的模块收敛回 SRA。"""

        _, _, config, user_cfg = self._build(
            m7a_root=None, sra_root=self.sra_root, game_exe=self.game_exe
        )
        asyncio.run(config.set("TaskMapping", "Daily", "M7A"))

        self.assertEqual(resolve_configured_engines(config), ("SRA",))
        self.assertEqual(
            get_assigned_script(
                DAILY,
                config,
                user_config=user_cfg,
                effective_engines=resolve_configured_engines(config),
            ),
            "SRA",
        )

    def test_configured_engine_keeps_the_stored_mapping(self) -> None:
        """两条路径都填时，回落不得覆盖用户选定的归属。"""

        _, _, config, user_cfg = self._build(
            m7a_root=self.m7a_root, sra_root=self.sra_root, game_exe=self.game_exe
        )
        asyncio.run(config.set("TaskMapping", "Daily", "M7A"))

        self.assertEqual(resolve_configured_engines(config), ("M7A", "SRA"))
        self.assertEqual(
            get_assigned_script(
                DAILY,
                config,
                user_config=user_cfg,
                effective_engines=resolve_configured_engines(config),
            ),
            "M7A",
        )

    def test_user_override_still_wins_over_the_script_mapping(self) -> None:
        """用户级 Managed.TaskMapping 仍是第一级，回落不得越过它。"""

        _, _, config, user_cfg = self._build(
            m7a_root=self.m7a_root, sra_root=self.sra_root, game_exe=self.game_exe
        )
        asyncio.run(config.set("TaskMapping", "Daily", "M7A"))
        # Managed.TaskMapping 走 JSONValidator，落盘形状是 JSON 字符串。
        asyncio.run(
            user_cfg.set("Managed", "TaskMapping", json.dumps({"Daily": "SRA"}))
        )

        self.assertEqual(
            get_assigned_script(
                DAILY,
                config,
                user_config=user_cfg,
                effective_engines=resolve_configured_engines(config),
            ),
            "SRA",
        )


if __name__ == "__main__":
    unittest.main()
