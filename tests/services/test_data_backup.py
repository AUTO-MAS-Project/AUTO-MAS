import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.services.data_backup import create_data_backup


class DataBackupTest(unittest.TestCase):
    def test_backup_contains_directories_and_consistent_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for directory in ("data", "config", "history"):
                (root / directory).mkdir()
            (root / "config" / "Config.json").write_text("{}", encoding="utf-8")
            (root / "history" / "latest.log").write_text("done", encoding="utf-8")

            database = sqlite3.connect(root / "data" / "data.db")
            try:
                database.execute("PRAGMA journal_mode=WAL")
                database.execute("PRAGMA wal_autocheckpoint=0")
                database.execute("CREATE TABLE records(value TEXT)")
                database.execute("INSERT INTO records VALUES ('saved')")
                database.commit()

                backup_path = create_data_backup(root)
                try:
                    with zipfile.ZipFile(backup_path) as archive:
                        names = set(archive.namelist())
                        self.assertTrue(
                            {
                                "data/",
                                "config/",
                                "history/",
                                "data/data.db",
                                "config/Config.json",
                                "history/latest.log",
                            }.issubset(names)
                        )
                        self.assertNotIn("data/data.db-wal", names)
                        archive.extract("data/data.db", root / "extracted")

                    snapshot = sqlite3.connect(root / "extracted" / "data" / "data.db")
                    try:
                        value = snapshot.execute("SELECT value FROM records").fetchone()
                    finally:
                        snapshot.close()
                    self.assertEqual(value, ("saved",))
                finally:
                    backup_path.unlink(missing_ok=True)
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
