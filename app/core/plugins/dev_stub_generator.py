#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

"""兼容层：保留旧导入路径，实际实现已迁移至 scripts.dev_stub_generator。"""

from scripts.dev_stub_generator import ( 
    generate_plugin_context_stubs,
    is_dev_stub_generation_enabled,
)

__all__ = ["generate_plugin_context_stubs", "is_dev_stub_generation_enabled"]
