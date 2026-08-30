"""拿真实发行包的形状回归依赖解析。

夹具 `data/maafw_release_corpus.json` 是 2026-08-30 对 MaaFramework 官方目录
里 46 个 Windows 发行包做远程勘察的结果（HTTP Range 读 zip 中央目录，不下整包），
每条记录该包自带的 MaaFramework 版本、库所在目录、requirements.txt 里的
maafw 声明、外壳标记与 agent 形态。

比手编用例有价值的地方在于它是真实分布：10 个不同的 FW 版本、三种库存放位置、
20 个包压根没有 requirements.txt、3 个声明与实际发行的库对不上。手编用例
想不到这些形状。

夹具是**快照**，不会自己更新——它钉的是「这些形状我们处理得对」，
不是「上游现在长这样」。
"""

import json
import unittest
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import InvalidVersion, Version

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
    MINIMUM_SUPPORTED_MAAFW_VERSION,
)

CORPUS = json.loads(
    (Path(__file__).parent / "data" / "maafw_release_corpus.json").read_text(
        encoding="utf-8"
    )
)


def probed_requirement(dll_version: str) -> str | None:
    """模拟 probe_bundled_maafw_version 之后的钉法。"""

    if dll_version in ("-",) or dll_version.startswith("?"):
        return None
    try:
        return "maafw==" + str(Version(dll_version))
    except InvalidVersion:
        return None


def declared_requirement(pin: str) -> str | None:
    return None if pin in ("-", "(无 maafw 行)") else pin


def resolve(entry) -> str:
    """当前的解析顺序：自带库探测 > requirements 声明 > 无约束兜底。"""

    return (
        probed_requirement(entry["dll"])
        or declared_requirement(entry["declared"])
        or "maafw"
    )


class CorpusShapeTest(unittest.TestCase):
    def test_corpus_is_not_empty(self) -> None:
        self.assertGreaterEqual(len(CORPUS), 40)

    def test_every_resolution_is_a_valid_requirement(self) -> None:
        for e in CORPUS:
            with self.subTest(app=e["app"], asset=e["asset"]):
                Requirement(resolve(e))  # 非法会抛

    def test_the_shipped_library_always_wins_when_detectable(self) -> None:
        for e in CORPUS:
            probed = probed_requirement(e["dll"])
            if probed is None:
                continue
            with self.subTest(app=e["app"]):
                self.assertEqual(resolve(e), probed)

    def test_only_projects_without_a_library_fall_back_to_unpinned(self) -> None:
        unpinned = [e for e in CORPUS if resolve(e) == "maafw"]
        for e in unpinned:
            with self.subTest(app=e["app"]):
                self.assertIsNone(
                    probed_requirement(e["dll"]),
                    "有库可探却回退到了无约束",
                )

    def test_stale_declarations_are_overridden(self) -> None:
        """三个真实案例：声明与实际发行的库对不上，必须以库为准。"""

        stale = []
        for e in CORPUS:
            probed = probed_requirement(e["dll"])
            declared = declared_requirement(e["declared"])
            if not probed or not declared or "==" not in declared:
                continue
            dv = declared.split("==", 1)[1].strip().lstrip("vV")
            if Version(dv) != Version(probed.split("==", 1)[1]):
                stale.append(e["app"])
                self.assertEqual(resolve(e), probed)
        self.assertGreaterEqual(len(stale), 3, "夹具里应有已知的陈旧声明样本")


class CorpusCoverageTest(unittest.TestCase):
    """夹具本身要覆盖到那些容易被手编用例漏掉的形状。"""

    def test_multiple_library_locations_are_represented(self) -> None:
        locations = {e["at"] for e in CORPUS if e["at"] != "无"}
        self.assertIn("maafw", locations)
        self.assertIn("<root>", locations)
        self.assertIn("runtimes/win-x64/native", locations)

    def test_many_projects_declare_nothing(self) -> None:
        silent = [e for e in CORPUS if e["declared"] == "-"]
        self.assertGreaterEqual(len(silent), 15)

    def test_a_wide_span_of_framework_versions(self) -> None:
        vers = {e["dll"] for e in CORPUS if e["dll"] != "-"}
        self.assertGreaterEqual(len(vers), 8)

    def test_prerelease_versions_are_represented(self) -> None:
        self.assertTrue(any("beta" in e["dll"] for e in CORPUS))

    def test_projects_below_the_supported_floor_are_known(self) -> None:
        """低于下限的是已知的两个，不该悄悄多出来。"""

        floor = Version(MINIMUM_SUPPORTED_MAAFW_VERSION)
        below = set()
        for e in CORPUS:
            probed = probed_requirement(e["dll"])
            if probed and Version(probed.split("==", 1)[1]) < floor:
                below.add(e["app"])
        self.assertEqual(below, {"MMleo", "MaaEOV"})


if __name__ == "__main__":
    unittest.main()
