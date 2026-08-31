"""宿主 → worker 的 job 文件序列化接缝。

宿主构建运行计划，写成 JSON 交给隔离 venv 里的 worker 子进程解析。
这一步跨进程，任何不可 JSON 序列化的字段（Path、Enum、datetime）都会在
运行期才炸。本文件用真实项目的计划把这条缝走一遍，不起子进程。
"""

import json
import tempfile
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    load_interface_model,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
    MaaFWDeviceConfig,
    MaaFWRunnerJobPayload,
    MaaFWRunPlan,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.run_plan import (
    build_maafw_run_plan,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.service import (
    MaaFWRunnerService,
)

TARGET_ROOT = Path("D:/MAS/tmp/maafw-embedded-target")
TARGETS = {
    "M9A": ("M9A-win-x86_64-v4.7.1-MFAA", "PC", "Win32"),
    "MaaEnd": ("MaaEnd-win-x86_64-v2.26.0", "Win32-Front", "Win32"),
    "Maa_bbb": ("Maa_bbb-win-x86_64-v1.12.14", "桌面端", "Win32"),
}

SYNTHETIC_INTERFACE = {
    "interface_version": 2,
    "name": "Demo",
    "version": "v1.0.0",
    "controller": [{"name": "桌面端", "type": "Win32"}],
    "resource": [{"name": "简中", "path": ["{PROJECT_DIR}/resource/base"]}],
    "task": [{"name": "启动游戏", "entry": "StartUp", "default_check": True}],
}


def round_trip(plan: MaaFWRunPlan, work_dir: Path) -> MaaFWRunnerJobPayload:
    """按宿主的真实写法落盘，再按 worker 的真实读法解析回来。"""

    service = MaaFWRunnerService()
    payload = service.create_job_payload(plan, MaaFWDeviceConfig(type="Win32", hWnd=0))
    job_path = service.write_job_file(payload, work_dir)

    # 以下三行与 worker.main() 中的解析路径逐字对应
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    restored_plan = MaaFWRunPlan.model_validate(raw["plan"])
    restored_device = MaaFWDeviceConfig.model_validate(raw["deviceConfig"])

    return MaaFWRunnerJobPayload(
        plan=restored_plan,
        deviceConfig=restored_device,
        ownerPid=raw.get("ownerPid"),
        ownerCreateTime=raw.get("ownerCreateTime"),
    )


class SyntheticPlanRoundTripTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.project = self.root / "project"
        (self.project / "resource" / "base").mkdir(parents=True)
        (self.project / "interface.json").write_text(
            json.dumps(SYNTHETIC_INTERFACE, ensure_ascii=False), encoding="utf-8"
        )

    def test_plan_survives_the_job_file(self) -> None:
        plan = build_maafw_run_plan(
            self.project,
            SYNTHETIC_INTERFACE,
            task_names=["启动游戏"],
            managed_env_root=self.root / "envs",
        )
        restored = round_trip(plan, self.root / "jobs")
        self.assertEqual(restored.plan.controllerName, plan.controllerName)
        self.assertEqual(restored.plan.resourceName, plan.resourceName)
        self.assertEqual(
            [task.name for task in restored.plan.tasks],
            [task.name for task in plan.tasks],
        )

    def test_owner_identity_is_filled_and_survives(self) -> None:
        plan = build_maafw_run_plan(
            self.project,
            SYNTHETIC_INTERFACE,
            task_names=["启动游戏"],
            managed_env_root=self.root / "envs",
        )
        restored = round_trip(plan, self.root / "jobs")
        # 看门狗靠这两个字段判定宿主是否还活着
        self.assertIsInstance(restored.ownerPid, int)
        self.assertGreater(restored.ownerPid, 0)
        self.assertIsInstance(restored.ownerCreateTime, float)
        self.assertGreater(restored.ownerCreateTime, 0)

    def test_job_file_is_utf8_and_not_ascii_escaped(self) -> None:
        plan = build_maafw_run_plan(
            self.project,
            SYNTHETIC_INTERFACE,
            task_names=["启动游戏"],
            managed_env_root=self.root / "envs",
        )
        service = MaaFWRunnerService()
        payload = service.create_job_payload(
            plan, MaaFWDeviceConfig(type="Win32", hWnd=0)
        )
        job_path = service.write_job_file(payload, self.root / "jobs")
        text = job_path.read_text(encoding="utf-8")
        self.assertIn("启动游戏", text)
        self.assertNotIn("\\u542f", text)

    def test_every_plan_field_is_json_native(self) -> None:
        """model_dump(mode="json") 之后不得残留 Path / Enum / datetime。"""

        plan = build_maafw_run_plan(
            self.project,
            SYNTHETIC_INTERFACE,
            task_names=["启动游戏"],
            managed_env_root=self.root / "envs",
        )
        dumped = plan.model_dump(mode="json")

        def walk(value, path="plan"):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertIsInstance(key, str, path)
                    walk(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
            else:
                self.assertIsInstance(value, (str, int, float, bool, type(None)), path)

        walk(dumped)
        json.dumps(dumped, ensure_ascii=False)  # 不得抛


class RealProjectPlanRoundTripTest(unittest.TestCase):
    """真实项目的计划走同一条缝（本机没有靶子就跳过）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)

    def test_real_plans_survive_the_job_file(self) -> None:
        checked = 0
        for label, (folder, controller, _type) in TARGETS.items():
            project = TARGET_ROOT / folder
            if not (project / "interface.json").is_file():
                continue
            with self.subTest(target=label):
                interface = load_interface_model(project)
                task_names = [task.name for task in interface.task][:3]
                plan = build_maafw_run_plan(
                    project,
                    interface,
                    controller_name=controller,
                    task_names=task_names,
                    managed_env_root=self.work / "envs",
                )
                restored = round_trip(plan, self.work / "jobs")
                self.assertEqual(restored.plan.controllerName, controller)
                self.assertEqual(
                    [task.name for task in restored.plan.tasks],
                    [task.name for task in plan.tasks],
                )
                self.assertTrue(restored.plan.tasks, "计划里应至少有一个任务")
                checked += 1
        if checked == 0:
            self.skipTest(f"本机没有靶子：{TARGET_ROOT}")


if __name__ == "__main__":
    unittest.main()
