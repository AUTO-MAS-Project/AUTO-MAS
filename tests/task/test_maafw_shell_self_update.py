import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.core  # noqa: F401

from app.task.MaaFW import manager as manager_module
from app.task.MaaFW.manager import MaaFWManager


class DisableShellSelfUpdateTest(unittest.TestCase):
    """MXU 的自动更新闸门在 interface.json 里，不在外壳设置里。

    MXU src/App.tsx 的条件是 ``interface.mirrorchyan_rid && interface.version``；
    UI 里没有对应开关，所以只能从 interface.json 下手。一旦开始下载，MXU 会把
    待跑任务挂起等安装重启（autoStartTasksPending → pendingAutoTasksRef）——
    2026-08-29 真机实测就是这样把整轮任务顶掉的。
    """

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.path = self.root / "interface.json"
        self.original = {
            "interface_version": 2,
            "name": "MaaEnd",
            "version": "v2.22.0",
            "github": "https://github.com/MaaEnd/MaaEnd",
            "mirrorchyan_rid": "MaaEnd",
            "task": [{"name": "打开游戏"}],
        }
        self._write(self.original)

        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.project_root = self.root

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_removes_only_the_update_gate_key(self) -> None:
        self.manager._disable_shell_self_update()
        written = self._read()

        self.assertNotIn("mirrorchyan_rid", written)
        # version 还要参与界面显示与遥测，不能动；其余字段逐一保持。
        self.assertEqual(written["version"], "v2.22.0")
        self.assertEqual(written["task"], self.original["task"])
        self.assertEqual(written["github"], self.original["github"])
        self.assertEqual(len(written), len(self.original) - 1)

    def test_round_trip_restores_the_key(self) -> None:
        snapshot = self.manager._snapshot_interface_update_keys()
        self.manager._disable_shell_self_update()
        self.manager._restore_interface_update_keys(snapshot)
        self.assertEqual(self._read(), self.original)

    def test_restore_deletes_a_key_the_project_never_had(self) -> None:
        # 项目本来就没有 rid（比如自建项目），跑完不能凭空多出来一个。
        self._write({k: v for k, v in self.original.items() if k != "mirrorchyan_rid"})
        snapshot = self.manager._snapshot_interface_update_keys()
        self.assertEqual(snapshot, {})
        self._write(self.original)
        self.manager._restore_interface_update_keys(snapshot)
        self.assertNotIn("mirrorchyan_rid", self._read())

    def test_old_manifest_without_the_field_is_a_no_op(self) -> None:
        # 旧版 manifest 没有这个字段，按既有行为跳过而不是报错。
        self.manager._restore_interface_update_keys(None)
        self.assertEqual(self._read(), self.original)

    def test_missing_interface_file_is_tolerated(self) -> None:
        self.path.unlink()
        self.assertEqual(self.manager._snapshot_interface_update_keys(), {})
        self.manager._disable_shell_self_update()
        self.manager._restore_interface_update_keys({"mirrorchyan_rid": "MaaEnd"})

    def test_write_failure_never_breaks_the_run(self) -> None:
        # 关不掉更新最多是这一轮被外壳顶掉，不该让运行本身直接失败。
        with patch.object(
            manager_module,
            "atomic_write_maafw_config",
            side_effect=PermissionError("locked"),
        ):
            self.manager._disable_shell_self_update()
        self.assertEqual(self._read(), self.original)


if __name__ == "__main__":
    unittest.main()
