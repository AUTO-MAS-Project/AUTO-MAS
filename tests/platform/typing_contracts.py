"""仅供 mypy 检查，不能运行：逐个后端核对统一契约，不装配平台依赖。"""

from typing import assert_type

import app.core.notify.native as native
import app.core.notify.native.common as common_notification
import app.core.notify.native.windows as windows_notification
from app import services, tools, utils
from app.core import Notify
from app.core.notify.manager import NotificationManager as NotificationManager
from app.core.notify.native.contracts import NotificationAPI, NotificationSender
from app.services.common.custom_script import native as common_script
from app.services.contracts.custom_script import ScriptCommandAPI
from app.services.contracts.power import PowerController
from app.services.contracts.startup import StartupManager
from app.services.unsupported.power import CommonPowerController
from app.services.unsupported.startup import CommonStartupManager
from app.services.windows import custom_script_native as windows_script
from app.services.windows.power import WindowsPowerController
from app.services.windows.startup import WindowsStartupManager
from app.task.BAAH.tools.push_log import baah_resolve
from app.task.MaaEnd.inventory_report import inventory_resolve
from app.task.MaaEnd.push_log import maaend_resolve
from app.task.OkNte.push_log import oknte_resolve
from app.task.Okww.push_log import okww_resolve
from app.task.ZzzOd.push_log import make_zzzod_resolve
from app.utils.common import emulator_native as common_emulator
from app.utils.common import host as common_host
from app.utils.common import update_native as common_update
from app.utils.common.log_box.pipeline import PostProcessor
from app.utils.common.log_box.results import LogEntry
from app.utils.common.process import platform as common_process
from app.utils.contracts.audio import AudioAPI
from app.utils.contracts.display import DisplayAPI, MonitorInfo
from app.utils.contracts.emulator_native import EmulatorNativeAPI
from app.utils.contracts.file_lock import FileLockAPI
from app.utils.contracts.host import HostAPI
from app.utils.contracts.process import ProcessAPI, ProcessPlatform
from app.utils.contracts.registry import RegistryAPI
from app.utils.contracts.secret import SecretAPI
from app.utils.contracts.update_native import UpdateNativeAPI
from app.utils.contracts.vdd import VddAPI
from app.utils.contracts.window import WindowAPI
from app.utils.posix import file_lock as posix_file_lock
from app.utils.unsupported import audio as unsupported_audio
from app.utils.unsupported import display as unsupported_display
from app.utils.unsupported import file_lock as unsupported_file_lock
from app.utils.unsupported import registry as unsupported_registry
from app.utils.unsupported import secret as unsupported_secret
from app.utils.unsupported import vdd as unsupported_vdd
from app.utils.unsupported import window as unsupported_window
from app.utils.windows import audio as windows_audio
from app.utils.windows import display as windows_display
from app.utils.windows import emulator_native as windows_emulator
from app.utils.windows import file_lock as windows_file_lock
from app.utils.windows import host as windows_host
from app.utils.windows import process as windows_process
from app.utils.windows import registry as windows_registry
from app.utils.windows import secret as windows_secret
from app.utils.windows import update_native as windows_update
from app.utils.windows import vdd as windows_vdd
from app.utils.windows import window as windows_window

# 必须是实际实现的赋值；不要用 cast、Any 或 ignore 绕过签名核对。
okww_processor: PostProcessor = okww_resolve
oknte_processor: PostProcessor = oknte_resolve
baah_processor: PostProcessor = baah_resolve
maaend_processor: PostProcessor = maaend_resolve
inventory_processor: PostProcessor = inventory_resolve
zzzod_processor: PostProcessor = make_zzzod_resolve(set(), {})
file_lock_windows: FileLockAPI = windows_file_lock
file_lock_posix: FileLockAPI = posix_file_lock
file_lock_unsupported: FileLockAPI = unsupported_file_lock
audio_windows: AudioAPI = windows_audio
audio_unsupported: AudioAPI = unsupported_audio
display_windows: DisplayAPI = windows_display
display_unsupported: DisplayAPI = unsupported_display
emulator_windows: EmulatorNativeAPI = windows_emulator
emulator_common: EmulatorNativeAPI = common_emulator
host_windows: HostAPI = windows_host
host_common: HostAPI = common_host
notification_windows: NotificationAPI = windows_notification
notification_common: NotificationAPI = common_notification
process_windows: ProcessAPI = windows_process
process_common: ProcessAPI = common_process
registry_windows: RegistryAPI = windows_registry
registry_unsupported: RegistryAPI = unsupported_registry
secret_windows: SecretAPI = windows_secret
secret_unsupported: SecretAPI = unsupported_secret
update_windows: UpdateNativeAPI = windows_update
update_common: UpdateNativeAPI = common_update
vdd_windows: VddAPI = windows_vdd
vdd_unsupported: VddAPI = unsupported_vdd
window_windows: WindowAPI = windows_window
window_unsupported: WindowAPI = unsupported_window
power_windows: PowerController = WindowsPowerController()
power_unsupported: PowerController = CommonPowerController()
startup_windows: StartupManager = WindowsStartupManager()
startup_unsupported: StartupManager = CommonStartupManager()
script_common: ScriptCommandAPI = common_script
script_windows: ScriptCommandAPI = windows_script

# 消费者从根入口看到契约，不随运行 mypy 的宿主系统改变。
assert_type(utils.window, WindowAPI)
assert_type(utils.file_lock, FileLockAPI)
assert_type(utils.audio, AudioAPI)
assert_type(utils.host, HostAPI)
notification_entry: NotificationAPI = native
assert_type(utils.registry, RegistryAPI)
assert_type(utils.secret, SecretAPI)
assert_type(utils.emulator_native, EmulatorNativeAPI)
assert_type(utils.update_native, UpdateNativeAPI)
assert_type(utils.vdd, VddAPI)
assert_type(utils.window.get_window_handles(123), list[int])
assert_type(utils.display.list_monitors(), list[MonitorInfo])
assert_type(utils.secret.looks_like_dpapi_blob("value"), bool)
assert_type(utils.process_platform.platform_process, ProcessPlatform)
assert_type(services.power, PowerController)
assert_type(services.startup, StartupManager)
assert_type(services.custom_script_native, ScriptCommandAPI)
assert_type(tools.community.has_community_credentials({}), bool)
assert_type(utils.log_box.LogPipeline().finish(), list[LogEntry])
assert_type(utils.log.sources.LogSource("run.log").read_new(), list[str])

assert_type(native.prepare_sender(), NotificationSender)
assert_type(Notify, NotificationManager)
