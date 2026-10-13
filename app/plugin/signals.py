"""插件系统唯一 blinker Namespace。"""

from __future__ import annotations

from blinker import Namespace

plugin_signals = Namespace()

service_changed = plugin_signals.signal("service_changed")
sources_changed = plugin_signals.signal("sources_changed")
capabilities_changed = plugin_signals.signal("capabilities_changed")
install_progress = plugin_signals.signal("install_progress")
upgrade_progress = plugin_signals.signal("upgrade_progress")
precheck_failed = plugin_signals.signal("precheck_failed")
