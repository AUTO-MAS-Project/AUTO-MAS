from __future__ import annotations

import errno
import hashlib
import json
import multiprocessing
import os
import stat
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

import app.configuration.persistence.generation_store as generation_store_module
from app.configuration.persistence.generation_store import (
    FAULT_POINTS,
    AtomicGenerationStore as _AtomicGenerationStore,
    GenerationConflictError,
    GenerationDurabilityError,
    GenerationIntegrityError,
    GenerationLockTimeoutError,
    GenerationPathLengthError,
    GenerationRecoveryRequiredError,
    NoCommittedGenerationError,
)


class InjectedFault(RuntimeError):
    pass


def AtomicGenerationStore(
    directory: Path,
    **kwargs,
) -> _AtomicGenerationStore:
    """Build the production store with an explicit one-root test schema."""
    kwargs.setdefault("required_roots", ("Config",))
    return _AtomicGenerationStore(directory, **kwargs)


def _generation_path(
    store: _AtomicGenerationStore,
    generation: str,
) -> Path:
    return store.generations_directory / generation


def _root_path(
    store: _AtomicGenerationStore,
    generation: str,
    root_name: str,
) -> Path:
    return _generation_path(store, generation) / "roots" / f"{root_name}.bin"


def _rewrite_selected_manifest(
    store: _AtomicGenerationStore,
    generation: str,
    mutate,
) -> None:
    manifest_path = _generation_path(store, generation) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_bytes = generation_store_module._serialize_json(manifest)
    manifest_path.write_bytes(manifest_bytes)

    current = json.loads(store.current_path.read_text(encoding="utf-8"))
    current["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    store.current_path.write_bytes(
        generation_store_module._serialize_json(current)
    )


def _process_cas_writer(
    store_path: str,
    expected_generation: str,
    expected_revision: int,
    value: bytes,
    start_event,
    result_queue,
) -> None:
    start_event.wait(timeout=10)
    try:
        snapshot = AtomicGenerationStore(Path(store_path)).commit(
            {"Config": value},
            expected_generation=expected_generation,
            expected_revision=expected_revision,
        )
    except GenerationConflictError:
        result_queue.put(("conflict", 0))
    except BaseException as exc:
        result_queue.put(("error", type(exc).__name__))
    else:
        result_queue.put(("committed", snapshot.revision))


