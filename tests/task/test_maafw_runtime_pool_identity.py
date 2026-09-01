"""`automas_maafw_runtime_pool` 的导入与纯逻辑回归。

该包由 `mfwa` 逐字节移入（见 `docs/迁移审计/maafw-移植基准对照-20260830.md` §2），
本文件只覆盖不触碰文件系统、不联网、不安装解释器的纯选择器逻辑。
"""

import importlib
import unittest

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
    MaaFWRuntimeIdentityError,
    MaaFWRuntimePool,
    MaaFWRuntimePoolError,
    MaaFWRuntimePoolService,
    POOL_MARKER_NAME,
    POOL_SCHEMA_VERSION,
    build_runtime_id,
    build_runtime_identity,
    canonicalize_requirements,
    find_maafw_requirement,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.identity import (
    infer_exact_maafw_version,
    requirement_distribution_name,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.service import (
    _normalize_python_request,
    _normalize_runtime_request,
    _request_contains_selector,
    _runtime_matches_request,
)

PROBED_PYTHON = {
    "implementation": "cpython",
    "cacheTag": "cpython-313",
    "soabi": "cp313-win_amd64",
    "version": "3.13.14",
    "platform": "win-amd64",
    "architecture": "AMD64",
}


class RuntimePoolPackageImportTest(unittest.TestCase):
    def test_public_surface_is_importable(self) -> None:
        self.assertTrue(issubclass(MaaFWRuntimePoolError, RuntimeError))
        self.assertTrue(issubclass(MaaFWRuntimeIdentityError, ValueError))
        self.assertIsInstance(POOL_MARKER_NAME, str)
        self.assertIsInstance(POOL_SCHEMA_VERSION, int)
        for symbol in (MaaFWRuntimePool, MaaFWRuntimePoolService):
            self.assertTrue(callable(symbol))

    def test_submodules_import_without_side_effects(self) -> None:
        base = "app.task.MaaFW.tools.core.automas_maafw_runtime_pool"
        for name in ("cache", "identity", "installer", "pool", "service"):
            self.assertIsNotNone(importlib.import_module(base + "." + name))


class CanonicalizeRequirementsTest(unittest.TestCase):
    def test_order_independent_and_case_normalized(self) -> None:
        left = canonicalize_requirements(["MaaFW==4.0.0", "Pillow>=10"])
        right = canonicalize_requirements([" pillow>=10 ", "maafw==4.0.0"])
        self.assertEqual(left, right)
        self.assertEqual(left, ("maafw==4.0.0", "pillow>=10"))

    def test_comments_and_blank_lines_are_dropped(self) -> None:
        self.assertEqual(
            canonicalize_requirements(["# comment", "", "  ", "maafw==4.0.0"]),
            ("maafw==4.0.0",),
        )

    def test_extras_are_sorted_within_a_requirement(self) -> None:
        self.assertEqual(
            canonicalize_requirements(["Pkg[Zeta,alpha]>=1"]),
            ("pkg[alpha,zeta]>=1",),
        )

    def test_empty_selector_is_rejected(self) -> None:
        with self.assertRaises(MaaFWRuntimeIdentityError):
            canonicalize_requirements([])
        with self.assertRaises(MaaFWRuntimeIdentityError):
            canonicalize_requirements(["# only a comment"])

    def test_non_string_entry_is_rejected(self) -> None:
        with self.assertRaises(MaaFWRuntimeIdentityError):
            canonicalize_requirements([object()])  # type: ignore[list-item]

    def test_local_and_editable_requirements_are_rejected(self) -> None:
        rejected = (
            "-e .",
            "./vendor/maafw",
            "../maafw",
            "C:/tmp/maafw-4.0.0-py3-none-any.whl",
            "file:///tmp/maafw",
            "maafw @ file:///tmp/maafw",
            "maafw.zip",
            # 归档后缀按后缀判定，不分 scheme —— 远端 wheel 同样被拒
            "maafw @ https://example.invalid/maafw.whl",
        )
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(MaaFWRuntimeIdentityError):
                    canonicalize_requirements([value])

    def test_non_archive_remote_url_requirement_is_allowed(self) -> None:
        self.assertEqual(
            canonicalize_requirements(["maafw @ https://example.invalid/simple"]),
            ("maafw @ https://example.invalid/simple",),
        )


class RuntimeIdentityTest(unittest.TestCase):
    def test_identity_uses_probed_interpreter_verbatim(self) -> None:
        identity = build_runtime_identity(
            ["maafw==4.0.0"],
            python_identity=PROBED_PYTHON,
        )
        self.assertEqual(identity["pythonAbi"], "cpython:cpython-313:cp313-win_amd64")
        self.assertEqual(identity["pythonVersion"], "3.13.14")
        self.assertEqual(identity["platform"], "win-amd64")
        self.assertEqual(identity["architecture"], "AMD64")
        self.assertEqual(identity["requirements"], ["maafw==4.0.0"])

    def test_identity_accepts_python_version_fallback_key(self) -> None:
        probed = dict(PROBED_PYTHON)
        probed.pop("version")
        probed["pythonVersion"] = "3.13.14"
        identity = build_runtime_identity(["maafw==4.0.0"], python_identity=probed)
        self.assertEqual(identity["pythonVersion"], "3.13.14")

    def test_identity_rejects_incomplete_probe(self) -> None:
        probed = dict(PROBED_PYTHON)
        probed["soabi"] = "   "
        with self.assertRaises(MaaFWRuntimeIdentityError):
            build_runtime_identity(["maafw==4.0.0"], python_identity=probed)

    def test_host_interpreter_identity_is_self_describing(self) -> None:
        identity = build_runtime_identity(["maafw==4.0.0"])
        self.assertEqual(identity["requirements"], ["maafw==4.0.0"])
        self.assertEqual(identity["pythonAbi"].count(":"), 2)
        self.assertTrue(identity["pythonVersion"])

    def test_runtime_id_is_stable_and_order_independent(self) -> None:
        first = build_runtime_id(
            ["maafw==4.0.0", "pillow>=10"],
            python_identity=PROBED_PYTHON,
        )
        second = build_runtime_id(
            ["Pillow>=10", "MaaFW==4.0.0"],
            python_identity=PROBED_PYTHON,
        )
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("maafw-runtime-"))
        self.assertEqual(len(first), len("maafw-runtime-") + 24)

    def test_patch_version_change_selects_a_new_runtime(self) -> None:
        older = dict(PROBED_PYTHON, version="3.13.13")
        self.assertNotEqual(
            build_runtime_id(["maafw==4.0.0"], python_identity=PROBED_PYTHON),
            build_runtime_id(["maafw==4.0.0"], python_identity=older),
        )

    def test_requirement_change_selects_a_new_runtime(self) -> None:
        self.assertNotEqual(
            build_runtime_id(["maafw==4.0.0"], python_identity=PROBED_PYTHON),
            build_runtime_id(["maafw==4.1.0"], python_identity=PROBED_PYTHON),
        )


