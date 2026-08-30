"""`Run.Engine` 的 API / 持久化往返。

阶段 5 放宽了 `MaaFWConfig_Run.Engine` 的 Literal 并据此重新生成了前端客户端。
本文件把「前端能提交什么、后端存下什么、重启后读回什么」这条链走一遍，
覆盖 DTO 校验、ConfigItem 校验器与磁盘往返三处。
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from app.core.config import AppConfig
from app.models.config import GlobalConfig, MaaFWConfig
from app.models.schema import MaaFWConfig as MaaFWConfigDTO
from app.models.schema import MaaFWConfig_Run


class RunEngineDtoTest(unittest.TestCase):
    def test_dto_defaults_to_external(self) -> None:
        self.assertEqual(MaaFWConfig_Run().Engine, "external")
        # 顶层 DTO 的各分节是可选的（支持部分更新），给了 Run 才有 Engine
        self.assertIsNone(MaaFWConfigDTO().Run)
        self.assertEqual(MaaFWConfigDTO(Run={}).Run.Engine, "external")

    def test_dto_accepts_embedded(self) -> None:
        payload = MaaFWConfigDTO.model_validate({"Run": {"Engine": "embedded"}})
        self.assertEqual(payload.Run.Engine, "embedded")

    def test_dto_rejects_an_unknown_engine(self) -> None:
        for bogus in ("managed", "Embedded", "", None, 1):
            with self.subTest(engine=bogus):
                with self.assertRaises(ValidationError):
                    MaaFWConfig_Run(Engine=bogus)

    def test_generated_client_exposes_both_engines(self) -> None:
        """前端生成物必须同步，否则 UI 下拉提交的值前端类型层就先红。"""

        model = (
            Path(__file__).resolve().parents[2]
            / "frontend/src/api/models/MaaFWConfig_Run.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("EXTERNAL = 'external'", model)
        self.assertIn("EMBEDDED = 'embedded'", model)


class RunEnginePersistenceTest(unittest.TestCase):
    def test_engine_round_trips_through_disk(self) -> None:
        asyncio.run(self._round_trip())

    async def _round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as manager_dir:
            manager_root = Path(manager_dir)
            with patch("app.core.config.Path.cwd", return_value=manager_root):
                manager = AppConfig()
                script_uid, script = await manager.add_script("MaaFW")
                # 新建脚本必须默认走第一层
                self.assertEqual(script.get("Run", "Engine"), "external")

                await script.update({"Run": {"Engine": "embedded"}})
                self.assertEqual(script.get("Run", "Engine"), "embedded")
                persisted = await manager.ScriptConfig.toDict(if_decrypt=False)

            restored = GlobalConfig()
            await restored.ScriptConfig.load(persisted)
            restored_script = restored.ScriptConfig[script_uid]
            self.assertIsInstance(restored_script, MaaFWConfig)
            self.assertEqual(restored_script.get("Run", "Engine"), "embedded")

    def test_switching_back_to_external_round_trips(self) -> None:
        asyncio.run(self._round_trip_back())

    async def _round_trip_back(self) -> None:
        with tempfile.TemporaryDirectory() as manager_dir:
            manager_root = Path(manager_dir)
            with patch("app.core.config.Path.cwd", return_value=manager_root):
                manager = AppConfig()
                script_uid, script = await manager.add_script("MaaFW")
                await script.update({"Run": {"Engine": "embedded"}})
                await script.update({"Run": {"Engine": "external"}})
                persisted = await manager.ScriptConfig.toDict(if_decrypt=False)

            restored = GlobalConfig()
            await restored.ScriptConfig.load(persisted)
            self.assertEqual(
                restored.ScriptConfig[script_uid].get("Run", "Engine"), "external"
            )

    def test_unknown_engine_on_disk_is_corrected_not_propagated(self) -> None:
        """手改过配置文件的用户不该因为一个错值就掉进未知分支。"""

        asyncio.run(self._corrupt_engine())

    async def _corrupt_engine(self) -> None:
        with tempfile.TemporaryDirectory() as manager_dir:
            manager_root = Path(manager_dir)
            with patch("app.core.config.Path.cwd", return_value=manager_root):
                manager = AppConfig()
                script_uid, _ = await manager.add_script("MaaFW")
                persisted = await manager.ScriptConfig.toDict(if_decrypt=False)

            payload = json.loads(json.dumps(persisted))
            entry = payload[str(script_uid)]
            entry.setdefault("Run", {})["Engine"] = "totally-bogus"

            restored = GlobalConfig()
            await restored.ScriptConfig.load(payload)
            engine = restored.ScriptConfig[script_uid].get("Run", "Engine")
            self.assertIn(engine, ("external", "embedded"))
            self.assertNotEqual(engine, "totally-bogus")


if __name__ == "__main__":
    unittest.main()
