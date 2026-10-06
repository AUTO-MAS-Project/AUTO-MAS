"""MuMu 游戏配置：路径矫正、订阅期备份 Session、``_raw`` + Virtual 映射。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import AfterValidator, BeforeValidator, Field, PrivateAttr

from auto_mas_core import (
    ConfigCollection,
    ConfigGroup,
    DeviceStatus,
    EmulatorDeviceEntry,
    EmulatorEntry,
    ExecutablePath,
    UiVisibility,
    collection,
    ui,
    ui_visibility,
)
from auto_mas_core.adapters.game import Virtual, virtual_field

from .constants import _EXE_NAMES, _LAUNCH_DIAG, _MUMU_RELATIVE

if TYPE_CHECKING:
    from .control import MuMuControl


def locate_mumu(value: object) -> str | Path | None:
    """在 ExecutablePath 之前做 MuMu 管理器定位。

    口径对齐非插件版 ``EmulatorPathValidator`` → ``find_emulator_manager_path(..., "mumu")``：
    - 空 → None
    - 文件：自父目录起最多 2 层父级，按相对布局找 MuMuManager.exe
    - 目录：本层 / 最多 3 层父级 / 一层子目录内按 executables 序找
    - 未命中：原样交给 ExecutablePath（非法则纠成 None）
    """
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text:
        return None

    path = Path(text)
    if not path.exists():
        return text

    # ── 旁路 exe → 有限相对布局 ──
    if path.is_file():
        bases = [path.parent]
        cur = path.parent
        for _ in range(2):
            parent = cur.parent
            if parent == cur:
                break
            bases.append(parent)
            cur = parent
        seen: set[str] = set()
        for base in bases:
            for parts in _MUMU_RELATIVE:
                cand = base.joinpath(*parts)
                key = cand.as_posix().casefold()
                if key in seen:
                    continue
                seen.add(key)
                if cand.is_file():
                    return cand
        return text

    # ── 目录：本层 / 父级 / 一层子目录 ──
    def hit_in(directory: Path) -> Path | None:
        for name in _EXE_NAMES:
            cand = directory / name
            if cand.is_file():
                return cand
        return None

    found = hit_in(path)
    if found:
        return found
    cur = path
    for _ in range(3):
        parent = cur.parent
        if parent == cur:
            break
        found = hit_in(parent)
        if found:
            return found
        cur = parent
    try:
        for sub in path.iterdir():
            if sub.is_dir():
                found = hit_in(sub)
                if found:
                    return found
    except OSError:
        pass
    return text


class MuMuDevice(EmulatorDeviceEntry):
    """MuMu 设备：Control 写入官方 info 行到 ``_raw``；Virtual 只读映射。"""

    class Info(EmulatorDeviceEntry.Info):
        # index 落盘身份键；其余从 ``_raw`` 读
        name: Virtual[str] = Field(default=None, description="实例名称")
        status: Virtual[DeviceStatus] = Field(
            default=DeviceStatus.UNKNOWN, description="实例状态"
        )
        adb_address: Virtual[str] = Field(default=None, description="ADB 连接地址")

    class Data(ConfigGroup):
        # 官方 info 同名；UI 隐藏
        pid: Annotated[Virtual[int], ui(visibility=UiVisibility.HIDE)] = Field(
            default=None, description="外壳进程 PID"
        )
        headless_pid: Annotated[Virtual[int], ui(visibility=UiVisibility.HIDE)] = Field(
            default=None, description="虚拟机进程 PID"
        )
        main_wnd: Annotated[Virtual[str], ui(visibility=UiVisibility.HIDE)] = Field(
            default=None, description="主窗口句柄"
        )
        render_wnd: Annotated[Virtual[str], ui(visibility=UiVisibility.HIDE)] = Field(
            default=None, description="渲染窗口句柄"
        )
        player_state: Annotated[Virtual[str], ui(visibility=UiVisibility.HIDE)] = Field(
            default=None, description="外壳启动阶段"
        )
        error_code: Annotated[Virtual[int], ui(visibility=UiVisibility.HIDE)] = Field(
            default=None, description="列表错误码"
        )
        launch_err_code: Annotated[Virtual[int], ui(visibility=UiVisibility.HIDE)] = (
            Field(default=None, description="启动错误码")
        )
        launch_err_msg: Annotated[Virtual[str], ui(visibility=UiVisibility.HIDE)] = (
            Field(default=None, description="启动错误描述")
        )
        # API 无显隐布尔：对 main_wnd 薄读
        window_visible: Annotated[Virtual[bool], ui(visibility=UiVisibility.HIDE)] = (
            Field(default=None, description="主窗是否可见")
        )

    class Session(ConfigGroup):
        """订阅期备份：``setting -aw`` 原样落盘。空 dict 即无活动会话。

        不校验键、不归一值 —— 键集与值类型都由 MuMu 版本决定，故值类型是
        ``Any``：官方吐 JSON，布尔、数字、字符串都可能，这里只做搬运，
        还原时整份写回。落盘是为了抗崩溃：进程没走完退订路径时，下次启动的
        清扫还能凭它还原。
        """

        backup: Annotated[dict[str, Any], ui(visibility=UiVisibility.HIDE)] = Field(
            default_factory=dict, description="订阅前的可写配置原文"
        )

    info: Info = Field(default_factory=Info, description="设备信息")
    data: Data = Field(default_factory=Data, description="运行时数据")
    session: Session = Field(default_factory=Session, description="订阅期配置备份")

    # Control sync 直接赋值；不落盘；不在此做整理
    _raw: dict[str, object] = PrivateAttr(default_factory=dict)

    def diagnosis(self) -> str:
        """启动失败报错后缀（读 ``_raw`` 诊断键）。"""
        parts = [
            f"{label}={self._raw.get(key)}"
            for key, label in _LAUNCH_DIAG
            if self._raw.get(key) not in (None, "", 0, False)
        ]
        return ("；MuMu 诊断: " + ", ".join(parts)) if parts else ""

    @property
    def _control(self) -> MuMuControl:
        from .control import MuMuControl as MC

        ctrl = super()._control
        if not isinstance(ctrl, MC):
            raise TypeError("非 MuMu 管理实例")
        return ctrl

    # ── Virtual：按文档类型直接读 ``_raw`` ──

    @virtual_field("info.name")
    def _vf_name(self) -> str:
        return str(self._raw.get("name") or self.info.index)

    @virtual_field("info.status")
    def _vf_status(self) -> DeviceStatus:
        if not self._raw:
            return DeviceStatus.UNKNOWN
        if self._raw.get("is_android_started"):
            return DeviceStatus.ONLINE
        if self._raw.get("is_process_started"):
            return DeviceStatus.STARTING
        return DeviceStatus.OFFLINE

    @virtual_field("info.adb_address")
    def _vf_adb(self) -> str:
        host = self._raw.get("adb_host_ip")
        port = self._raw.get("adb_port")
        if host is not None and port is not None:
            return f"{host}:{port}"
        try:
            return f"127.0.0.1:{5555 + int(self.info.index) * 2}"
        except (TypeError, ValueError):
            return ""

    @virtual_field("data.pid")
    def _vf_pid(self) -> int | None:
        v = self._raw.get("pid")
        return v if isinstance(v, int) else None

    @virtual_field("data.headless_pid")
    def _vf_headless_pid(self) -> int | None:
        v = self._raw.get("headless_pid")
        return v if isinstance(v, int) else None

    @virtual_field("data.main_wnd")
    def _vf_main_wnd(self) -> str | None:
        v = self._raw.get("main_wnd")
        return v if isinstance(v, str) and v else None

    @virtual_field("data.render_wnd")
    def _vf_render_wnd(self) -> str | None:
        v = self._raw.get("render_wnd")
        return v if isinstance(v, str) and v else None

    @virtual_field("data.player_state")
    def _vf_player_state(self) -> str | None:
        v = self._raw.get("player_state")
        return v if isinstance(v, str) and v else None

    @virtual_field("data.error_code")
    def _vf_error_code(self) -> int | None:
        v = self._raw.get("error_code")
        return v if isinstance(v, int) else None

    @virtual_field("data.launch_err_code")
    def _vf_launch_err_code(self) -> int | None:
        v = self._raw.get("launch_err_code")
        return v if isinstance(v, int) else None

    @virtual_field("data.launch_err_msg")
    def _vf_launch_err_msg(self) -> str | None:
        v = self._raw.get("launch_err_msg")
        return v if isinstance(v, str) else None

    @virtual_field("data.window_visible")
    def _vf_window_visible(self) -> bool | None:
        """仅 ``main_wnd`` → IsWindowVisible；禁止按 pid 搜窗。"""
        wnd = self._raw.get("main_wnd")
        if not isinstance(wnd, str) or not wnd or sys.platform != "win32":
            return None
        try:
            hwnd = int(wnd, 16)
        except ValueError:
            return None
        import win32gui

        try:
            if not win32gui.IsWindow(hwnd):
                return None
            return bool(win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd))
        except Exception:
            return None

    # ── UI 显隐 ──

    @ui_visibility("action.open")
    def _vis_open(self) -> UiVisibility:
        if self.info.status in {DeviceStatus.ONLINE, DeviceStatus.STARTING}:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.close")
    def _vis_close(self) -> UiVisibility:
        if self.info.status not in {
            DeviceStatus.ONLINE,
            DeviceStatus.STARTING,
            DeviceStatus.ERROR,
        }:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.show")
    def _vis_show(self) -> UiVisibility:
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        vis = self.data.window_visible
        if vis is True:
            return UiVisibility.HIDE
        if vis is None:
            return UiVisibility.DISABLE
        return self._busy_vis()

    @ui_visibility("action.hide")
    def _vis_hide(self) -> UiVisibility:
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        vis = self.data.window_visible
        if vis is False:
            return UiVisibility.HIDE
        if vis is None:
            return UiVisibility.DISABLE
        return self._busy_vis()

    @ui_visibility("action.minimize")
    def _vis_minimize(self) -> UiVisibility:
        return self._vis_hide()

    @ui_visibility("action.maximize")
    def _vis_maximize(self) -> UiVisibility:
        return self._vis_show()

    @ui_visibility("action.open_store")
    def _vis_open_store(self) -> UiVisibility:
        if self.info.status != DeviceStatus.ONLINE:
            return UiVisibility.HIDE
        return self._busy_vis()

    @ui_visibility("action.delete_instance")
    def _vis_delete_instance(self) -> UiVisibility:
        if self.info.status == DeviceStatus.STARTING:
            return UiVisibility.HIDE
        return self._busy_vis()


class MuMuGame(EmulatorEntry):
    """MuMu 模拟器配置。"""

    class Info(EmulatorEntry.Info):
        path: Annotated[
            ExecutablePath,
            BeforeValidator(locate_mumu),
            AfterValidator(
                lambda p: (
                    p
                    if p is not None and p.name.casefold() == "mumumanager.exe"
                    else None
                )
            ),
        ] = Field(default=None, description="MuMuManager.exe 路径")
        force_kill: bool = Field(
            default=False, description="关闭时强制结束 MuMu 相关进程"
        )
        # 稳定模式与配置守卫已固化为默认启用，不再是开关：
        # 任务订阅实例时备份原状 + 写入安全值，退订时整份还原（见 control.py）

    info: Info = Field(default_factory=Info, description="游戏信息")
    devices: ConfigCollection[MuMuDevice] = collection(MuMuDevice)

    @property
    def _control(self) -> MuMuControl:
        from .control import MuMuControl as MC

        ctrl = super()._control
        if not isinstance(ctrl, MC):
            raise TypeError("非 MuMu 管理实例")
        return ctrl
