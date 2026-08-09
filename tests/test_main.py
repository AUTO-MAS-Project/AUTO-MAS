import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class MainDevelopmentEnvironmentTest(unittest.TestCase):
    def test_explicit_development_environment(self) -> None:
        with patch.dict(os.environ, {"AUTO_MAS_DEV": "true"}):
            self.assertTrue(main.is_development_environment())

    def test_repository_venv_is_development_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = Path(temp_dir)
            (repository / ".git").mkdir()
            (repository / ".venv").mkdir()

            with patch.dict(os.environ, {"AUTO_MAS_DEV": ""}), patch.object(
                main, "current_dir", repository
            ), patch.object(sys, "prefix", str(repository / ".venv")):
                self.assertTrue(main.is_development_environment())

    def test_non_repository_environment_requires_elevation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            application_dir = Path(temp_dir)

            with patch.dict(os.environ, {"AUTO_MAS_DEV": ""}), patch.object(
                main, "current_dir", application_dir
            ), patch.object(sys, "prefix", str(application_dir / "python")):
                self.assertFalse(main.is_development_environment())


if __name__ == "__main__":
    unittest.main()
