"""MuMu 适配器常量：路径定位、进程识别、设置键与稳定模式数据的单一来源。"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ── 可执行定位（config.locate_mumu）──
# 对齐非插件版 MUMU_RELATIVE_EXECUTABLE_PATTERNS（自基准目录向上最多 2 层）
_MUMU_RELATIVE = (
    ("MuMuManager.exe",),
    ("nx_main", "MuMuManager.exe"),
    ("shell", "MuMuManager.exe"),
)
# 与 EMULATOR_PATH_BOOK['mumu'].executables 一致，目录扫描时按序试
_EXE_NAMES = ("MuMuManager.exe", "MuMuPlayer.exe")

# ── 注册表搜索（search）──
_EMULATOR_TYPE = "mumu"
# 对齐非插件版 _extract_path_from_command
_CMDLINE_PATH = re.compile(
    r"([A-Za-z]:[/\\](?:[^/\\:*?\"<>|\r\n]+[/\\])*[^/\\:*?\"<>|\r\n]+"
    r"\.(?:exe|cmd|bat|lnk|msi))(?:,\d+)?",
    re.IGNORECASE,
)

# ── 包 / 进程 / 启动诊断 / 前台 ──
STORE_PACKAGE = "com.mumu.store"
_STORE_OVERLAY_OP = "SYSTEM_ALERT_WINDOW"
FORCE_KILL_KEYWORDS = ("mumunxdevice", "mumunxmain", "mumuvmmheadless")
_LAUNCH_DIAG = (
    ("launch_err_code", "启动错误码"),
    ("launch_err_msg", "启动错误"),
    ("error_code", "实例错误码"),
    ("player_state", "实例状态"),
)
# ── 去广告：Windows 侧图片缓存目录（占位用）──
# 目录换成同名空文件，MuMu 就写不进缓存图。12.0 与 6 两套安装路径各占一份 ——
# 装哪个版本不确定，不在的那条 mkdir 建出来即可（见 ``set_block_ad``）。
# 两类缓存都占：
#   startupImage —— 实例开屏图，口径同非插件版
#     EMULATOR_SPLASH_ADS_PATH_BOOK['mumu']。emulator2/master_mode:308 实测它
#     会被实例启动时删掉重建，故单靠它不够，但留着无害（那边也只是不再指望它）。
#   ProgramAds —— 小程序弹窗图，常驻的 MuMuNxService.exe 在实例启动等事件时
#     直接拿它画；实测遇到文件不会改回目录，只记「no cache ads」，
#     故这条才是真正拦住弹窗的那份。
_SPLASH_ADS_PATHS = (
    Path(os.getenv("APPDATA") or "") / "Netease/MuMuPlayer-12.0/data/startupImage",
    Path(os.getenv("APPDATA") or "") / "Netease/MuMuPlayer/data/startupImage",
    Path(os.getenv("APPDATA") or "") / "Netease/MuMuPlayer-12.0/data/ProgramAds",
    Path(os.getenv("APPDATA") or "") / "Netease/MuMuPlayer/data/ProgramAds",
)

_FOREGROUND_MARKERS = (
    "topResumedActivity=",
    "ResumedActivity:",
    "mResumedActivity:",
    "mCurrentFocus=",
)

# ── 门控刷新窗口与节拍 ──
# 操作函数不自己 sync，只等 devices 上出现期待值；间隔即它们的时延下限，
# 故忙时提速。闲时 1Hz 只是为了让 UI 上的状态不至于太陈旧。
_WINDOW_SEC = 600.0
_SYNC_INTERVAL = 1.0
_BUSY_INTERVAL = 0.2

# ── 订阅期写入：``EmulatorExpect`` 字段 → 官方可写 key ──
# 分辨率与稳定项同一张表、同一套逻辑：怎么写由值的形态定（见 control 里的循环）。
# 标量三态 —— ``None`` 不做要求该键不出现，给了值就按值覆写；
# 元组是容许值表 —— 当前档在表内就不动，越界才写表首。
# 只这几项。cpu/内存/帧率不碰 —— 那是用户的机器预算，任务没有立场替他定。
# 稳定项行尾标依据（MAA 文档点名 / MAA issue 模板收集 / 机械推断），
# 口径同 emulator2/stability.MUMU_ITEMS。
_WRITE_KEYS = {
    # 分辨率：写 ``.custom`` 是死的，必须同时把 _RESOLUTION_MODE_KEY 打到 custom
    "width": "resolution_width.custom",
    "height": "resolution_height.custom",
    "dpi": "resolution_dpi.custom",
    "keep_alive": "app_keptlive",  # maa_tracked
    "high_frame_rate": "dynamic_adjust_frame_rate",  # maa_tracked
    "vertical_sync": "vertical_sync",  # mechanical
    "display_fps": "show_frame_rate",  # mechanical
    "auto_rotate": "window_auto_rotate",  # mechanical
    "vram_strategy": "renderer_strategy",  # maa_documented，容许值表
}
_RESOLUTION_MODE_KEY = "resolution_mode"
