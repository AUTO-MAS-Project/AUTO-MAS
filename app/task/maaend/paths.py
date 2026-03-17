from pathlib import Path


MANAGED_CONFIG_NAME = "AUTO-MAS.json"
LOCAL_CONFIG_NAME = "mxu-MaaEnd.json"


def managed_user_config_path(script_id: str, user_id: str) -> Path:
    return (
        Path.cwd() / f"data/{script_id}/{user_id}/ConfigFile/{MANAGED_CONFIG_NAME}"
    )


def managed_default_config_path(script_id: str) -> Path:
    return Path.cwd() / f"data/{script_id}/Default/ConfigFile/{MANAGED_CONFIG_NAME}"
