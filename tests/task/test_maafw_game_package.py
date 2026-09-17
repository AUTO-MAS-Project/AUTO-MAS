import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.task.MaaFW.tools.embedded.game_package import (
    collect_start_app_nodes,
    normalize_package,
    resolve_game_package,
    resource_paths_for,
)

#: M9A 官服 `resource/base/pipeline/startup.json` 里的真实节点形状。
#: 包名带 Activity，且和其他服共用同一个节点名 Start1999——叠加就是靠这一点生效的。
M9A_BASE_NODE = {
    "Start1999": {
        "action": {
            "type": "StartApp",
            "param": {
                "package": (
                    "com.shenlan.m.reverse1999"
                    "/com.ssgame.mobile.gamesdk.frame.AppStartUpActivity"
                )
            },
        },
        "next": ["DisableStart1999"],
    }
}

#: M9A 国际服 EN 覆盖同一节点，包名是裸的（没有 Activity）。
M9A_EN_NODE = {
    "Start1999": {
        "action": {
            "type": "StartApp",
            "param": {"package": "com.bluepoch.m.en.reverse1999"},
        }
    }
}

#: MaaEnd `tasks/AndroidOpenGame.json` 里 option case 的真实 pipeline_override 形状。
#: 同一份 override 里还有 StopApp，不能把它也当成启动包名。
MAAEND_OVERRIDE = {
    "StartUpGame": {
        "action": {
            "type": "StartApp",
            "param": {"package": "com.hypergryph.endfield/com.u8.sdk.U8UnityContext"},
        }
    },
    "CloseGame": {
        "action": {
            "type": "StopApp",
            "param": {"package": "com.hypergryph.endfield"},
        }
    },
}


class NormalizeTest(unittest.TestCase):
    def test_strips_the_activity(self) -> None:
        self.assertEqual(
            normalize_package("com.shenlan.m.reverse1999/com.ssgame.Activity"),
            "com.shenlan.m.reverse1999",
        )

    def test_bare_package_survives(self) -> None:
        """国际服和 StopApp 写的就是裸包名，不能因为没有斜杠就丢掉。"""
        self.assertEqual(
            normalize_package("com.bluepoch.m.en.reverse1999"),
            "com.bluepoch.m.en.reverse1999",
        )

    def test_blank_stays_blank(self) -> None:
        for raw in ("", "   ", "/com.only.activity"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_package(raw), "")


class CollectTest(unittest.TestCase):
    def test_reads_the_real_m9a_node(self) -> None:
        self.assertEqual(
            collect_start_app_nodes(M9A_BASE_NODE),
            {
                "Start1999": (
                    "com.shenlan.m.reverse1999"
                    "/com.ssgame.mobile.gamesdk.frame.AppStartUpActivity"
                )
            },
        )

    def test_stop_app_is_not_a_launch(self) -> None:
        """同一份 override 里 StopApp 的包名长得一样，认错了就会去「启动」它。"""
        self.assertEqual(
            collect_start_app_nodes(MAAEND_OVERRIDE),
            {"StartUpGame": "com.hypergryph.endfield/com.u8.sdk.U8UnityContext"},
        )

    def test_garbage_does_not_raise(self) -> None:
        for raw in (
            None,
            [],
            "text",
            {"Node": "text"},
            {"Node": {"action": "StartApp"}},
        ):
            with self.subTest(raw=raw):
                self.assertEqual(collect_start_app_nodes(raw), {})


