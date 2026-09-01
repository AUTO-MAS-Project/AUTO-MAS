"""`automas_maafw_agent_env` 复用隔离 venv 前的基解释器校验。

背景：受管模式下（AUTO-MAS-Runtime 用 Job Object 监督后端）
``_venv_bootstrap_python()`` 落到 ``sys.executable``（监督器管理的那个
venv）时，若监督器之后 repair/rebuild 了那个 venv，用它建出来的隔离 venv 的
``pyvenv.cfg`` 里 ``home`` 会指向一个已经不存在的目录，venv 从此静默失效
（Windows 上 venv 自己的 python.exe 是个重定向存根，要靠 home 才能定位标准
库所在的 DLL/Lib，home 目录一旦被删，venv 自己的文件即使还在也起不来）。
"""

import os
import tempfile
import unittest
from pathlib import Path

from app.task.MaaFW.tools.core.automas_maafw_agent_env import env as agent_env
from app.task.MaaFW.tools.core.automas_maafw_agent_env.planner import venv_python_exe


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


class IsValidVenvPathBaseInterpreterTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _make_fake_venv(self, home: Path) -> Path:
        venv_path = self.root / "maafw_venv_fake"
        _touch(venv_python_exe(venv_path))
        (venv_path / "pyvenv.cfg").write_text(
            f"home = {home}\nversion_info = 3.12.10\n", encoding="utf-8"
        )
        return venv_path

    def test_venv_is_invalid_once_its_base_interpreter_directory_is_gone(
        self,
    ) -> None:
        # 监督器 repair/rebuild 把 sys.executable 所在的那个 venv 整个删掉重
        # 建后，旧 pyvenv.cfg 里的 home 会指向一个已经不存在的目录——这里不
        # 创建它，模拟该场景。
        missing_home = self.root / "deleted-supervised-backend-venv"
        venv_path = self._make_fake_venv(missing_home)

        self.assertFalse(agent_env._is_valid_venv_path(venv_path))

    def test_venv_stays_valid_while_its_base_interpreter_is_present(self) -> None:
        real_home = self.root / "backend-venv"
        exe_name = "python.exe" if os.name == "nt" else "python"
        _touch(real_home / exe_name)
        venv_path = self._make_fake_venv(real_home)

        self.assertTrue(agent_env._is_valid_venv_path(venv_path))

    def test_venv_missing_pyvenv_cfg_is_still_caught_as_before(self) -> None:
        # 新判据是叠加的，不能盖掉原有的结构完整性检查
        venv_path = self.root / "maafw_venv_bare"
        _touch(venv_python_exe(venv_path))

        self.assertFalse(agent_env._is_valid_venv_path(venv_path))


if __name__ == "__main__":
    unittest.main()
