import unittest
from datetime import datetime

import app.core  # noqa: F401

from app.task.MaaFW import manager as manager_module
from app.task.MaaFW.manager import MaaFWManager
from app.task.MaaFW.tools.external.profile import (
    MFAAVALONIA_LOG_PROFILE,
    MXU_LOG_PROFILE,
    SHELL_LOG_PROFILES,
    ShellLogProfile,
    get_shell_log_profile,
    pick_latest_mxu_log,
    resolve_log_relpath,
)
from app.task.MaaFW.tools.external.shell import ShellFamily

# 逐字取自 D:\MAS\reference\MaaYYs-win-x86_64-v3.10.2\debug\2026-07-04-2.log
# 的静态样本（2026-08-28 审计），作为 MXU 画像的证据 fixture。
_MXU_START_LINE = "2026-07-04 10:25:44 INFO  [Task] 实例 配置 3: 开始执行任务, 数量: 1"
_MXU_SUBMIT_LINE = (
    "2026-07-04 10:25:45 INFO  [Task] 实例 配置 3: 任务已提交, task_ids: [200000001]"
)
_MXU_DRAINED_LINE = (
    "2026-07-04 10:25:46 DEBUG [App] 收到 state-changed，已刷新运行时状态, "
    "kind: tasks-completed"
)
_MXU_STOP_LINE = "2026-07-04 10:26:05 INFO  [Task] [task-stop#nopmvdi] 停止任务"


class MfaAvaloniaProfileDriftGuardTest(unittest.TestCase):
    """MFAAvalonia 画像必须与 manager.py 的生产常量逐项一致。

    画像是数据表、manager 是运行实现；任何一侧单独改动都会让 2.3 的
    per-shell 表失真，故此处逐项断言绑定。
    """

    def test_markers_match_manager_constants(self) -> None:
        self.assertEqual(
            MFAAVALONIA_LOG_PROFILE.completion_markers,
            manager_module._COMPLETION_MARKERS,
        )
        self.assertEqual(
            MFAAVALONIA_LOG_PROFILE.abandon_markers,
            (manager_module._ABANDON_MARKER,),
        )
        self.assertEqual(
            MFAAVALONIA_LOG_PROFILE.controller_failure_markers,
            manager_module._CONTROLLER_FAILURE_MARKERS,
        )
        self.assertEqual(
            MFAAVALONIA_LOG_PROFILE.failure_markers,
            manager_module._FAILURE_MARKERS,
        )

    def test_time_format_matches_manager(self) -> None:
        self.assertEqual(
            MFAAVALONIA_LOG_PROFILE.time_format, manager_module._LOG_TIME_FORMAT
        )
        # manager.py 构造 LogMonitor((1, 24), ...)：时间戳位于行内 [1:24) 切片。
        self.assertEqual(MFAAVALONIA_LOG_PROFILE.time_stamp_range, (1, 24))

    def test_log_relpath_matches_manager_layout(self) -> None:
        # manager.py: project_root / "logs" / f"log-{now:%Y%m%d}.log"
        self.assertEqual(
            resolve_log_relpath(
                MFAAVALONIA_LOG_PROFILE, datetime(2026, 8, 28, 12, 0, 0)
            ),
            "logs/log-20260828.log",
        )

    def test_timestamp_slice_parses_mfa_format_line(self) -> None:
        line = "[2026-08-27 19:08:22.666] [ERR] 初始化控制器失败"
        start, end = MFAAVALONIA_LOG_PROFILE.time_stamp_range
        parsed = datetime.strptime(
            line[start:end], MFAAVALONIA_LOG_PROFILE.time_format
        )
        self.assertEqual(parsed, datetime(2026, 8, 27, 19, 8, 22, 666000))

    def test_profile_is_run_validated(self) -> None:
        self.assertTrue(MFAAVALONIA_LOG_PROFILE.run_validated)


