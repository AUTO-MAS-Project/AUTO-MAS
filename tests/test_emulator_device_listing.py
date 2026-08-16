import json
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

from app.api.info import get_emulator_devices_combox, router
from app.core.config import AppConfig
from app.models.emulator import DeviceStatus
from app.models.schema import ComboBoxOut, EmulatorDeleteIn
from app.utils.emulator.general import GeneralDeviceManager
from app.utils.emulator.ldplayer import LDManager
from app.utils.emulator.mumu import MumuManager


class EmulatorDeviceListingTest(unittest.IsolatedAsyncioTestCase):
    async def test_mumu_list_devices_only_queries_all_instance_info(self) -> None:
        manager = MumuManager.__new__(MumuManager)
        manager.get_device_info = AsyncMock(
            return_value=json.dumps(
                {
                    "0": {
                        "index": 0,
                        "name": "MuMu 0",
                        "is_android_started": True,
                        "is_process_started": True,
                    },
                    "8": {
                        "index": 8,
                        "name": "MuMu 8",
                        "is_android_started": False,
                        "is_process_started": False,
                    },
                }
            )
        )
        manager.get_adb_info = AsyncMock()

        result = await manager.list_devices()

        self.assertEqual(result, {"0": "MuMu 0", "8": "MuMu 8"})
        manager.get_device_info.assert_awaited_once_with("all")
        manager.get_adb_info.assert_not_awaited()

    async def test_ldplayer_list_devices_only_runs_list2(self) -> None:
        manager = LDManager.__new__(LDManager)
        manager.emulator_path = Path("dnconsole.exe")
        manager.config = SimpleNamespace(get=lambda _section, _key: 30)
        run_process = AsyncMock(
            return_value=SimpleNamespace(
                returncode=0,
                stdout=(
                    "0,LDPlayer 0,0,0,0,0,0,1280,720,240\n"
                    "2,LDPlayer 2,0,0,1,100,200,1280,720,240\n"
                ),
            )
        )

        with patch(
            "app.utils.emulator.ldplayer.ProcessRunner.run_process", run_process
        ):
            result = await manager.list_devices()

        self.assertEqual(result, {"0": "LDPlayer 0", "2": "LDPlayer 2"})
        run_process.assert_awaited_once()
        self.assertEqual(run_process.await_args.args[1], "list2")

    async def test_general_list_devices_is_empty(self) -> None:
        manager = GeneralDeviceManager.__new__(GeneralDeviceManager)

        self.assertEqual(await manager.list_devices(), {})

    async def test_mumu_get_info_reuses_all_instance_status_and_queries_adb(
        self,
    ) -> None:
        manager = MumuManager.__new__(MumuManager)
        manager.get_device_info = AsyncMock(
            return_value=json.dumps(
                {
                    "0": {
                        "index": 0,
                        "name": "MuMu 0",
                        "is_android_started": True,
                        "is_process_started": True,
                    },
                    "1": {
                        "index": 1,
                        "name": "MuMu 1",
                        "is_android_started": False,
                        "is_process_started": True,
                    },
                }
            )
        )
        manager.get_adb_info = AsyncMock(
            side_effect=[
                json.dumps({"adb_host_ip": "127.0.0.1", "adb_port": 16384}),
                json.dumps({"adb_host_ip": "127.0.0.1", "adb_port": 16416}),
            ]
        )

        result = await manager.getInfo(None)

        manager.get_device_info.assert_awaited_once_with("all")
        self.assertEqual(
            manager.get_adb_info.await_args_list,
            [call("0"), call("1")],
        )
        self.assertEqual(result["0"].status, DeviceStatus.ONLINE)
        self.assertEqual(result["0"].adb_address, "127.0.0.1:16384")
        self.assertEqual(result["1"].status, DeviceStatus.STARTING)
        self.assertEqual(result["1"].adb_address, "127.0.0.1:16416")

    async def test_config_combobox_uses_lightweight_device_listing(self) -> None:
        emulator_id = uuid.uuid4()
        emulator_config = SimpleNamespace(
            get=lambda section, key: "mumu" if (section, key) == ("Info", "Type") else None
        )
        owner = SimpleNamespace(EmulatorConfig={emulator_id: emulator_config})
        manager = SimpleNamespace(
            list_devices=AsyncMock(return_value={"0": "MuMu 0"})
        )

        with patch(
            "app.core.emulator_manager.EmulatorManager.get_emulator_instance",
            AsyncMock(return_value=manager),
        ):
            result = await AppConfig.get_emulator_devices_combox(
                owner, str(emulator_id)
            )

        self.assertEqual(
            result,
            [
                {"label": "未选择", "value": "-"},
                {"label": "MuMu 0", "value": "0"},
            ],
        )
        manager.list_devices.assert_awaited_once_with()

    async def test_config_combobox_preserves_empty_special_cases(self) -> None:
        emulator_id = uuid.uuid4()
        general_config = SimpleNamespace(
            get=lambda section, key: (
                "general" if (section, key) == ("Info", "Type") else None
            )
        )
        owner = SimpleNamespace(EmulatorConfig={emulator_id: general_config})

        self.assertEqual(
            await AppConfig.get_emulator_devices_combox(owner, "-"), []
        )
        self.assertEqual(
            await AppConfig.get_emulator_devices_combox(owner, str(emulator_id)), []
        )


class EmulatorDeviceComboboxApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_contract_is_unchanged(self) -> None:
        route = next(
            route
            for route in router.routes
            if route.path == "/api/info/combox/emulator/devices"
        )
        self.assertEqual(route.methods, {"POST"})
        self.assertIs(route.response_model, ComboBoxOut)

        raw_data = [
            {"label": "未选择", "value": "-"},
            {"label": "MuMu 0", "value": "0"},
        ]
        with patch.object(
            AppConfig,
            "get_emulator_devices_combox",
            AsyncMock(return_value=raw_data),
        ):
            result = await get_emulator_devices_combox(
                EmulatorDeleteIn(emulatorId=str(uuid.uuid4()))
            )

        self.assertIsInstance(result, ComboBoxOut)
        self.assertEqual(result.code, 200)
        self.assertEqual(
            [item.model_dump() for item in result.data],
            raw_data,
        )

    async def test_endpoint_error_response_is_unchanged(self) -> None:
        with patch.object(
            AppConfig,
            "get_emulator_devices_combox",
            AsyncMock(side_effect=RuntimeError("scan failed")),
        ):
            result = await get_emulator_devices_combox(
                EmulatorDeleteIn(emulatorId=str(uuid.uuid4()))
            )

        self.assertEqual(result.code, 500)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.message, "RuntimeError: scan failed")
        self.assertEqual(result.data, [])


if __name__ == "__main__":
    unittest.main()