class MaaFWRequirementLookupTest(unittest.TestCase):
    def test_finds_maafw_regardless_of_spelling(self) -> None:
        self.assertEqual(
            find_maafw_requirement(["pillow>=10", "MaaFW==4.0.0"]),
            "maafw==4.0.0",
        )

    def test_returns_none_when_absent(self) -> None:
        self.assertIsNone(find_maafw_requirement(["pillow>=10"]))

    def test_distribution_name_falls_back_for_non_pep508(self) -> None:
        self.assertEqual(requirement_distribution_name("MaaFW==4.0.0"), "maafw")
        self.assertEqual(requirement_distribution_name("MaaFW =!= 1"), "maafw")

    def test_exact_version_inference(self) -> None:
        self.assertEqual(infer_exact_maafw_version("maafw==4.0.0"), "4.0.0")
        self.assertIsNone(infer_exact_maafw_version("maafw>=4.0.0"))
        self.assertIsNone(infer_exact_maafw_version("maafw==4.0.*"))
        self.assertIsNone(infer_exact_maafw_version("pillow==4.0.0"))
        self.assertIsNone(infer_exact_maafw_version(None))


class RuntimeRequestNormalizationTest(unittest.TestCase):
    def test_bare_string_becomes_a_single_requirement(self) -> None:
        requirements, metadata, touch, python = _normalize_runtime_request(
            " maafw==4.0.0 "
        )
        self.assertEqual(requirements, ["maafw==4.0.0"])
        self.assertEqual(metadata, {})
        self.assertFalse(touch)
        self.assertIsNone(python)

    def test_empty_string_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_runtime_request("   ")

    def test_mapping_aliases_are_accepted(self) -> None:
        for key in ("requirements", "packages"):
            with self.subTest(key=key):
                requirements = _normalize_runtime_request({key: ["maafw==4.0.0"]})[0]
                self.assertEqual(requirements, ["maafw==4.0.0"])
        for key in ("maafwRequirement", "requirement"):
            with self.subTest(key=key):
                requirements = _normalize_runtime_request({key: "maafw==4.0.0"})[0]
                self.assertEqual(requirements, ["maafw==4.0.0"])

    def test_metadata_and_touch_are_carried_through(self) -> None:
        _, metadata, touch, _ = _normalize_runtime_request(
            {"requirements": ["maafw==4.0.0"], "metadata": {"a": 1}, "touch": True}
        )
        self.assertEqual(metadata, {"a": 1})
        self.assertTrue(touch)

    def test_bad_requirement_container_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            _normalize_runtime_request({"requirements": {"a": "b"}})
        with self.assertRaises(TypeError):
            _normalize_runtime_request({"requirements": [1, 2]})
        with self.assertRaises(TypeError):
            _normalize_runtime_request(object())  # type: ignore[arg-type]

    def test_selector_detection(self) -> None:
        self.assertTrue(_request_contains_selector({"requirements": []}))
        self.assertTrue(_request_contains_selector({"python": {"constraint": "3.13"}}))
        self.assertFalse(_request_contains_selector({"metadata": {}}))

    def test_minor_only_python_constraint_is_widened(self) -> None:
        self.assertEqual(
            _normalize_python_request({"constraint": "3.13"}),
            {"implementation": "cpython", "constraint": "==3.13.*"},
        )

    def test_python_constraint_must_be_present_and_valid(self) -> None:
        self.assertIsNone(_normalize_python_request(None))
        with self.assertRaises(ValueError):
            _normalize_python_request({"constraint": "  "})
        with self.assertRaises(ValueError):
            _normalize_python_request({"constraint": "not-a-specifier"})
        with self.assertRaises(TypeError):
            _normalize_python_request("3.13")