class AtomicGenerationStoreTest(unittest.TestCase):
    def test_windows_path_budget_rejects_before_layout_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            with (
                patch.object(
                    generation_store_module,
                    "_uses_windows_legacy_path_limit",
                    return_value=True,
                ),
                patch.object(
                    generation_store_module,
                    "WINDOWS_SAFE_PATH_LIMIT",
                    1,
                ),
                self.assertRaises(GenerationPathLengthError) as captured,
            ):
                AtomicGenerationStore(store_path)

            error = captured.exception
            self.assertEqual(error.role, "staging-root")
            self.assertGreater(
                error.actual_utf16_chars,
                error.limit_utf16_chars,
            )
            self.assertNotIn(str(store_path), str(error))
            self.assertFalse(store_path.exists())

    def test_first_consecutive_commit_and_cross_instance_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            first_store = AtomicGenerationStore(
                store_path,
                required_roots=("Config", "Tools"),
            )

            first = first_store.commit(
                {"Config": b"one", "Tools": b"two"},
                expected_generation=None,
                expected_revision=0,
            )
            second = first_store.commit(
                {"Config": b"three", "Tools": b"four"},
                expected_generation=first.generation,
                expected_revision=first.revision,
            )
            reopened = AtomicGenerationStore(
                store_path,
                required_roots=("Config", "Tools"),
            )
            third = reopened.commit(
                {"Config": b"five", "Tools": b"six"},
                expected_generation=second.generation,
                expected_revision=second.revision,
            )

            self.assertEqual(first.revision, 1)
            self.assertEqual(second.revision, 2)
            self.assertEqual(third.revision, 3)
            self.assertEqual(second.parent_generation, first.generation)
            self.assertEqual(third.parent_generation, second.generation)
            self.assertEqual(dict(reopened.read_current().roots), {
                "Config": b"five",
                "Tools": b"six",
            })
            with self.assertRaises(TypeError):
                current_roots = reopened.read_current().roots
                current_roots["Config"] = b"mutable"  # type: ignore[index]

    def test_required_root_schema_is_nonempty_and_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            with self.assertRaises(TypeError):
                _AtomicGenerationStore(store_path)  # type: ignore[call-arg]
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                _AtomicGenerationStore(store_path, required_roots=())

            store = AtomicGenerationStore(Path(temp_dir) / "store")
            with self.assertRaises(NoCommittedGenerationError):
                store.read_current()

            for roots in ({}, {"Config": b"x", "Extra": b"y"}):
                with self.subTest(roots=tuple(roots)):
                    with self.assertRaisesRegex(ValueError, "root set"):
                        store.commit(
                            roots,
                            expected_generation=None,
                            expected_revision=0,
                        )

            first = store.commit(
                {"Config": b"one"},
                expected_generation=None,
                expected_revision=0,
            )
            self.assertEqual(dict(first.roots), {"Config": b"one"})

    def test_cas_rejects_stale_writer_and_aba_after_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            first = store.commit({"Config": b"A"})
            second = store.commit(
                {"Config": b"B"},
                expected_generation=first.generation,
                expected_revision=first.revision,
            )
            with self.assertRaises(GenerationConflictError):
                store.commit(
                    {"Config": b"stale"},
                    expected_generation=first.generation,
                    expected_revision=first.revision,
                )

            rolled_back = store.rollback(
                first.generation,
                expected_generation=second.generation,
                expected_revision=second.revision,
            )
            self.assertGreater(rolled_back.revision, second.revision)
            self.assertEqual(rolled_back.rollback_of, first.generation)
            self.assertEqual(rolled_back.roots["Config"], b"A")
            self.assertNotEqual(rolled_back.generation, first.generation)

            with self.assertRaises(GenerationConflictError):
                store.commit(
                    {"Config": b"stale-after-aba"},
                    expected_generation=first.generation,
                    expected_revision=first.revision,
                )

    def test_transaction_retry_is_idempotent_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            transaction_id = UUID("11111111-1111-4111-8111-111111111111")
            first = store.commit(
                {"Config": b"same"},
                expected_generation=None,
                expected_revision=0,
                transaction_id=transaction_id,
            )
            retry = AtomicGenerationStore(store.directory).commit(
                {"Config": b"same"},
                expected_generation=None,
                expected_revision=0,
                transaction_id=transaction_id,
            )

            self.assertEqual(retry.generation, first.generation)
            self.assertEqual(retry.revision, first.revision)
            self.assertEqual(
                len(list(store.generations_directory.iterdir())),
                1,
            )
            with self.assertRaises(GenerationConflictError):
                store.commit(
                    {"Config": b"same"},
                    expected_generation=first.generation,
                    expected_revision=first.revision,
                    transaction_id=transaction_id,
                )
            with self.assertRaises(GenerationConflictError):
                store.commit(
                    {"Config": b"different"},
                    transaction_id=transaction_id,
                )
            self.assertEqual(store.read_current().roots["Config"], b"same")

    def test_idempotent_retry_matches_only_original_parent_cas_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            first = store.commit({"Config": b"one"})
            transaction_id = UUID("66666666-6666-4666-8666-666666666666")
            second = store.commit(
                {"Config": b"two"},
                expected_generation=first.generation,
                expected_revision=first.revision,
                transaction_id=transaction_id,
            )

            retry = AtomicGenerationStore(store.directory).commit(
                {"Config": b"two"},
                expected_generation=first.generation,
                expected_revision=first.revision,
                transaction_id=transaction_id,
            )
            self.assertEqual(retry.generation, second.generation)
            with self.assertRaises(GenerationConflictError):
                store.commit(
                    {"Config": b"two"},
                    expected_generation=second.generation,
                    expected_revision=second.revision,
                    transaction_id=transaction_id,
                )

    def test_request_cas_digest_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            snapshot = store.commit({"Config": b"value"})
            _rewrite_selected_manifest(
                store,
                snapshot.generation,
                lambda manifest: manifest.__setitem__(
                    "request_cas_sha256",
                    "0" * 64,
                ),
            )

            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "request CAS",
            ):
                store.read_current()

    def test_committed_lineage_rejects_duplicate_transaction_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            first = store.commit(
                {"Config": b"one"},
                transaction_id=UUID(
                    "77777777-7777-4777-8777-777777777777"
                ),
            )
            duplicate_id = UUID("88888888-8888-4888-8888-888888888888")
            second = store.commit(
                {"Config": b"two"},
                transaction_id=duplicate_id,
            )

            first_path = _generation_path(store, first.generation)
            duplicate_parent = (
                f"g-{first.revision:020d}-{duplicate_id.hex}"
            )
            duplicate_parent_path = store.generations_directory / duplicate_parent
            first_path.rename(duplicate_parent_path)
            first_manifest_path = duplicate_parent_path / "manifest.json"
            first_manifest = json.loads(
                first_manifest_path.read_text(encoding="utf-8")
            )
            first_manifest["generation"] = duplicate_parent
            first_manifest["transaction_id"] = duplicate_id.hex
            first_manifest_bytes = generation_store_module._serialize_json(
                first_manifest
            )
            first_manifest_path.write_bytes(first_manifest_bytes)

            second_manifest_path = (
                _generation_path(store, second.generation) / "manifest.json"
            )
            second_manifest = json.loads(
                second_manifest_path.read_text(encoding="utf-8")
            )
            second_manifest["parent"] = duplicate_parent
            second_manifest["parent_manifest_sha256"] = hashlib.sha256(
                first_manifest_bytes
            ).hexdigest()
            second_manifest["request_cas_sha256"] = (
                generation_store_module._request_cas_sha256(
                    duplicate_parent,
                    first.revision,
                )
            )
            second_manifest_bytes = generation_store_module._serialize_json(
                second_manifest
            )
            second_manifest_path.write_bytes(second_manifest_bytes)
            current = json.loads(
                store.current_path.read_text(encoding="utf-8")
            )
            current["manifest_sha256"] = hashlib.sha256(
                second_manifest_bytes
            ).hexdigest()
            store.current_path.write_bytes(
                generation_store_module._serialize_json(current)
            )

            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "reuses a transaction",
            ):
                store.commit(
                    {"Config": b"three"},
                    expected_generation=second.generation,
                    expected_revision=second.revision,
                )

    def test_two_instances_serialize_concurrent_cas_writers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            first_store = AtomicGenerationStore(store_path)
            second_store = AtomicGenerationStore(store_path)
            baseline = first_store.commit({"Config": b"baseline"})
            barrier = threading.Barrier(2)

            def writer(store: _AtomicGenerationStore, value: bytes):
                barrier.wait(timeout=5)
                try:
                    return store.commit(
                        {"Config": value},
                        expected_generation=baseline.generation,
                        expected_revision=baseline.revision,
                    )
                except GenerationConflictError as exc:
                    return exc

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [
                    executor.submit(writer, first_store, b"one"),
                    executor.submit(writer, second_store, b"two"),
                ]
                resolved = [future.result(timeout=10) for future in results]

            successes = [
                result
                for result in resolved
                if not isinstance(result, GenerationConflictError)
            ]
            conflicts = [
                result
                for result in resolved
                if isinstance(result, GenerationConflictError)
            ]
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(
                AtomicGenerationStore(store_path).read_current().revision,
                baseline.revision + 1,
            )

    def test_cross_process_byte_lock_serializes_cas_writers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            baseline = AtomicGenerationStore(store_path).commit(
                {"Config": b"baseline"}
            )
            context = multiprocessing.get_context("spawn")
            start_event = context.Event()
            result_queue = context.Queue()
            processes = [
                context.Process(
                    target=_process_cas_writer,
                    args=(
                        str(store_path),
                        baseline.generation,
                        baseline.revision,
                        value,
                        start_event,
                        result_queue,
                    ),
                )
                for value in (b"one", b"two")
            ]
            for process in processes:
                process.start()
            start_event.set()
            for process in processes:
                process.join(timeout=20)
            try:
                self.assertTrue(
                    all(not process.is_alive() for process in processes),
                    "cross-process CAS writers did not finish",
                )
                results = [result_queue.get(timeout=5) for _ in processes]
            finally:
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
                result_queue.close()

            self.assertEqual(
                sorted(result[0] for result in results),
                ["committed", "conflict"],
            )
            self.assertEqual(
                AtomicGenerationStore(store_path).read_current().revision,
                baseline.revision + 1,
            )

    def test_lock_timeout_is_explicit_and_has_stable_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(
                Path(temp_dir) / "store",
                lock_timeout_seconds=0.05,
                lock_retry_seconds=0.005,
            )
            process_lock = generation_store_module._process_lock_for(
                store.lock_path
            )
            process_lock.acquire()
            started = time.monotonic()
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        store.commit,
                        {"Config": b"value"},
                    )
                    with self.assertRaises(
                        GenerationLockTimeoutError
                    ) as captured:
                        future.result(timeout=1)
            finally:
                process_lock.release()

            self.assertEqual(
                captured.exception.error_code,
                "generation_lock_timeout",
            )
            self.assertLess(time.monotonic() - started, 1)

    @unittest.skipUnless(os.name == "nt", "Windows byte-lock semantics")
    def test_windows_byte_lock_uses_nonblocking_retry_deadline(self) -> None:
        import msvcrt

        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "LOCK"
            lock_path.write_bytes(b"\0")
            started = time.monotonic()
            with lock_path.open("r+b") as stream:
                with patch.object(
                    msvcrt,
                    "locking",
                    side_effect=OSError(errno.EACCES, "busy"),
                ) as locking:
                    with self.assertRaises(
                        GenerationLockTimeoutError
                    ) as captured:
                        generation_store_module._lock_one_byte(
                            stream,
                            deadline=time.monotonic() + 0.05,
                            retry_interval=0.005,
                        )

            self.assertEqual(
                captured.exception.error_code,
                "generation_lock_timeout",
            )
            self.assertLess(time.monotonic() - started, 1)
            self.assertGreater(locking.call_count, 1)
            self.assertTrue(
                all(
                    call.args[1] == msvcrt.LK_NBLCK
                    for call in locking.call_args_list
                )
            )

    def test_current_manifest_and_root_corruption_fail_closed(self) -> None:
        mutations = (
            "current_json",
            "current_missing",
            "manifest_hash",
            "manifest_revision_bool",
            "manifest_missing",
            "root_hash",
            "root_size",
            "root_missing",
            "extra_root",
            "extra_generation_entry",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory() as temp_dir:
                    store = AtomicGenerationStore(Path(temp_dir) / "store")
                    snapshot = store.commit({"Config": b"payload"})
                    generation_path = _generation_path(
                        store,
                        snapshot.generation,
                    )
                    manifest_path = generation_path / "manifest.json"
                    root_path = _root_path(
                        store,
                        snapshot.generation,
                        "Config",
                    )

                    if mutation == "current_json":
                        store.current_path.write_bytes(b"{broken")
                    elif mutation == "current_missing":
                        store.current_path.unlink()
                    elif mutation == "manifest_hash":
                        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
                    elif mutation == "manifest_revision_bool":
                        _rewrite_selected_manifest(
                            store,
                            snapshot.generation,
                            lambda manifest: manifest.__setitem__(
                                "revision",
                                True,
                            ),
                        )
                    elif mutation == "manifest_missing":
                        manifest_path.unlink()
                    elif mutation == "root_hash":
                        root_path.write_bytes(b"payloae")
                    elif mutation == "root_size":
                        root_path.write_bytes(b"payload-extra")
                    elif mutation == "root_missing":
                        root_path.unlink()
                    elif mutation == "extra_root":
                        (generation_path / "roots" / "extra.bin").write_bytes(
                            b"extra"
                        )
                    elif mutation == "extra_generation_entry":
                        (generation_path / "extra.txt").write_bytes(b"extra")

                    with self.assertRaises(
                        (GenerationIntegrityError, NoCommittedGenerationError)
                    ):
                        AtomicGenerationStore(store.directory).read_current()

    def test_dangling_or_reparse_root_is_rejected_lexically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            snapshot = store.commit({"Config": b"payload"})
            root_path = _root_path(store, snapshot.generation, "Config")
            real_lexical_stat = generation_store_module._lexical_stat
            real_stat = root_path.lstat()
            reparse_attribute = getattr(
                stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0x400,
            )
            fake_reparse = SimpleNamespace(
                st_mode=real_stat.st_mode,
                st_file_attributes=reparse_attribute,
                st_size=real_stat.st_size,
            )

            def lexical_stat(path: Path):
                if path == root_path:
                    return fake_reparse
                return real_lexical_stat(path)

            with patch.object(
                generation_store_module,
                "_lexical_stat",
                side_effect=lexical_stat,
            ):
                with self.assertRaisesRegex(
                    GenerationIntegrityError,
                    "missing or unsafe",
                ):
                    store.read_current()

    def test_strict_root_names_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            for invalid_name in ("../Config", "Config.json", "CON", "a b", ""):
                with self.subTest(name=invalid_name):
                    with self.assertRaises(ValueError):
                        _AtomicGenerationStore(
                            store_path,
                            required_roots=(invalid_name,),
                        )
            with self.assertRaisesRegex(ValueError, "collide"):
                _AtomicGenerationStore(
                    store_path,
                    required_roots=("Config", "config"),
                )
            with self.assertRaisesRegex(ValueError, "root count"):
                _AtomicGenerationStore(
                    store_path,
                    required_roots=("A", "B", "C"),
                    max_roots=2,
                )

            store = AtomicGenerationStore(
                store_path,
                required_roots=("A", "B"),
                max_roots=2,
                max_root_bytes=4,
                max_total_bytes=6,
            )
            with self.assertRaisesRegex(ValueError, "root set"):
                store.commit({"A": b"x"})
            with self.assertRaisesRegex(ValueError, "root set"):
                store.commit({"A": b"x", "B": b"y", "C": b"z"})
            with self.assertRaisesRegex(ValueError, "root size"):
                store.commit({"A": b"12345", "B": b"x"})
            with self.assertRaisesRegex(ValueError, "total root size"):
                store.commit({"A": b"1234", "B": b"567"})

    def test_root_set_digest_is_persisted_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            snapshot = store.commit({"Config": b"value"})

            incompatible = AtomicGenerationStore(
                store.directory,
                required_roots=("Other",),
            )
            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "identity metadata",
            ):
                incompatible.read_current()

            _rewrite_selected_manifest(
                store,
                snapshot.generation,
                lambda manifest: manifest.__setitem__(
                    "root_set_sha256",
                    "0" * 64,
                ),
            )
            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "identity metadata",
            ):
                store.read_current()

    def test_each_fault_window_reopens_with_old_or_new_authority(self) -> None:
        for point in FAULT_POINTS:
            with self.subTest(point=point):
                with tempfile.TemporaryDirectory() as temp_dir:
                    store_path = Path(temp_dir) / "store"
                    baseline_store = AtomicGenerationStore(store_path)
                    baseline = baseline_store.commit({"Config": b"old"})

                    def fault_hook(actual_point: str) -> None:
                        if actual_point == point:
                            raise InjectedFault(point)

                    faulting_store = AtomicGenerationStore(
                        store_path,
                        fault_hook=fault_hook,
                    )
                    with self.assertRaisesRegex(InjectedFault, point):
                        faulting_store.commit(
                            {"Config": b"new"},
                            expected_generation=baseline.generation,
                            expected_revision=baseline.revision,
                        )

                    reopened = AtomicGenerationStore(store_path)
                    current = reopened.read_current()
                    if point == "after_current_replace":
                        self.assertEqual(current.roots["Config"], b"new")
                        self.assertEqual(current.revision, baseline.revision + 1)
                        self.assertEqual(reopened.list_orphans(), ())
                    else:
                        self.assertEqual(current.generation, baseline.generation)
                        self.assertEqual(current.roots["Config"], b"old")
                        orphans = reopened.list_orphans()
                        expected_count = (
                            2 if point == "before_current_replace" else 1
                        )
                        self.assertEqual(len(orphans), expected_count)
                        expected_kind = (
                            "published"
                            if point
                            in {
                                "after_generation_rename",
                                "before_current_replace",
                            }
                            else "staging"
                        )
                        self.assertIn(
                            expected_kind,
                            {orphan.kind for orphan in orphans},
                        )
                        if point == "before_current_replace":
                            current_temp = next(
                                orphan
                                for orphan in orphans
                                if orphan.kind == "current-temp"
                            )
                            self.assertTrue(current_temp.valid)

    def test_durable_current_replace_failure_is_not_treated_as_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            baseline = store.commit({"Config": b"old"})
            real_durable_move = generation_store_module._durable_move

            def fail_current_replace(
                source: Path,
                destination: Path,
                *,
                replace_existing: bool,
            ) -> None:
                if destination == store.current_path:
                    raise GenerationDurabilityError(
                        "injected durable replacement failure"
                    )
                real_durable_move(
                    source,
                    destination,
                    replace_existing=replace_existing,
                )

            with patch.object(
                generation_store_module,
                "_durable_move",
                side_effect=fail_current_replace,
            ):
                with self.assertRaises(
                    GenerationDurabilityError
                ) as captured:
                    store.commit(
                        {"Config": b"new"},
                        expected_generation=baseline.generation,
                        expected_revision=baseline.revision,
                    )

            self.assertEqual(
                captured.exception.error_code,
                "generation_durability_error",
            )
            self.assertEqual(store.read_current().generation, baseline.generation)
            self.assertEqual(
                {orphan.kind for orphan in store.list_orphans()},
                {"published", "current-temp"},
            )

    @unittest.skipUnless(os.name == "nt", "Windows durable-move flags")
    def test_windows_move_file_ex_always_requests_write_through(self) -> None:
        move_file_ex = Mock(return_value=1)
        kernel32 = SimpleNamespace(MoveFileExW=move_file_ex)
        with patch("ctypes.WinDLL", return_value=kernel32):
            generation_store_module._move_file_ex_windows(
                Path(r"C:\source"),
                Path(r"C:\destination"),
                replace_existing=False,
            )
            generation_store_module._move_file_ex_windows(
                Path(r"C:\source"),
                Path(r"C:\destination"),
                replace_existing=True,
            )

        self.assertEqual(move_file_ex.call_args_list[0].args[2], 0x8)
        self.assertEqual(move_file_ex.call_args_list[1].args[2], 0x9)

    def test_fault_hook_cannot_smuggle_unvalidated_publish_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            baseline = AtomicGenerationStore(store_path).commit(
                {"Config": b"old"}
            )
            staging_store: _AtomicGenerationStore

            def alter_staging(point: str) -> None:
                if point != "before_generation_rename":
                    return
                pending = next(staging_store.staging_directory.iterdir())
                (pending / "unexpected.bin").write_bytes(b"unsafe")

            staging_store = AtomicGenerationStore(
                store_path,
                fault_hook=alter_staging,
            )
            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "unexpected entries",
            ):
                staging_store.commit({"Config": b"new"})
            self.assertEqual(
                AtomicGenerationStore(store_path).read_current().generation,
                baseline.generation,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            baseline = AtomicGenerationStore(store_path).commit(
                {"Config": b"old"}
            )
            current_store: _AtomicGenerationStore

            def alter_current_temp(point: str) -> None:
                if point != "before_current_replace":
                    return
                current_temp = next(
                    current_store.directory.glob(".CURRENT.*.tmp")
                )
                current_temp.write_bytes(b"{}")

            current_store = AtomicGenerationStore(
                store_path,
                fault_hook=alter_current_temp,
            )
            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "integrity differs",
            ):
                current_store.commit({"Config": b"new"})
            self.assertEqual(
                AtomicGenerationStore(store_path).read_current().generation,
                baseline.generation,
            )

    def test_orphan_is_never_auto_committed_or_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            baseline_store = AtomicGenerationStore(store_path)
            baseline = baseline_store.commit({"Config": b"old"})

            def fault_hook(point: str) -> None:
                if point == "after_generation_rename":
                    raise InjectedFault(point)

            faulting = AtomicGenerationStore(store_path, fault_hook=fault_hook)
            with self.assertRaises(InjectedFault):
                faulting.commit(
                    {"Config": b"orphan"},
                    expected_generation=baseline.generation,
                    expected_revision=baseline.revision,
                    transaction_id=UUID(
                        "22222222-2222-4222-8222-222222222222"
                    ),
                )

            reopened = AtomicGenerationStore(store_path)
            orphan = reopened.list_orphans()[0]
            orphan_path = _root_path(
                reopened,
                orphan.generation,
                "Config",
            )
            orphan_bytes = orphan_path.read_bytes()
            committed = reopened.commit(
                {"Config": b"next"},
                expected_generation=baseline.generation,
                expected_revision=baseline.revision,
            )

            self.assertGreater(committed.revision, orphan.revision)
            self.assertNotEqual(committed.generation, orphan.generation)
            self.assertEqual(orphan_path.read_bytes(), orphan_bytes)
            self.assertEqual(orphan_bytes, b"orphan")
            self.assertEqual(reopened.read_current().roots["Config"], b"next")

    def test_rollback_skips_orphan_revision_and_keeps_current_monotonic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            store = AtomicGenerationStore(store_path)
            first = store.commit({"Config": b"A"})
            second = store.commit({"Config": b"B"})

            def fault_hook(point: str) -> None:
                if point == "after_generation_rename":
                    raise InjectedFault(point)

            with self.assertRaises(InjectedFault):
                AtomicGenerationStore(
                    store_path,
                    fault_hook=fault_hook,
                ).commit({"Config": b"never-current"})
            orphan = store.list_orphans()[0]
            rolled_back = store.rollback(
                first.generation,
                expected_generation=second.generation,
                expected_revision=second.revision,
            )

            self.assertGreater(rolled_back.revision, orphan.revision)
            self.assertEqual(rolled_back.rollback_of, first.generation)
            self.assertEqual(rolled_back.parent_generation, second.generation)
            self.assertEqual(rolled_back.roots["Config"], b"A")

    def test_rollback_rejects_published_orphan_as_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"
            store = AtomicGenerationStore(store_path)
            current = store.commit({"Config": b"current"})

            def fault_hook(point: str) -> None:
                if point == "after_generation_rename":
                    raise InjectedFault(point)

            with self.assertRaises(InjectedFault):
                AtomicGenerationStore(
                    store_path,
                    fault_hook=fault_hook,
                ).commit({"Config": b"orphan"})
            orphan = store.list_orphans()[0]

            with self.assertRaisesRegex(
                GenerationConflictError,
                "committed lineage",
            ):
                store.rollback(
                    orphan.generation,
                    expected_generation=current.generation,
                    expected_revision=current.revision,
                )

    def test_rollback_requires_strict_ancestor_and_matching_target_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            first = store.commit({"Config": b"A"})
            with self.assertRaisesRegex(
                GenerationConflictError,
                "strict committed ancestor",
            ):
                store.rollback(
                    first.generation,
                    expected_generation=first.generation,
                    expected_revision=first.revision,
                )

            second = store.commit({"Config": b"B"})
            rollback = store.rollback(
                first.generation,
                expected_generation=second.generation,
                expected_revision=second.revision,
            )
            _rewrite_selected_manifest(
                store,
                rollback.generation,
                lambda manifest: manifest.__setitem__(
                    "rollback_of",
                    second.generation,
                ),
            )
            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "rollback roots differ",
            ):
                store.commit(
                    {"Config": b"C"},
                    expected_generation=rollback.generation,
                    expected_revision=rollback.revision,
                )

    def test_parent_manifest_hash_anchors_rollback_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            first = store.commit({"Config": b"A"})
            second = store.commit({"Config": b"B"})
            first_manifest = (
                _generation_path(store, first.generation) / "manifest.json"
            )
            first_manifest.write_bytes(first_manifest.read_bytes() + b" ")

            # Reading CURRENT validates only the selected complete generation.
            self.assertEqual(store.read_current().generation, second.generation)
            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "parent metadata differs",
            ):
                store.rollback(
                    first.generation,
                    expected_generation=second.generation,
                    expected_revision=second.revision,
                )
            with self.assertRaisesRegex(
                GenerationIntegrityError,
                "parent metadata differs",
            ):
                store.commit(
                    {"Config": b"C"},
                    expected_generation=second.generation,
                    expected_revision=second.revision,
                )

    def test_commit_validates_history_without_loading_old_root_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            first = store.commit({"Config": b"A"})
            second = store.commit({"Config": b"B"})
            third = store.commit({"Config": b"C"})
            forbidden_paths = {
                _root_path(store, first.generation, "Config"),
                _root_path(store, second.generation, "Config"),
            }
            real_read = generation_store_module._read_plain_bytes

            def reject_historical_payload(path: Path, **kwargs):
                if path in forbidden_paths:
                    raise AssertionError(
                        "historical root payload was loaded"
                    )
                return real_read(path, **kwargs)

            with patch.object(
                generation_store_module,
                "_read_plain_bytes",
                side_effect=reject_historical_payload,
            ):
                fourth = store.commit(
                    {"Config": b"D"},
                    expected_generation=third.generation,
                    expected_revision=third.revision,
                )
            self.assertEqual(fourth.roots["Config"], b"D")

    def test_rollback_transaction_retry_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            first = store.commit({"Config": b"A"})
            second = store.commit({"Config": b"B"})
            transaction_id = UUID("33333333-3333-4333-8333-333333333333")
            rollback = store.rollback(
                first.generation,
                expected_generation=second.generation,
                expected_revision=second.revision,
                transaction_id=transaction_id,
            )
            retry = AtomicGenerationStore(store.directory).rollback(
                first.generation,
                expected_generation=second.generation,
                expected_revision=second.revision,
                transaction_id=transaction_id,
            )
            self.assertEqual(retry.generation, rollback.generation)
            self.assertEqual(retry.revision, rollback.revision)

    def test_sensitive_bytes_never_enter_repr_or_integrity_exception(self) -> None:
        secret = b"super-secret-token-DO-NOT-LOG"
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(
                Path(temp_dir) / "store",
                required_roots=("Secrets",),
            )
            snapshot = store.commit({"Secrets": secret})
            self.assertNotIn(secret.decode(), repr(snapshot))

            root_path = _root_path(store, snapshot.generation, "Secrets")
            root_path.write_bytes(b"X" * len(secret))
            with self.assertRaises(GenerationIntegrityError) as captured:
                store.read_current()
            self.assertNotIn(secret.decode(), str(captured.exception))
            self.assertNotIn(secret.decode(), repr(captured.exception))

    def test_current_is_not_recovered_from_a_lone_published_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            snapshot = store.commit({"Config": b"committed"})
            store.current_path.unlink()

            reopened = AtomicGenerationStore(store.directory)
            with self.assertRaises(GenerationRecoveryRequiredError):
                reopened.read_current()
            with self.assertRaises(GenerationRecoveryRequiredError):
                reopened.commit(
                    {"Config": b"must-not-create-new-genesis"},
                    expected_generation=None,
                    expected_revision=0,
                )
            orphans = reopened.list_orphans()
            self.assertEqual(
                [(item.generation, item.kind, item.valid) for item in orphans],
                [(snapshot.generation, "published", True)],
            )
            self.assertFalse(reopened.current_path.exists())

    def test_recover_initial_generation_requires_explicit_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            initial = store.commit({"Config": b"genesis"})
            generation_path = _generation_path(store, initial.generation)
            before = {
                path.relative_to(generation_path): path.read_bytes()
                for path in generation_path.rglob("*")
                if path.is_file()
            }
            store.current_path.unlink()

            reopened = AtomicGenerationStore(store.directory)
            with self.assertRaises(GenerationIntegrityError):
                reopened.recover_initial_generation(
                    generation=initial.generation,
                    manifest_sha256="f" * 64,
                )
            self.assertFalse(reopened.current_path.exists())
            self.assertEqual(
                {
                    path.relative_to(generation_path): path.read_bytes()
                    for path in generation_path.rglob("*")
                    if path.is_file()
                },
                before,
            )

            recovered = reopened.recover_initial_generation(
                generation=initial.generation,
                manifest_sha256=initial.manifest_sha256,
            )
            self.assertEqual(recovered.generation, initial.generation)
            self.assertEqual(reopened.read_current().roots["Config"], b"genesis")
            self.assertEqual(reopened.list_orphans(), ())
            self.assertEqual(
                {
                    path.relative_to(generation_path): path.read_bytes()
                    for path in generation_path.rglob("*")
                    if path.is_file()
                },
                before,
            )

    def test_recover_initial_generation_never_replaces_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            initial = store.commit({"Config": b"genesis"})
            before = store.current_path.read_bytes()

            with self.assertRaises(GenerationConflictError):
                store.recover_initial_generation(
                    generation=initial.generation,
                    manifest_sha256=initial.manifest_sha256,
                )
            self.assertEqual(store.current_path.read_bytes(), before)
            self.assertEqual(store.read_current().generation, initial.generation)

    def test_recover_initial_generation_rejects_competing_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "store")
            initial = store.commit({"Config": b"genesis"})
            store.current_path.unlink()
            staging = store.staging_directory / (
                ".pending-g-00000000000000000002-" + "a" * 32
            )
            staging.mkdir()
            entries_before = sorted(
                path.relative_to(store.directory).as_posix()
                for path in store.directory.rglob("*")
            )

            reopened = AtomicGenerationStore(store.directory)
            with self.assertRaises(GenerationRecoveryRequiredError):
                reopened.recover_initial_generation(
                    generation=initial.generation,
                    manifest_sha256=initial.manifest_sha256,
                )
            self.assertFalse(reopened.current_path.exists())
            self.assertEqual(
                sorted(
                    path.relative_to(store.directory).as_posix()
                    for path in store.directory.rglob("*")
                ),
                entries_before,
            )

    def test_recover_initial_generation_preserves_temp_evidence_on_fault(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "store"

            def publish_fault(point: str) -> None:
                if point == "after_generation_rename":
                    raise InjectedFault(point)

            with self.assertRaises(InjectedFault):
                AtomicGenerationStore(
                    store_path,
                    fault_hook=publish_fault,
                ).commit({"Config": b"genesis"})

            reopened = AtomicGenerationStore(store_path)
            orphan = reopened.list_orphans()[0]
            candidate = reopened.inspect_generation(orphan.generation)

            def recovery_fault(point: str) -> None:
                if point == "before_current_replace":
                    raise InjectedFault(point)

            with self.assertRaises(InjectedFault):
                AtomicGenerationStore(
                    store_path,
                    fault_hook=recovery_fault,
                ).recover_initial_generation(
                    generation=candidate.generation,
                    manifest_sha256=candidate.manifest_sha256,
                )

            interrupted = AtomicGenerationStore(store_path)
            self.assertFalse(interrupted.current_path.exists())
            self.assertEqual(
                {item.kind for item in interrupted.list_orphans()},
                {"published", "current-temp"},
            )

            recovered = interrupted.recover_initial_generation(
                generation=candidate.generation,
                manifest_sha256=candidate.manifest_sha256,
            )
            self.assertEqual(recovered.generation, candidate.generation)
            self.assertEqual(interrupted.read_current().roots["Config"], b"genesis")
            self.assertEqual(
                [item.kind for item in interrupted.list_orphans()],
                ["current-temp"],
            )

    def test_missing_current_with_staging_or_current_temp_blocks_genesis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "staging-store"

            def fault_hook(point: str) -> None:
                if point == "after_staging_write":
                    raise InjectedFault(point)

            with self.assertRaises(InjectedFault):
                AtomicGenerationStore(
                    store_path,
                    fault_hook=fault_hook,
                ).commit({"Config": b"pending"})
            staging_store = AtomicGenerationStore(store_path)
            with self.assertRaises(GenerationRecoveryRequiredError):
                staging_store.commit({"Config": b"new-genesis"})
            self.assertEqual(
                [orphan.kind for orphan in staging_store.list_orphans()],
                ["staging"],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(Path(temp_dir) / "temp-store")
            current_temp = store.directory / (
                ".CURRENT."
                "44444444444444448444444444444444."
                "55555555555545558555555555555555.tmp"
            )
            current_temp.write_bytes(b"{}")

            with self.assertRaises(GenerationRecoveryRequiredError):
                store.read_current()
            with self.assertRaises(GenerationRecoveryRequiredError):
                store.commit({"Config": b"new-genesis"})
            orphans = store.list_orphans()
            self.assertEqual(len(orphans), 1)
            self.assertEqual(orphans[0].kind, "current-temp")
            self.assertFalse(orphans[0].valid)

    def test_manifest_schema_and_root_files_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(
                Path(temp_dir) / "store",
                required_roots=("ARoot", "zRoot"),
            )
            snapshot = store.commit({"zRoot": b"z", "ARoot": b"a"})
            generation_path = _generation_path(store, snapshot.generation)
            manifest = json.loads(
                (generation_path / "manifest.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                [record["name"] for record in manifest["roots"]],
                ["ARoot", "zRoot"],
            )
            self.assertEqual(
                {path.name for path in (generation_path / "roots").iterdir()},
                {"ARoot.bin", "zRoot.bin"},
            )
            self.assertEqual(
                set(manifest),
                {
                    "schema_version",
                    "kind",
                    "revision",
                    "generation",
                    "parent",
                    "parent_revision",
                    "parent_manifest_sha256",
                    "transaction_id",
                    "rollback_of",
                    "root_set_sha256",
                    "request_cas_sha256",
                    "roots",
                },
            )
            self.assertEqual(
                manifest["root_set_sha256"],
                store.root_set_sha256,
            )


if __name__ == "__main__":
    unittest.main()
