"""`automas_maafw_project_store` 的导入与纯逻辑回归。

该包由 `mfwa` 逐字节移入（见 `docs/迁移审计/maafw-移植基准对照-20260830.md` §2），
第三层（资源共享）尚未解 gate，本文件只覆盖不落盘、不解压的路径与约束校验逻辑。
"""

import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_project_store import (
    CHECKOUT_KIND,
    CHECKOUT_MARKER_NAME,
    MANIFEST_FILE_NAME,
    MaaFWProjectStoreError,
    MaaFWProjectStoreService,
    RUN_ROOT_KIND,
    RUN_ROOT_MARKER_NAME,
    STORE_KIND,
    STORE_MARKER_NAME,
    STORE_SCHEMA_VERSION,
)
from app.task.MaaFW.tools.core.automas_maafw_project_store.service import (
    _looks_like_local_path,
    _maafw_constraint_accepts_version,
    _normalize_python_constraint,
    _normalize_relative_path,
    _python_constraint_accepts_minor_family,
    _validate_component,
    _validate_zip_member_name,
)


class ProjectStorePackageImportTest(unittest.TestCase):
    def test_public_surface_is_importable(self) -> None:
        self.assertTrue(issubclass(MaaFWProjectStoreError, RuntimeError))
        self.assertTrue(callable(MaaFWProjectStoreService))
        self.assertIsInstance(STORE_SCHEMA_VERSION, int)
        for name in (
            MANIFEST_FILE_NAME,
            CHECKOUT_KIND,
            CHECKOUT_MARKER_NAME,
            RUN_ROOT_KIND,
            RUN_ROOT_MARKER_NAME,
            STORE_KIND,
            STORE_MARKER_NAME,
        ):
            self.assertIsInstance(name, str)
            self.assertTrue(name)

    def test_marker_kinds_are_distinct(self) -> None:
        self.assertEqual(
            len({STORE_KIND, CHECKOUT_KIND, RUN_ROOT_KIND}),
            3,
        )


class NormalizeRelativePathTest(unittest.TestCase):
    def test_backslashes_and_project_dir_token_are_stripped(self) -> None:
        self.assertEqual(
            _normalize_relative_path("{PROJECT_DIR}\\resource\\base", "resource"),
            Path("resource") / "base",
        )
        self.assertEqual(
            _normalize_relative_path("${PROJECT_DIR}/resource/base", "resource"),
            Path("resource") / "base",
        )

    def test_redundant_segments_are_collapsed(self) -> None:
        self.assertEqual(
            _normalize_relative_path("./resource//base/", "resource"),
            Path("resource") / "base",
        )

    def test_parent_traversal_is_rejected(self) -> None:
        for value in ("../secret", "resource/../../secret", "{PROJECT_DIR}/../x"):
            with self.subTest(value=value):
                with self.assertRaises(MaaFWProjectStoreError):
                    _normalize_relative_path(value, "resource")

    def test_absolute_paths_are_rejected(self) -> None:
        for value in ("C:/tmp/x", "/etc/passwd", "C:\\tmp\\x"):
            with self.subTest(value=value):
                with self.assertRaises(MaaFWProjectStoreError):
                    _normalize_relative_path(value, "resource")

    def test_empty_is_rejected_unless_root_allowed(self) -> None:
        with self.assertRaises(MaaFWProjectStoreError):
            _normalize_relative_path("{PROJECT_DIR}", "resource")
        self.assertEqual(
            _normalize_relative_path("{PROJECT_DIR}", "resource", allow_root=True),
            Path("."),
        )


class ZipMemberNameValidationTest(unittest.TestCase):
    def test_plain_member_is_normalized(self) -> None:
        self.assertEqual(
            _validate_zip_member_name("pkg\\resource\\base\\x.json"),
            ("pkg/resource/base/x.json", ("pkg", "resource", "base", "x.json")),
        )

    def test_zip_slip_is_rejected(self) -> None:
        for value in ("../evil", "pkg/../../evil", "./evil/../.."):
            with self.subTest(value=value):
                with self.assertRaises(MaaFWProjectStoreError):
                    _validate_zip_member_name(value)

    def test_absolute_and_drive_members_are_rejected(self) -> None:
        for value in ("/etc/passwd", "//host/share/x", "C:/evil", "C:\\evil"):
            with self.subTest(value=value):
                with self.assertRaises(MaaFWProjectStoreError):
                    _validate_zip_member_name(value)

    def test_nul_byte_is_rejected(self) -> None:
        with self.assertRaises(MaaFWProjectStoreError):
            _validate_zip_member_name("pkg/x\x00.json")

    def test_windows_hostile_components_are_rejected(self) -> None:
        for value in ("pkg/x./y", "pkg/x /y", "pkg/a:b/y", "pkg/CON/y", "pkg/nul.txt"):
            with self.subTest(value=value):
                with self.assertRaises(MaaFWProjectStoreError):
                    _validate_zip_member_name(value)

    def test_empty_member_is_rejected(self) -> None:
        with self.assertRaises(MaaFWProjectStoreError):
            _validate_zip_member_name("")