class ResolveTest(unittest.TestCase):
    """回归：resource 的叠加顺序就是覆盖顺序，传错顺序会拿到上一层的包名。"""

    def _resource(self, root: Path, name: str, node: dict) -> Path:
        path = root / name
        (path / "pipeline").mkdir(parents=True)
        (path / "pipeline" / "startup.json").write_text(
            json.dumps(node, ensure_ascii=False), encoding="utf-8"
        )
        return path

    def test_later_path_overrides_earlier(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._resource(root, "base", M9A_BASE_NODE)
            en = self._resource(root, "global_en", M9A_EN_NODE)

            self.assertEqual(
                resolve_game_package([base, en]).package,
                "com.bluepoch.m.en.reverse1999",
            )
            # 反过来传，拿到的就是 base 的包——顺序不是可有可无的
            self.assertEqual(
                resolve_game_package([en, base]).package,
                "com.shenlan.m.reverse1999",
            )

    def test_task_override_replaces_the_same_node(self) -> None:
        """override 的语义是按节点名覆盖，覆盖到同一个节点时它更具体、应当赢。"""
        with TemporaryDirectory() as tmp:
            base = self._resource(Path(tmp), "base", M9A_BASE_NODE)
            override = {
                "Start1999": {
                    "action": {
                        "type": "StartApp",
                        "param": {"package": "com.shenlan.m.reverse1999.bilibili"},
                    }
                }
            }

            outcome = resolve_game_package([base], [override])

            self.assertEqual(outcome.reason, "resolved")
            self.assertEqual(outcome.package, "com.shenlan.m.reverse1999.bilibili")

    def test_override_on_another_node_is_ambiguous_not_a_winner(self) -> None:
        """回归：override 覆盖的是**别的**节点时，两个 StartApp 同时存在。

        MaaFramework 只按节点名覆盖，`StartUpGame` 的 override 不会动 `Start1999`，
        所以此时我们无从知道任务入口会走到哪一个——挑一个去启动等于赌，
        宁可回落到用户手填的包名。
        """
        with TemporaryDirectory() as tmp:
            base = self._resource(Path(tmp), "base", M9A_BASE_NODE)

            outcome = resolve_game_package([base], [MAAEND_OVERRIDE])

            self.assertEqual(outcome.reason, "ambiguous")
            self.assertEqual(outcome.package, "")

    def test_override_only_project_works_without_resource(self) -> None:
        """MaaEnd 的包名根本不在 resource 目录里，只扫 resource 会一无所获。"""
        outcome = resolve_game_package([], [MAAEND_OVERRIDE])

        self.assertEqual(outcome.package, "com.hypergryph.endfield")

    def test_nothing_found_is_not_an_error(self) -> None:
        """很多项目自己在 pipeline 里开游戏，认不出来是正常结果。"""
        outcome = resolve_game_package([], [])

        self.assertEqual(outcome.reason, "not-found")
        self.assertEqual(outcome.package, "")

    def test_conflicting_packages_refuse_to_guess(self) -> None:
        """挑错了会去启动另一个游戏，比不启动更糟。"""
        outcome = resolve_game_package(
            [], [M9A_BASE_NODE, {"Other": MAAEND_OVERRIDE["StartUpGame"]}]
        )

        self.assertEqual(outcome.reason, "ambiguous")
        self.assertEqual(outcome.package, "")
        self.assertEqual(
            outcome.candidates,
            ("com.hypergryph.endfield", "com.shenlan.m.reverse1999"),
        )

    def test_unreadable_file_is_skipped(self) -> None:
        """项目里混进一个坏 JSON 不该让整次代理失败。"""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._resource(root, "base", M9A_BASE_NODE)
            (base / "pipeline" / "broken.json").write_text(
                "{ not json", encoding="utf-8"
            )

            self.assertEqual(
                resolve_game_package([base]).package, "com.shenlan.m.reverse1999"
            )


class ResourcePathsForTest(unittest.TestCase):
    """脚本编辑页按所选 resource 推包名时，先把 interface.resource[].path 解析成目录。"""

    def _interface(self) -> MaaFWInterface:
        # 照抄 M9A interface.json 里 resource 的写法：相对路径以 ./ 开头、按叠加顺序排列
        return MaaFWInterface.model_validate(
            {
                "interface_version": 2,
                "name": "M9A",
                "resource": [
                    {"name": "官服", "path": ["./resource/base"]},
                    {
                        "name": "B 服",
                        "path": ["./resource/base", "./resource/bilibili"],
                    },
                    {
                        "name": "越界",
                        "path": ["{PROJECT_DIR}/resource/base", "../outside"],
                    },
                    {"name": "缺目录", "path": ["./resource/missing"]},
                ],
            }
        )

    def test_keeps_declared_order_and_expands_project_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "resource" / "base").mkdir(parents=True)
            (root / "resource" / "bilibili").mkdir()
            interface = self._interface()

            self.assertEqual(
                resource_paths_for(root, interface, "B 服"),
                [
                    (root / "resource" / "base").resolve(),
                    (root / "resource" / "bilibili").resolve(),
                ],
            )
            # {PROJECT_DIR} 展开；跳出项目目录的条目丢掉，不抛错
            self.assertEqual(
                resource_paths_for(root, interface, "越界"),
                [(root / "resource" / "base").resolve()],
            )
            self.assertEqual(resource_paths_for(root, interface, "缺目录"), [])
            self.assertEqual(
                resource_paths_for(root, interface, "不存在的 resource"), []
            )

    def test_resolves_package_per_resource_like_the_edit_page_does(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "resource" / "base"
            (base / "pipeline").mkdir(parents=True)
            (base / "pipeline" / "startup.json").write_text(
                json.dumps(M9A_BASE_NODE, ensure_ascii=False), encoding="utf-8"
            )
            bili = root / "resource" / "bilibili"
            (bili / "pipeline").mkdir(parents=True)
            (bili / "pipeline" / "startup.json").write_text(
                json.dumps(
                    {
                        "Start1999": {
                            "action": {
                                "type": "StartApp",
                                "param": {
                                    "package": "com.shenlan.m.reverse1999.bilibili"
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            interface = self._interface()

            official = resolve_game_package(resource_paths_for(root, interface, "官服"))
            bilibili = resolve_game_package(resource_paths_for(root, interface, "B 服"))
            self.assertEqual(official.package, "com.shenlan.m.reverse1999")
            self.assertEqual(bilibili.package, "com.shenlan.m.reverse1999.bilibili")


if __name__ == "__main__":
    unittest.main()