class MxuProfileEvidenceTest(unittest.TestCase):
    """MXU 画像必须与静态样本逐行吻合，且明确标注未经真机验证。"""

    def test_fallback_slice_parses_the_backend_log(self) -> None:
        """兜底那份是 Rust 后端日志（debug/mxu-tauri.log），行首带方括号。"""

        line = (
            "[2026-08-29][18:15:43][INFO][mxu_lib::web_server] "
            "Web server listening on http://127.0.0.1:12701"
        )
        start, end = MXU_LOG_PROFILE.fallback_time_stamp_range
        self.assertEqual(
            datetime.strptime(line[start:end], MXU_LOG_PROFILE.fallback_time_format),
            datetime(2026, 8, 29, 18, 15, 43),
        )

    def test_primary_slice_parses_the_frontend_sample_lines(self) -> None:
        """判据串只出现在前端日志里，首选切片必须对得上它。

        MXU 同时写两份：前端 debug/<日期>-<序号>.log 带 [App]/[Task]/[MAA] 标签，
        判据串全在这里；Rust 后端 debug/mxu-tauri.log 只有启动那类行。首选必须
        是前端那份，盯着后端那份会永远等不到任务标记。
        """

        start, end = MXU_LOG_PROFILE.time_stamp_range
        for line, expected in (
            (_MXU_START_LINE, datetime(2026, 7, 4, 10, 25, 44)),
            (_MXU_DRAINED_LINE, datetime(2026, 7, 4, 10, 25, 46)),
            (_MXU_STOP_LINE, datetime(2026, 7, 4, 10, 26, 5)),
        ):
            with self.subTest(line=line[:30]):
                parsed = datetime.strptime(
                    line[start:end], MXU_LOG_PROFILE.time_format
                )
                self.assertEqual(parsed, expected)

    def test_markers_hit_only_their_sample_lines(self) -> None:
        lines = (
            _MXU_START_LINE,
            _MXU_SUBMIT_LINE,
            _MXU_DRAINED_LINE,
            _MXU_STOP_LINE,
        )

        def hits(markers):
            return [
                line
                for line in lines
                if any(marker in line for marker in markers)
            ]

        self.assertEqual(hits(MXU_LOG_PROFILE.completion_markers), [_MXU_DRAINED_LINE])
        self.assertEqual(hits(MXU_LOG_PROFILE.task_start_markers), [_MXU_START_LINE])
        self.assertEqual(hits(MXU_LOG_PROFILE.stop_markers), [_MXU_STOP_LINE])

    def test_unvalidated_and_fail_closed(self) -> None:
        # 真机验证前不得被运行链路采信；失败判别串样本中未出现，不猜测。
        self.assertFalse(MXU_LOG_PROFILE.run_validated)
        self.assertEqual(MXU_LOG_PROFILE.controller_failure_markers, ())
        self.assertEqual(MXU_LOG_PROFILE.abandon_markers, ())

    def test_both_log_shapes_are_declared(self) -> None:
        """两份日志都要在画像里有据可查，且各自带上自己的时间切片。

        前端那份的当日启动序号在启动前不可知，只能靠 log_glob_dir 在起进程
        之后 glob；后端那份是固定名，不含 strftime 占位符，resolve 出来与
        写死的一致。
        """

        self.assertEqual(MXU_LOG_PROFILE.log_glob_dir, "debug")
        self.assertEqual(
            resolve_log_relpath(MXU_LOG_PROFILE, datetime(2026, 8, 28)),
            "debug/mxu-tauri.log",
        )
        self.assertIsNotNone(MXU_LOG_PROFILE.fallback_time_stamp_range)
        # 两套切片必须不同，相同就说明有一边写错了。
        self.assertNotEqual(
            MXU_LOG_PROFILE.time_stamp_range,
            MXU_LOG_PROFILE.fallback_time_stamp_range,
        )

    def test_self_exiting_shell_is_declared(self) -> None:
        """-q / --quit-after-run：进程干净退出本身就是完成信号。"""

        self.assertTrue(MXU_LOG_PROFILE.exits_after_run)
        self.assertFalse(MFAAVALONIA_LOG_PROFILE.exits_after_run)


