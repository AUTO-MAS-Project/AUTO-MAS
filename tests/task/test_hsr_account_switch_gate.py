"""切号只能走 SRA，缺 SRA 路径时不能一声不吭地跳过。

`_build_login_plan`（`AutoProxy.py`）在 SRA 路径为空时直接返回 `m7a_fallback`，
**不看** `user_needs_account_switch()`。往下 `uses_sra_start_game` 为假 →
队列里不插 StartGame → `ensure_game_started_by_mas` 见游戏已在运行就「跳过重复
启动」。结果是多个用户全跑在同一个已登录账号上，不报错不告警，完成态还按各自
MAS 用户写回。

这个洞一直都在，但此前 M7A-only 脚本会被 `check()` 整个拦死，踩不到；修完引擎
回落（`8bd3e7fb`）之后「只填三月七路径」成了一等公民形态，它就从偏门变成顺手
能踩。

判据只在**确实配了账号密码**时才生效：没配账密的用户本来就依赖游戏当前登录
态，有没有 SRA 都是同一个账号，不该被这条拦住。

直控用户不计入——计数点在 `check()` 里直控分支 `continue` 之后。
"""

import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.core.task_manager import TaskInfo
from app.models.config import HSRConfig, HSRUserConfig
from app.models.task import ScriptItem
from app.task.HSR.manager import HSRManager


async def build_script(*, m7a_root, sra_root, game_exe, users):
    """users: [(名字, 是否配了账密), ...]"""

    script_uid = uuid.uuid4()
    script_config = HSRConfig()
    await script_config.update(
        {
            "Info": {
                "Name": "测试 HSR",
                "M7APath": str(m7a_root),
                "SRAPath": str(sra_root) if sra_root else "",
            },
            "Game": {"Enabled": True, "Path": str(game_exe)},
        }
    )

    for name, with_credentials in users:
        _, user_cfg = await script_config.UserData.add(HSRUserConfig)
        info = {"Name": name, "Status": True, "RemainedDay": -1}
        if with_credentials:
            info["Id"] = f"{name}@example.com"
            info["Password"] = "pw-" + name
        await user_cfg.update({"Info": info})

    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-id",
        queue_id=None,
        script_id=str(script_uid),
        user_id=None,
    )
    script_item = ScriptItem(script_id=str(script_uid), name="测试 HSR", status="运行")
    task_info.script_list = [script_item]
    return HSRManager(script_item), script_uid, script_config


class AccountSwitchGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.m7a_root = root / "March7thAssistant"
        self.m7a_root.mkdir(parents=True)
        (self.m7a_root / "March7th Assistant.exe").write_bytes(b"")
        (self.m7a_root / "config.yaml").write_text(
            "instance_type: CalyxGolden" + chr(10), encoding="utf-8"
        )
        self.sra_root = root / "StarRailAssistant"
        self.sra_root.mkdir(parents=True)
        (self.sra_root / "SRA-cli.exe").write_bytes(b"")
        self.game_exe = root / "StarRail.exe"
        self.game_exe.write_bytes(b"")

    def _run(self, *, users, with_sra: bool):
        async def go():
            manager, script_uid, config = await build_script(
                m7a_root=self.m7a_root,
                sra_root=self.sra_root if with_sra else None,
                game_exe=self.game_exe,
                users=users,
            )
            with mock.patch.object(
                app.core.Config, "ScriptConfig", {script_uid: config}
            ):
                return await manager.check(), manager

        return asyncio.run(go())

    def test_two_credentialed_users_without_sra_are_blocked(self) -> None:
        result, _ = self._run(
            users=[("甲", True), ("乙", True)], with_sra=False
        )
        self.assertNotEqual(result, "Pass")
        self.assertIn("SRA", result)
        self.assertIn("同一个已登录账号", result)

    def test_two_credentialed_users_pass_once_sra_is_configured(self) -> None:
        result, _ = self._run(users=[("甲", True), ("乙", True)], with_sra=True)
        self.assertEqual(result, "Pass", result)

    def test_mixed_users_are_blocked_too(self) -> None:
        """一个配了账密一个没配，切号照样被静默跳过。"""

        result, _ = self._run(
            users=[("甲", True), ("乙", False)], with_sra=False
        )
        self.assertNotEqual(result, "Pass")
        self.assertIn("SRA", result)

    def test_users_without_credentials_are_not_blocked(self) -> None:
        """都没配账密时有没有 SRA 都是同一个账号，不该被这条拦住。"""

        result, _ = self._run(
            users=[("甲", False), ("乙", False)], with_sra=False
        )
        self.assertEqual(result, "Pass", result)

    def test_single_credentialed_user_passes_with_a_warning(self) -> None:
        result, manager = self._run(users=[("甲", True)], with_sra=False)
        self.assertEqual(result, "Pass", result)
        joined = chr(10).join(manager._log_lines)
        self.assertIn("未配置 SRA 路径", joined)
        self.assertIn("当前已登录的账号", joined)

    def test_single_user_with_sra_gets_no_warning(self) -> None:
        result, manager = self._run(users=[("甲", True)], with_sra=True)
        self.assertEqual(result, "Pass", result)
        self.assertNotIn("未配置 SRA 路径", chr(10).join(manager._log_lines))


if __name__ == "__main__":
    unittest.main()
