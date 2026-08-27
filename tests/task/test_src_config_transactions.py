import tempfile
import unittest
from pathlib import Path

from app.task.SRC.tools.config import (
    is_src_config_available,
    read_src_installation_id,
    recover_interrupted_src_config_swap,
    stage_src_config_update,
)


class SrcConfigTransactionTest(unittest.TestCase):
    def test_installation_id_uses_stable_file_stat(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir)
            src_exe_path = src_root_path / "src.exe"
            src_exe_path.write_bytes(b"first executable")

            installation_id = read_src_installation_id(src_root_path)
            self.assertEqual(
                read_src_installation_id(src_root_path),
                installation_id,
            )

            other_src_root_path = src_root_path.parent / "other-src"
            other_src_root_path.mkdir()
            (other_src_root_path / "src.exe").write_bytes(src_exe_path.read_bytes())
            self.assertNotEqual(
                installation_id,
                read_src_installation_id(other_src_root_path),
            )

    def test_fresh_template_config_is_available_and_stageable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir)
            src_exe_path = src_root_path / "src.exe"
            src_exe_path.write_bytes(b"src")
            src_set_path = src_root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "template.json").write_text(
                '{"Template": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.template-cn.yaml").write_text(
                "WebuiPort: 23333\n", encoding="utf-8"
            )

            self.assertTrue(is_src_config_available(src_set_path))
            staging_path = stage_src_config_update(
                src_set_path,
                expected_installation_id=read_src_installation_id(src_root_path),
            )

            self.assertTrue((staging_path / "src.json").is_file())
            self.assertTrue((staging_path / "deploy.yaml").is_file())

    def test_invalid_fresh_deploy_template_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_set_path = Path(temp_dir) / "config"
            src_set_path.mkdir()
            (src_set_path / "template.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.template-cn.yaml").write_text(
                "Run: [\n", encoding="utf-8"
            )

            self.assertFalse(is_src_config_available(src_set_path))

    def test_stage_generates_runtime_entries_from_non_template_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir)
            (src_root_path / "src.exe").write_bytes(b"src")
            src_set_path = src_root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "template.json").write_text("{}", encoding="utf-8")
            (src_set_path / "user.json").write_text('{"User": true}', encoding="utf-8")
            (src_set_path / "deploy.template-cn.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            staging_path = stage_src_config_update(
                src_set_path,
                expected_installation_id=read_src_installation_id(src_root_path),
            )

            self.assertEqual(
                (staging_path / "src.json").read_text(encoding="utf-8"),
                '{"User": true}',
            )
            self.assertTrue((staging_path / "deploy.yaml").is_file())

    def test_interrupted_swap_recovery_restores_backup_and_quarantines_staging(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir)
            (src_root_path / "src.exe").write_bytes(b"src")
            src_set_path = src_root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "template.json").write_text(
                '{"Original": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.template-cn.yaml").write_text(
                "WebuiPort: 23333\n", encoding="utf-8"
            )
            backup_path = src_root_path / "config.old"
            src_set_path.rename(backup_path)

            interrupted_staging_path = src_root_path / "config.tmp"
            interrupted_staging_path.mkdir()
            (interrupted_staging_path / "src.json").write_text(
                '{"Interrupted": true}', encoding="utf-8"
            )
            (interrupted_staging_path / "deploy.yaml").write_text(
                "WebuiPort: 1\n", encoding="utf-8"
            )

            recover_interrupted_src_config_swap(
                src_set_path,
                expected_installation_id=read_src_installation_id(src_root_path),
            )

            self.assertTrue(src_set_path.is_dir())
            self.assertFalse(backup_path.exists())
            quarantined_paths = list(
                src_root_path.glob(f"{interrupted_staging_path.name}.untrusted-*")
            )
            self.assertEqual(len(quarantined_paths), 1)
            self.assertEqual(
                (src_set_path / "template.json").read_text(encoding="utf-8"),
                '{"Original": true}',
            )

    def test_stage_recovers_old_only_transaction_before_copying(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir)
            (src_root_path / "src.exe").write_bytes(b"src")
            src_set_path = src_root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "template.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.template-cn.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            backup_path = src_root_path / "config.old"
            src_set_path.rename(backup_path)

            staging_path = stage_src_config_update(
                src_set_path,
                expected_installation_id=read_src_installation_id(src_root_path),
            )

            self.assertTrue(src_set_path.is_dir())
            self.assertTrue(staging_path.is_dir())
            self.assertFalse(backup_path.exists())


if __name__ == "__main__":
    unittest.main()
