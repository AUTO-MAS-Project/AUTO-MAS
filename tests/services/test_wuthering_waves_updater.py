import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from app.services import wuthering_waves_updater as wwu
from app.services.wuthering_waves_updater import (
    ResourceEntry,
    UpdatePlan,
    _apply_deletions,
    _build_patch_plan,
    _commit_file,
    _download_entry,
    _entry_url,
    _plan_full_sync,
    build_update_plan,
    resolve_within,
    safe_relative_path,
    select_cdn_urls,
    update_wuthering_waves,
)


def _md5(payload: bytes) -> str:
    return hashlib.md5(payload).hexdigest()


def _entry(dest: str, payload: bytes, **kwargs) -> ResourceEntry:
    return ResourceEntry(dest=dest, md5=_md5(payload), size=len(payload), **kwargs)


class PathSafetyTest(unittest.TestCase):
    """dest 来自网络，落盘前必须挡住穿越（okww 曾因此清空过项目源码）。"""

    def test_rejects_parent_traversal(self) -> None:
        for dest in (
            "../evil.dll",
            "../../Windows/System32/evil.dll",
            "Client/../../evil.dll",
            "Client/..",
        ):
            with self.subTest(dest=dest), self.assertRaises(ValueError):
                safe_relative_path(dest)

    def test_rejects_dest_pointing_at_directory_itself(self) -> None:
        # pathlib 会把 "." 归一成空 parts，放过就等于让 os.replace 冲掉整个游戏目录
        for dest in (".", "./", ".\\"):
            with self.subTest(dest=dest), self.assertRaises(ValueError):
                safe_relative_path(dest)

    def test_single_dot_component_is_normalized_not_rejected(self) -> None:
        # "Client/./x" 被 pathlib 归一成安全路径，不必拒绝
        self.assertEqual(
            safe_relative_path("Client/./evil.dll"), Path("Client/evil.dll")
        )

    def test_rejects_absolute_and_drive(self) -> None:
        for dest in ("/etc/passwd", "C:/Windows/evil.dll", "C:\\Windows\\evil.dll"):
            with self.subTest(dest=dest), self.assertRaises(ValueError):
                safe_relative_path(dest)

    def test_rejects_empty(self) -> None:
        for dest in ("", "   "):
            with self.subTest(dest=dest), self.assertRaises(ValueError):
                safe_relative_path(dest)

    def test_accepts_normal_manifest_paths(self) -> None:
        self.assertEqual(
            safe_relative_path("Client/Content/Paks/pakchunk0-WindowsNoEditor.pak"),
            Path("Client/Content/Paks/pakchunk0-WindowsNoEditor.pak"),
        )
        # 清单里有带空格的真实条目
        self.assertEqual(
            safe_relative_path("Wuthering Waves.exe"), Path("Wuthering Waves.exe")
        )

    def test_normalizes_backslashes(self) -> None:
        self.assertEqual(
            safe_relative_path("Client\\Binaries\\x.dll"), Path("Client/Binaries/x.dll")
        )

    def test_resolve_within_blocks_escape(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_within(root, "../outside.bin")
            self.assertTrue(
                resolve_within(root, "a/b.bin").is_relative_to(root.resolve())
            )


class CdnSelectionTest(unittest.TestCase):
    def test_orders_by_weight_and_keeps_all_as_fallback(self) -> None:
        index = {
            "default": {
                "cdnList": [
                    {"P": 0, "K1": 1, "K2": 1, "url": "https://low.example/"},
                    {"P": 99, "K1": 1, "K2": 1, "url": "https://high.example/"},
                ]
            }
        }
        # 全部保留：单个 CDN 连不上时要能逐个换
        self.assertEqual(
            select_cdn_urls(index),
            ("https://high.example/", "https://low.example/"),
        )

    def test_skips_disabled_entries(self) -> None:
        index = {
            "default": {
                "cdnList": [
                    {"P": 99, "K1": 0, "K2": 1, "url": "https://off.example/"},
                    {"P": 1, "K1": 1, "K2": 1, "url": "https://on.example/"},
                ]
            }
        }
        self.assertEqual(select_cdn_urls(index), ("https://on.example/",))

    def test_falls_back_to_disabled_when_none_enabled(self) -> None:
        # 宁可试被标记为停用的，也不要一个都不试
        index = {
            "default": {
                "cdnList": [{"P": 5, "K1": 0, "K2": 0, "url": "https://only.example/"}]
            }
        }
        self.assertEqual(select_cdn_urls(index), ("https://only.example/",))

    def test_appends_missing_trailing_slash(self) -> None:
        index = {
            "default": {"cdnList": [{"P": 1, "K1": 1, "K2": 1, "url": "https://x"}]}
        }
        self.assertEqual(select_cdn_urls(index), ("https://x/",))

    def test_raises_without_any_cdn(self) -> None:
        with self.assertRaises(ValueError):
            select_cdn_urls({"default": {"cdnList": []}})


class EntryUrlTest(unittest.TestCase):
    plan = UpdatePlan(
        target_version="3.6.0",
        kind="patch",
        base_url="launcher/patch/3.5.3/resources/",
        cdn_urls=("https://cdn.example/",),
        downloads=(),
    )

    def test_from_folder_overrides_plan_base(self) -> None:
        # 整文件条目自带 fromFolder（zip/），补丁包才走计划级 baseUrl
        entry = ResourceEntry(
            dest="Client/x.pak", md5="0", size=1, from_folder="launcher/full/zip/"
        )
        self.assertEqual(
            _entry_url("https://cdn.example/", self.plan, entry),
            "https://cdn.example/launcher/full/zip/Client/x.pak",
        )

    def test_falls_back_to_plan_base(self) -> None:
        entry = ResourceEntry(dest="a_b.krpdiff", md5="0", size=1)
        self.assertEqual(
            _entry_url("https://cdn.example/", self.plan, entry),
            "https://cdn.example/launcher/patch/3.5.3/resources/a_b.krpdiff",
        )

    def test_encodes_spaces(self) -> None:
        entry = ResourceEntry(dest="Wuthering Waves.exe", md5="0", size=1)
        self.assertIn(
            "Wuthering%20Waves.exe", _entry_url("https://c/", self.plan, entry)
        )


class DownloadTest(unittest.IsolatedAsyncioTestCase):
    payload = b"official game bytes" * 64

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.staging = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.entry = _entry("Client/x.pak", self.payload)
        self.plan = UpdatePlan(
            target_version="3.6.0",
            kind="full",
            base_url="base/zip/",
            cdn_urls=("https://a.example/", "https://b.example/"),
            downloads=(self.entry,),
        )

    async def _run(self, handler) -> Path:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _download_entry(client, self.plan, self.entry, self.staging)

    async def test_downloads_and_verifies(self) -> None:
        target = await self._run(lambda _: httpx.Response(200, content=self.payload))
        self.assertEqual(target.read_bytes(), self.payload)

    async def test_rejects_corrupt_payload_and_removes_it(self) -> None:
        with self.assertRaises(RuntimeError):
            await self._run(lambda _: httpx.Response(200, content=b"tampered"))
        # 坏残留必须删掉，否则下一轮续传会接在坏字节后面
        self.assertFalse((self.staging / "Client/x.pak").exists())

    async def test_resumes_from_partial_with_206(self) -> None:
        partial = self.staging / "Client/x.pak"
        partial.parent.mkdir(parents=True, exist_ok=True)
        cut = 100
        partial.write_bytes(self.payload[:cut])

        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Range", ""))
            return httpx.Response(206, content=self.payload[cut:])

        target = await self._run(handler)
        self.assertEqual(seen[0], f"bytes={cut}-")
        self.assertEqual(target.read_bytes(), self.payload)

    async def test_server_ignoring_range_must_truncate_not_append(self) -> None:
        # 请求 Range 却回 200 时若追加写入，会把新内容接在旧字节后，静默产出坏文件
        partial = self.staging / "Client/x.pak"
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(self.payload[:100])
        target = await self._run(lambda _: httpx.Response(200, content=self.payload))
        self.assertEqual(target.read_bytes(), self.payload)

    async def test_reuses_already_complete_file_without_network(self) -> None:
        done = self.staging / "Client/x.pak"
        done.parent.mkdir(parents=True, exist_ok=True)
        done.write_bytes(self.payload)

        def handler(_: httpx.Request) -> httpx.Response:
            raise AssertionError("已完整的文件不应重新下载")

        self.assertEqual((await self._run(handler)).read_bytes(), self.payload)

    async def test_fails_over_to_next_cdn(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "a.example":
                return httpx.Response(503)
            return httpx.Response(200, content=self.payload)

        self.assertEqual((await self._run(handler)).read_bytes(), self.payload)


class PatchPlanTest(unittest.TestCase):
    manifest = {
        "resource": [
            {"dest": "a_b_group_0.krpdiff", "md5": "aa", "size": 10},
            {
                "dest": "Client/whole.pak",
                "md5": "bb",
                "size": 20,
                "fromFolder": "base/zip/",
            },
        ],
        "groupInfos": [
            {
                "dest": "a_b_group_0.krpdiff",
                "srcFiles": [{"dest": "Client/p.pak", "md5": "old", "size": 5}],
                "dstFiles": [{"dest": "Client/p.pak", "md5": "new", "size": 6}],
            }
        ],
        "deleteFiles": ["Client/Content/Paks/gone.pak"],
        "applyTypes": ["group"],
    }

    def test_parses_downloads_groups_and_deletions(self) -> None:
        plan = _build_patch_plan(
            self.manifest,
            target_version="3.6.0",
            base_url="patch/resources/",
            cdn_urls=("https://c/",),
            whole_file_base_url="base/zip/",
        )
        self.assertEqual(plan.kind, "patch")
        self.assertEqual(len(plan.downloads), 2)
        self.assertEqual(plan.download_size, 30)
        self.assertEqual(plan.delete_files, ("Client/Content/Paks/gone.pak",))
        self.assertEqual(plan.groups[0].dst_files[0].md5, "new")

    def test_distinguishes_patch_blobs_from_whole_files(self) -> None:
        plan = _build_patch_plan(
            self.manifest,
            target_version="3.6.0",
            base_url="patch/resources/",
            cdn_urls=("https://c/",),
        )
        blobs = [e.dest for e in plan.downloads if e.is_patch_blob]
        whole = [e.dest for e in plan.downloads if not e.is_patch_blob]
        self.assertEqual(blobs, ["a_b_group_0.krpdiff"])
        self.assertEqual(whole, ["Client/whole.pak"])

    def test_empty_manifest_raises(self) -> None:
        with self.assertRaises(ValueError):
            _build_patch_plan(
                {"resource": []},
                target_version="3.6.0",
                base_url="x/",
                cdn_urls=("https://c/",),
            )


class FullSyncPlanTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.install_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write_local(self, dest: str, payload: bytes) -> None:
        path = self.install_dir / dest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def _write_local_manifest(self, entries: list[dict]) -> None:
        (self.install_dir / "LocalGameResources.json").write_text(
            json.dumps({"resource": entries}), encoding="utf-8"
        )

    async def _plan(self, remote: list[ResourceEntry]) -> UpdatePlan:
        return await _plan_full_sync(
            self.install_dir,
            remote,
            target_version="3.6.0",
            base_url="base/zip/",
            cdn_urls=("https://c/",),
            on_progress=None,
        )

    async def test_only_downloads_files_that_differ(self) -> None:
        same, changed = b"identical", b"remote-new"
        self._write_local("same.bin", same)
        self._write_local("changed.bin", b"local-old")
        plan = await self._plan(
            [_entry("same.bin", same), _entry("changed.bin", changed)]
        )
        self.assertEqual([e.dest for e in plan.downloads], ["changed.bin"])

    async def test_includes_missing_files(self) -> None:
        plan = await self._plan([_entry("absent.bin", b"payload")])
        self.assertEqual([e.dest for e in plan.downloads], ["absent.bin"])

    async def test_trusts_local_manifest_when_size_matches(self) -> None:
        payload = b"cached-by-launcher"
        self._write_local("cached.bin", payload)
        self._write_local_manifest(
            [{"dest": "cached.bin", "md5": _md5(payload), "size": len(payload)}]
        )
        plan = await self._plan([_entry("cached.bin", payload)])
        self.assertEqual(plan.downloads, ())

    async def test_ignores_stale_manifest_when_size_disagrees(self) -> None:
        # 缓存 md5 与实际不符但大小对不上时必须实算，不能盲信启动器清单
        remote = b"remote-content"
        self._write_local("drift.bin", b"different-length-content")
        self._write_local_manifest(
            [{"dest": "drift.bin", "md5": _md5(remote), "size": len(remote)}]
        )
        plan = await self._plan([_entry("drift.bin", remote)])
        self.assertEqual([e.dest for e in plan.downloads], ["drift.bin"])


class CommitTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.staging = root / "staging"
        self.install_dir = root / "game"
        self.staging.mkdir()
        self.install_dir.mkdir()
        self.addCleanup(self._tmp.cleanup)

    async def test_moves_verified_file_into_place(self) -> None:
        payload = b"verified bytes"
        source = self.staging / "x.pak"
        source.write_bytes(payload)
        await _commit_file(source, self.install_dir, _entry("Client/x.pak", payload))
        self.assertEqual((self.install_dir / "Client/x.pak").read_bytes(), payload)
        self.assertFalse(source.exists())

    async def test_refuses_to_install_corrupt_file(self) -> None:
        # 宁可本次更新失败，也不能把坏文件写进游戏目录
        source = self.staging / "x.pak"
        source.write_bytes(b"corrupt")
        target = self.install_dir / "Client/x.pak"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"original")
        with self.assertRaises(RuntimeError):
            await _commit_file(
                source, self.install_dir, _entry("Client/x.pak", b"expected")
            )
        self.assertEqual(target.read_bytes(), b"original")


class DeletionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.install_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _plan(self, deletions: tuple[str, ...]) -> UpdatePlan:
        return UpdatePlan(
            target_version="3.6.0",
            kind="patch",
            base_url="x/",
            cdn_urls=("https://c/",),
            downloads=(),
            delete_files=deletions,
        )

    async def test_removes_listed_files(self) -> None:
        victim = self.install_dir / "Client/gone.pak"
        victim.parent.mkdir(parents=True)
        victim.write_bytes(b"obsolete")
        await _apply_deletions(self.install_dir, self._plan(("Client/gone.pak",)))
        self.assertFalse(victim.exists())

    async def test_skips_traversal_attempts(self) -> None:
        outside = self.install_dir.parent / "precious.txt"
        outside.write_bytes(b"must survive")
        self.addCleanup(outside.unlink, True)
        await _apply_deletions(self.install_dir, self._plan(("../precious.txt",)))
        self.assertTrue(outside.exists())

    async def test_tolerates_already_absent_files(self) -> None:
        await _apply_deletions(self.install_dir, self._plan(("Client/never.pak",)))


_INDEX_URL = "https://index.example/index.json"
_FULL_MANIFEST = "launcher/full/indexFile.json"
_PATCH_MANIFEST = "launcher/patch/3.5.3/indexFile.json"


def _index(local_patch_version: str = "3.5.3") -> dict:
    return {
        "default": {
            "version": "3.6.0",
            "cdnList": [{"P": 1, "K1": 1, "K2": 1, "url": "https://cdn.example/"}],
            "resourcesBasePath": "launcher/full/zip",
            "config": {
                "indexFile": _FULL_MANIFEST,
                "patchConfig": [
                    {
                        "version": local_patch_version,
                        "indexFile": _PATCH_MANIFEST,
                        "baseUrl": "launcher/patch/3.5.3/resources/",
                    }
                ],
            },
        }
    }


class UpdateOrchestrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.install_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _serve(self, routes: dict[str, dict]):
        def handler(request: httpx.Request) -> httpx.Response:
            for suffix, body in routes.items():
                if str(request.url).endswith(suffix):
                    return httpx.Response(200, json=body)
            return httpx.Response(404)

        return handler

    async def _plan_with(
        self, routes: dict[str, dict], local_version: str
    ) -> UpdatePlan:
        handler = self._serve(routes)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await build_update_plan(
                client, _index(), self.install_dir, local_version
            )

    async def test_prefers_official_patch_when_version_matches(self) -> None:
        plan = await self._plan_with(
            {
                _PATCH_MANIFEST: {
                    "resource": [{"dest": "g0.krpdiff", "md5": "aa", "size": 5}],
                    "groupInfos": [],
                    "deleteFiles": [],
                }
            },
            "3.5.3",
        )
        self.assertEqual(plan.kind, "patch")
        # 回退整文件重下需要 zip/ 基址，必须从 index 带过来
        self.assertEqual(plan.whole_file_base_url, "launcher/full/zip/")

    async def test_falls_back_to_full_sync_for_unknown_version(self) -> None:
        plan = await self._plan_with(
            {_FULL_MANIFEST: {"resource": [{"dest": "a.pak", "md5": "aa", "size": 5}]}},
            "1.0.0",
        )
        self.assertEqual(plan.kind, "full")
        self.assertEqual(plan.base_url, "launcher/full/zip/")

    async def _update(
        self, routes: dict[str, dict], local_version: str, **kwargs
    ) -> str:
        handler = self._serve({_INDEX_URL: _index(), **routes})
        # 必须先抓住真类：工厂里若再引用 httpx.AsyncClient，打完补丁就是无限递归
        real_client = httpx.AsyncClient

        def client_factory(**_ignored):
            return real_client(transport=httpx.MockTransport(handler))

        with (
            patch.object(wwu, "get_official_index_url", lambda _: _INDEX_URL),
            patch.object(wwu.httpx, "AsyncClient", client_factory),
        ):
            return await update_wuthering_waves(
                self.install_dir, "官服", local_version, **kwargs
            )

    async def test_refuses_oversized_full_sync(self) -> None:
        # 大版本跨越时整文件同步接近重装，不该在无人值守时静默跑掉
        routes = {
            _FULL_MANIFEST: {
                "resource": [{"dest": "huge.pak", "md5": "aa", "size": 90 * 1024**3}]
            }
        }
        with self.assertRaises(RuntimeError) as ctx:
            await self._update(routes, "1.0.0", full_sync_limit=10 * 1024**3)
        self.assertIn("已中止", str(ctx.exception))

    async def test_records_version_when_already_current(self) -> None:
        payload = b"already installed"
        target = self.install_dir / "a.pak"
        target.write_bytes(payload)
        routes = {
            _FULL_MANIFEST: {
                "resource": [
                    {"dest": "a.pak", "md5": _md5(payload), "size": len(payload)}
                ]
            }
        }
        self.assertEqual(await self._update(routes, "1.0.0"), "3.6.0")
        state = json.loads(
            (self.install_dir / "launcherDownloadConfig.json").read_text("utf-8")
        )
        self.assertEqual(state["version"], "3.6.0")
