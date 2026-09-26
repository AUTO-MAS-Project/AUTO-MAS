import ast
from copy import deepcopy
from pathlib import Path


def _load_helpers():
    source_path = Path(__file__).parents[2] / "app/task/MAA/AutoProxy.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names = {"_configure_mumu_screenshot_enhancement", "_without_temporary_mumu_extras"}
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"_MUMU_EXTRAS_KEY": "MuMuEmulator12"}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["_configure_mumu_screenshot_enhancement"], namespace["_without_temporary_mumu_extras"]


def test_mumu_screenshot_overlay_preserves_native_options_and_is_not_written_back():
    configure, cleanup = _load_helpers()
    native = {
        "Configurations": {
            "Default": {
                "Gui": {
                    "ConnectSettings": {
                        "Extras": {
                            "MuMuEmulator12": {"EnableTouch": True},
                            "Other": {"IsEnabled": True},
                        }
                    }
                }
            }
        }
    }
    runtime = deepcopy(native)
    device = {"EmulatorPath": "C:/MuMu", "InstanceIndex": 2}

    configure(runtime, device)
    mumu = runtime["Configurations"]["Default"]["Gui"]["ConnectSettings"]["Extras"]["MuMuEmulator12"]
    assert mumu == {"EnableTouch": True, "IsEnabled": True, **device}
    cleaned = cleanup(deepcopy(runtime), device)
    assert cleaned["Configurations"]["Default"]["Gui"]["ConnectSettings"]["Extras"]["MuMuEmulator12"] == {
        "EnableTouch": True,
        "IsEnabled": True,
    }
    assert cleaned["Configurations"]["Default"]["Gui"]["ConnectSettings"]["Extras"]["Other"] == {"IsEnabled": True}


def test_screenshot_overlay_cleanup_leaves_other_extras():
    _, cleanup = _load_helpers()
    runtime = {
        "Configurations": {
            "Default": {
                "Gui": {
                    "ConnectSettings": {
                        "Extras": {"MuMuEmulator12": {"IsEnabled": True, "EmulatorPath": "x", "InstanceIndex": 0}, "Other": {}}
                    }
                }
            }
        }
    }
    cleaned = cleanup(runtime, {"EmulatorPath": "x", "InstanceIndex": 0})
    assert cleaned["Configurations"]["Default"]["Gui"]["ConnectSettings"]["Extras"] == {
        "MuMuEmulator12": {"IsEnabled": True},
        "Other": {},
    }
