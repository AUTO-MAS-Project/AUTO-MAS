from __future__ import annotations

from automas_script_hsr.adapter_plugin import HSRAdapterPlugin

from .catalog import M7ATaskCatalog
from .controller import M7AController


DEFAULT_INSTANCE = {
    "name": "HSR M7A 适配器",
    "enabled": True,
    "config": {},
}

schema = {
    "__no_plugin_config__": {
        "type": "boolean",
        "default": True,
        "hidden": True,
        "configurable": False,
        "title": "No plugin-level configuration",
    },
}


class Plugin(HSRAdapterPlugin):
    provides = ["hsr.task_catalog.m7a.v1", "hsr.controller.m7a.v1"]
    task_catalog_factory = M7ATaskCatalog
    controller_factory = M7AController
    task_catalog_service = "hsr.task_catalog.m7a.v1"
    controller_service = "hsr.controller.m7a.v1"
    display_name = "M7A HSR adapter"