class RuntimeMatchesRequestTest(unittest.TestCase):
    RUNTIME = {
        "selectorRequirements": ["maafw==4.0.0"],
        "identity": {
            "pythonAbi": "cpython:cpython-313:cp313-win_amd64",
            "pythonVersion": "3.13.14",
        },
    }

    def test_matching_requirements_only(self) -> None:
        self.assertTrue(
            _runtime_matches_request(
                self.RUNTIME,
                requirements=["MaaFW==4.0.0"],
                python_request=None,
            )
        )

    def test_requirement_mismatch_rejects(self) -> None:
        self.assertFalse(
            _runtime_matches_request(
                self.RUNTIME,
                requirements=["maafw==4.1.0"],
                python_request=None,
            )
        )

    def test_python_constraint_is_applied_to_identity(self) -> None:
        self.assertTrue(
            _runtime_matches_request(
                self.RUNTIME,
                requirements=None,
                python_request={"implementation": "cpython", "constraint": "==3.13.*"},
            )
        )
        self.assertFalse(
            _runtime_matches_request(
                self.RUNTIME,
                requirements=None,
                python_request={"implementation": "cpython", "constraint": "==3.12.*"},
            )
        )

    def test_implementation_mismatch_rejects(self) -> None:
        self.assertFalse(
            _runtime_matches_request(
                self.RUNTIME,
                requirements=None,
                python_request={"implementation": "pypy", "constraint": "==3.13.*"},
            )
        )

    def test_missing_or_invalid_identity_rejects(self) -> None:
        python_request = {"implementation": "cpython", "constraint": "==3.13.*"}
        self.assertFalse(
            _runtime_matches_request(
                {"selectorRequirements": []},
                requirements=None,
                python_request=python_request,
            )
        )
        self.assertFalse(
            _runtime_matches_request(
                {"identity": {"pythonAbi": "cpython:x:y", "pythonVersion": "bad"}},
                requirements=None,
                python_request=python_request,
            )
        )


if __name__ == "__main__":
    unittest.main()
