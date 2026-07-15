from __future__ import annotations

from automas_script_hsr.adapter_plugin import HSRAdapterPlugin

from .catalog import SRATaskCatalog
from .controller import SRAController


DEFAULT_INSTANCE = {
    "name": "HSR SRA 适配器",
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
    provides = ["hsr.task_catalog.sra.v1", "hsr.controller.sra.v1"]
    task_catalog_factory = SRATaskCatalog
    controller_factory = SRAController
    task_catalog_service = "hsr.task_catalog.sra.v1"
    controller_service = "hsr.controller.sra.v1"
    display_name = "SRA HSR adapter"
