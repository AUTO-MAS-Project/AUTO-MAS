import unittest
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict

from app.plugins import PluginManager
from automas_maafw_controller_win32.service import (
    MaaFWWin32ControllerService,
    MaaFWWin32Window,
)
from automas_maafw_interface.models import MaaFWController
from automas_script_maafw.runner_task import _match_controller_windows


class ForeignController(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    type: str


class MaaFWWin32ControllerDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    type: str


class DefinitionBackedWin32Service:
    def __init__(self) -> None:
        self.received_controller: object | None = None

    def match_controller_windows(self, controller: object) -> list[object]:
        self.received_controller = controller
        MaaFWWin32ControllerDefinition.model_validate(controller)
        return []


class MaaFWControllerContractTest(unittest.TestCase):
    def test_win32_service_accepts_a_foreign_pydantic_controller(self) -> None:
        controller = ForeignController(
            name="Win32-Front",
            type="Win32",
            win32={"window_regex": ".*MaaEnd.*"},
        )
        service = MaaFWWin32ControllerService()

        matches = service.match_controller_windows(
            controller,
            [MaaFWWin32Window(hWnd=1, className="MaaEnd", windowName="MaaEnd")],
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].controllerName, "Win32-Front")

    def test_runner_serializes_controller_before_crossing_service_boundary(self) -> None:
        controller = MaaFWController(
            name="Win32-Front",
            type="Win32",
            win32={"window_regex": ".*MaaEnd.*"},
        )
        service = DefinitionBackedWin32Service()

        with patch.object(PluginManager.service, "get", return_value=service):
            matches = _match_controller_windows(controller)

        self.assertEqual(matches, [])
        self.assertIsInstance(service.received_controller, dict)


if __name__ == "__main__":
    unittest.main()