class ComponentValidationTest(unittest.TestCase):
    def test_accepts_safe_identifiers(self) -> None:
        for value in ("M9A", "maa_yys", "v3.14.8", "a+b", "a-b"):
            with self.subTest(value=value):
                self.assertEqual(_validate_component(value, "projectId"), value)

    def test_rejects_separators_and_reserved_names(self) -> None:
        for value in ("a/b", "a\\b", "a b", "COM1", "prn.txt", "x.", ""):
            with self.subTest(value=value):
                with self.assertRaises(MaaFWProjectStoreError):
                    _validate_component(value, "projectId")


class PythonConstraintTest(unittest.TestCase):
    def test_normalization_is_canonical_and_order_independent(self) -> None:
        # SpecifierSet 的字符串形式是排序过的，写入 manifest 的约束因此可比较
        canonical = "<3.14,>=3.12"
        self.assertEqual(_normalize_python_constraint(">=3.12,<3.14"), canonical)
        self.assertEqual(_normalize_python_constraint("<3.14, >=3.12"), canonical)

    def test_invalid_or_empty_constraint_is_rejected(self) -> None:
        with self.assertRaises(MaaFWProjectStoreError):
            _normalize_python_constraint("not-a-specifier")
        with self.assertRaises(MaaFWProjectStoreError):
            _normalize_python_constraint("")

    def test_patch_pin_is_accepted_by_the_minor_family_probe(self) -> None:
        # `python313._pth` 只证明 3.13 ABI 家族；==3.13.14 必须被接受并路由到 Pool
        self.assertTrue(_python_constraint_accepts_minor_family("==3.13.14", 3, 13))
        self.assertTrue(_python_constraint_accepts_minor_family(">=3.12,<3.14", 3, 13))

    def test_other_minor_families_are_rejected(self) -> None:
        self.assertFalse(_python_constraint_accepts_minor_family("==3.13.14", 3, 12))
        self.assertFalse(_python_constraint_accepts_minor_family("==3.12.*", 3, 13))


class MaaFWConstraintTest(unittest.TestCase):
    def test_bare_version_is_treated_as_an_exact_pin(self) -> None:
        self.assertTrue(_maafw_constraint_accepts_version("4.0.0", "4.0.0"))
        self.assertTrue(_maafw_constraint_accepts_version("v4.0.0", "4.0.0"))
        self.assertFalse(_maafw_constraint_accepts_version("4.0.0", "4.0.1"))

    def test_specifier_forms_are_honoured(self) -> None:
        self.assertTrue(_maafw_constraint_accepts_version(">=4.0.0,<5", "4.3.1"))
        self.assertFalse(_maafw_constraint_accepts_version(">=4.0.0,<5", "5.0.0"))

    def test_prereleases_are_accepted(self) -> None:
        self.assertTrue(_maafw_constraint_accepts_version(">=4.0.0", "4.1.0rc1"))

    def test_empty_constraint_rejects(self) -> None:
        self.assertFalse(_maafw_constraint_accepts_version("   ", "4.0.0"))

    def test_invalid_constraint_raises(self) -> None:
        with self.assertRaises(MaaFWProjectStoreError):
            _maafw_constraint_accepts_version("~~4", "4.0.0")


class LooksLikeLocalPathTest(unittest.TestCase):
    def test_relative_and_token_prefixes_are_local(self) -> None:
        for value in ("./agent/main.py", "..\\agent", "{PROJECT_DIR}/agent"):
            with self.subTest(value=value):
                self.assertTrue(_looks_like_local_path(value))

    def test_any_separator_makes_it_local(self) -> None:
        self.assertTrue(_looks_like_local_path("agent/main.py"))
        self.assertTrue(_looks_like_local_path("agent\\main.py"))

    def test_bare_script_names_are_local_by_suffix(self) -> None:
        for value in ("main.py", "run.cmd", "run.exe", "run.ps1"):
            with self.subTest(value=value):
                self.assertTrue(_looks_like_local_path(value))

    def test_flags_urls_and_bare_words_are_not_local(self) -> None:
        for value in ("-m", "https://example.invalid/x", "python", ""):
            with self.subTest(value=value):
                self.assertFalse(_looks_like_local_path(value))


if __name__ == "__main__":
    unittest.main()
