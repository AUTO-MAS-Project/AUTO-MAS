import tempfile
import unittest
from pathlib import Path

import app.core  # noqa: F401

from app.api.maafw import _maafw_asset_file_path


class MaaFWAssetPathTest(unittest.TestCase):
    """项目内图片服务的安全边界。

    这个端点的 root 由请求方给定，等于把「读任意目录下的文件」的能力暴露出去，
    只能靠「必须在 root 内」+「必须是图片」两道闸门收窄成「读项目内的图片」。
    前端的 buildMaaFWAssetUrl 也拦一遍，但那只是省一次往返 —— 请求可以绕过前端
    直接打过来，边界在这里。
    """

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name) / "project"
        (self.root / "resource" / "announcement" / "images").mkdir(parents=True)
        self.image = self.root / "resource" / "announcement" / "images" / "bydjl.png"
        self.image.write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.root / "interface.json").write_text("{}", encoding="utf-8")
        (Path(self._temp.name) / "outside.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    def test_serves_a_project_image(self) -> None:
        resolved = _maafw_asset_file_path(
            str(self.root), chr(92).join(("resource", "announcement", "images", "bydjl.png"))
        )
        self.assertEqual(resolved, self.image.resolve())

    def test_accepts_backslash_separators(self) -> None:
        # markdown 里写 Windows 分隔符的项目确实存在，前端会归一化，这里也要认。
        resolved = _maafw_asset_file_path(
            str(self.root), chr(92).join(("resource", "announcement", "images", "bydjl.png"))
        )
        self.assertEqual(resolved, self.image.resolve())

    def test_rejects_traversal(self) -> None:
        for bad in ("../outside.png", "a/../../outside.png", "..", "a/../.."):
            with self.subTest(path=bad):
                with self.assertRaises(ValueError):
                    _maafw_asset_file_path(str(self.root), bad)

    def test_rejects_absolute_paths(self) -> None:
        unc = chr(92) * 2 + "host" + chr(92) + "share" + chr(92) + "x.png"
        for bad in ("C:/Windows/win.ini", "/etc/passwd", unc):
            with self.subTest(path=bad):
                with self.assertRaises(ValueError):
                    _maafw_asset_file_path(str(self.root), bad)

    def test_rejects_non_image_suffix(self) -> None:
        # 放开成任意后缀，这个端点就成了任意文件读取。
        with self.assertRaises(ValueError):
            _maafw_asset_file_path(str(self.root), "interface.json")

    def test_rejects_empty_path(self) -> None:
        for bad in ("", "   "):
            with self.subTest(path=bad):
                with self.assertRaises(ValueError):
                    _maafw_asset_file_path(str(self.root), bad)

    def test_rejects_missing_root(self) -> None:
        with self.assertRaises(ValueError):
            _maafw_asset_file_path(str(self.root / "nope"), "a.png")

    def test_missing_file_is_distinguishable(self) -> None:
        # 缺文件要能和「非法请求」分开：前者 404，后者 400。
        with self.assertRaises(FileNotFoundError):
            _maafw_asset_file_path(str(self.root), "resource/announcement/images/nope.png")


class MaaFWAssetRouteTest(unittest.TestCase):
    """路由必须挂在前端写死的那个地址上。

    前端 buildMaaFWAssetUrl 拼的是 `${base}/api/maafw/asset?root=..&path=..`；
    这条路由此前只存在于前端，后端没有对应实现，于是所有项目内图片一律 404
    （2026-08-29 用户在 M9A 任务说明里看到的就是这个）。
    """

    def test_route_is_registered_where_the_frontend_expects(self) -> None:
        from app.api.maafw import router

        paths = {route.path for route in router.routes}
        self.assertIn("/api/maafw/asset", paths)

    def test_router_is_exported_and_mounted(self) -> None:
        from app import api

        self.assertIn("maafw_router", api.__all__)
        source = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("app.include_router(maafw_router)", source)


if __name__ == "__main__":
    unittest.main()