class IdleClockNoiseFilterTest(unittest.TestCase):
    """空闲时钟只认实质新增（upstream issue #388）。

    噪音行逐字取自真实 M9A UI 日志：MFA 的内存清理与热键 IPC 会稳定滚动，
    实测 log-20260517.log 里有整段 1 小时 51 分只有这两类行的窗口 ——
    此前任何一行新日志都会重置空闲时钟，RunTimeLimit 超时因而形同虚设。
    """

    _NOISE_A = "[2026-05-17 17:02:11.001] [INF] [内存管理]释放了 128 MB（12%)\n"
    _NOISE_B = "[2026-05-17 17:03:11.002] [INF] 热键 IPC 客户端已连接\n"
    _REAL = "[2026-05-17 17:04:11.003] [INF] 更新任务完成：名称=更新资源\n"

    def test_noise_only_growth_is_not_progress(self) -> None:
        previous = self._REAL
        current = previous + self._NOISE_A + self._NOISE_B
        self.assertFalse(
            MaaFWManager._has_substantive_progress(previous, current)
        )

    def test_real_line_among_noise_counts_as_progress(self) -> None:
        previous = self._REAL
        current = previous + self._NOISE_A + self._REAL
        self.assertTrue(MaaFWManager._has_substantive_progress(previous, current))

    def test_rotation_or_truncation_counts_as_progress(self) -> None:
        # 新内容不以旧内容为前缀 → 取不到可靠增量，宁可少判一次超时。
        self.assertTrue(
            MaaFWManager._has_substantive_progress(self._REAL, self._NOISE_A)
        )

    def test_registered_markers_come_from_the_profile(self) -> None:
        self.assertEqual(
            MFAAVALONIA_LOG_PROFILE.idle_noise_markers,
            ("[内存管理]", "热键 IPC 客户端已连接"),
        )
        # MXU 无真机样本，留空 → 退化成「任何新增都算进展」，与修复前一致。
        self.assertEqual(MXU_LOG_PROFILE.idle_noise_markers, ())


class PickLatestMxuLogTest(unittest.TestCase):
    def test_picks_highest_sequence_for_the_date(self) -> None:
        names = ["2026-08-06-1.log", "2026-08-06-2.log", "2026-08-05-9.log"]
        self.assertEqual(
            pick_latest_mxu_log(names, "2026-08-06"), "2026-08-06-2.log"
        )

    def test_sequence_compares_numerically(self) -> None:
        names = ["2026-08-06-9.log", "2026-08-06-10.log"]
        self.assertEqual(
            pick_latest_mxu_log(names, "2026-08-06"), "2026-08-06-10.log"
        )

    def test_ignores_non_matching_names(self) -> None:
        # maafw.log / agent 日志等同目录文件不得干扰选取。
        names = [
            "maafw.log",
            "maafw.bak.2026.08.08-14.30.58.956.log",
            "go-service.log",
            "mxu-agent-0-19728.log",
            "2026-08-06-x.log",
        ]
        self.assertIsNone(pick_latest_mxu_log(names, "2026-08-06"))

    def test_returns_none_for_other_dates(self) -> None:
        self.assertIsNone(pick_latest_mxu_log(["2026-08-05-1.log"], "2026-08-06"))


class ProfileRegistryTest(unittest.TestCase):
    def test_registry_covers_known_families_only(self) -> None:
        self.assertEqual(
            set(SHELL_LOG_PROFILES),
            {ShellFamily.MFAAVALONIA, ShellFamily.MXU},
        )
        self.assertIs(
            get_shell_log_profile(ShellFamily.MFAAVALONIA), MFAAVALONIA_LOG_PROFILE
        )
        self.assertIs(get_shell_log_profile(ShellFamily.MXU), MXU_LOG_PROFILE)
        self.assertIsNone(get_shell_log_profile(ShellFamily.UNKNOWN))

    def test_profile_requires_at_least_one_path_shape(self) -> None:
        common = dict(
            family=ShellFamily.MXU,
            run_validated=False,
            time_stamp_range=(0, 19),
            time_format="%Y-%m-%d %H:%M:%S",
            completion_markers=(),
            abandon_markers=(),
            controller_failure_markers=(),
            failure_markers=(),
            task_start_markers=(),
            stop_markers=(),
        )
        with self.assertRaises(ValueError):
            ShellLogProfile(**common)
        # 两条都给是合法的：MXU 就是「固定名优先、日期序号名回退」。
        both = ShellLogProfile(
            **common,
            log_relpath_strftime="logs/a.log",
            log_glob_dir="debug",
        )
        self.assertEqual(both.log_relpath_strftime, "logs/a.log")
        self.assertEqual(both.log_glob_dir, "debug")


if __name__ == "__main__":
    unittest.main()
