#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""BAAH 配置托管与推送日志采集的最小回归测试。

覆盖 BAAH 专项最容易出错的三处契约：配置名的解析与校验、运行前托管写入与
运行后恢复的完整往返（含配置文件原本不存在的情况）、任务节点采集规则能否
从真实日志行里取到任务名。
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from app.task.BAAH.tools.config_manager import (
    MANAGED_SOFTWARE_VALUES,
    MANAGED_USER_VALUES,
    apply_managed_config,
    latest_log_file,
    list_config_names,
    read_json,
    resolve_config_name,
    resolve_log_time_range,
    resolve_user_config_path,
    restore_managed_config,
)


class TestResolveConfigName:
    """配置名解析与校验"""

    def test_strips_json_suffix_and_spaces(self) -> None:
        assert resolve_config_name("  国服2.json  ") == "国服2"
        assert resolve_config_name("国服2") == "国服2"

    @pytest.mark.parametrize("value", ["", "   ", ".json", ".", ".."])
    def test_rejects_empty_names(self, value: str) -> None:
        with pytest.raises(ValueError):
            resolve_config_name(value)

    @pytest.mark.parametrize("value", [r"..\evil", "../evil", r"a\b", "a/b"])
    def test_rejects_path_separators(self, value: str) -> None:
        with pytest.raises(ValueError):
            resolve_config_name(value)

    def test_resolve_user_config_path_appends_suffix(self, tmp_path: Path) -> None:
        path = resolve_user_config_path(tmp_path, "国服2.json")
        assert path == tmp_path / "国服2.json"


class TestManagedConfigRoundTrip:
    """托管写入与恢复"""

    def test_writes_managed_values_and_restores_original(self, tmp_path: Path) -> None:
        user_path = tmp_path / "BAAH_CONFIGS" / "国服2.json"
        user_path.parent.mkdir(parents=True)
        original = {"SERVER_TYPE": "CN", "CLOSE_BAAH_FINISH": False, "KEEP_ME": 7}
        user_path.write_text(json.dumps(original), encoding="utf-8")

        software_path = tmp_path / "DATA" / "CONFIGS" / "software_config.json"
        software_path.parent.mkdir(parents=True)
        software_original = {"LANGUAGE": "zh_CN", "SAVE_LOG_TO_FILE": False}
        software_path.write_text(json.dumps(software_original), encoding="utf-8")

        backup = apply_managed_config(user_path, software_path)

        # 托管项已写入，且原有字段未被破坏
        managed_user = json.loads(user_path.read_text(encoding="utf-8"))
        for key, value in MANAGED_USER_VALUES.items():
            assert managed_user[key] == value
        assert managed_user["SERVER_TYPE"] == "CN"
        assert managed_user["KEEP_ME"] == 7

        managed_software = json.loads(software_path.read_text(encoding="utf-8"))
        for key, value in MANAGED_SOFTWARE_VALUES.items():
            assert managed_software[key] == value
        assert managed_software["LANGUAGE"] == "zh_CN"

        restore_managed_config(backup)

        # 恢复为运行前的原值
        assert json.loads(user_path.read_text(encoding="utf-8")) == original
        assert (
            json.loads(software_path.read_text(encoding="utf-8")) == software_original
        )

    def test_removes_config_created_during_run(self, tmp_path: Path) -> None:
        """运行前不存在的配置文件，恢复阶段应被删除而不是留下半成品"""

        user_path = tmp_path / "BAAH_CONFIGS" / "新建.json"
        backup = apply_managed_config(user_path, None)
        assert user_path.is_file()

        restore_managed_config(backup)
        assert not user_path.exists()

    def test_written_file_has_no_bom(self, tmp_path: Path) -> None:
        """BAAH 带 BOM 会静默按默认值运行，写盘必须是无 BOM 的 UTF-8"""

        user_path = tmp_path / "BAAH_CONFIGS" / "国服2.json"
        apply_managed_config(user_path, None)

        raw = user_path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        json.loads(raw.decode("utf-8"))

    def test_restore_is_safe_without_apply(self, tmp_path: Path) -> None:
        from app.task.BAAH.tools.config_manager import ManagedConfigBackup

        restore_managed_config(
            ManagedConfigBackup(user_config_path=tmp_path / "x.json")
        )

    def test_restore_accepts_none_backup(self) -> None:
        """任务在托管配置写入前被中止时，收尾阶段会拿到 None，不应抛异常"""
        restore_managed_config(None)

    def test_applied_is_false_when_nothing_needed_changing(
        self, tmp_path: Path
    ) -> None:
        """配置本来就是托管值时不写文件，收尾阶段也无需恢复"""

        user_path = tmp_path / "BAAH_CONFIGS" / "已托管.json"
        user_path.parent.mkdir(parents=True)
        user_path.write_text(json.dumps(dict(MANAGED_USER_VALUES)), encoding="utf-8")

        backup = apply_managed_config(user_path, None)

        assert backup.applied is False
        assert restore_managed_config(backup) == []

    def test_rolls_back_user_config_when_software_write_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """软件配置写入失败时，已经落盘的用户配置必须回滚

        调用方只在写入成功后才会拿到备份对象；这里不回滚的话，用户配置就会
        带着托管值留下来，而收尾阶段已经无从恢复。
        """

        user_path = tmp_path / "BAAH_CONFIGS" / "国服2.json"
        user_path.parent.mkdir(parents=True)
        original = {"SERVER_TYPE": "CN", "KEEP_ME": 7}
        user_path.write_text(json.dumps(original), encoding="utf-8")

        software_path = tmp_path / "DATA" / "CONFIGS" / "software_config.json"

        import app.task.BAAH.tools.config_manager as config_manager

        real_write = config_manager.write_json

        def flaky_write(path: Path, data: dict) -> None:
            if path == software_path:
                raise OSError("模拟软件配置不可写")
            real_write(path, data)

        monkeypatch.setattr(config_manager, "write_json", flaky_write)

        with pytest.raises(OSError):
            apply_managed_config(user_path, software_path)

        assert json.loads(user_path.read_text(encoding="utf-8")) == original

    def test_reports_restore_failure_instead_of_swallowing_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """恢复失败必须回传给调用方：静默返回会让用户配置一直带着托管值"""

        user_path = tmp_path / "BAAH_CONFIGS" / "国服2.json"
        user_path.parent.mkdir(parents=True)
        user_path.write_text(json.dumps({"KEEP_ME": 7}), encoding="utf-8")

        backup = apply_managed_config(user_path, None)

        import app.task.BAAH.tools.config_manager as config_manager

        def boom(path: Path, data: dict) -> None:
            raise OSError("模拟配置文件只读")

        monkeypatch.setattr(config_manager, "write_json", boom)

        failures = restore_managed_config(backup)

        assert len(failures) == 1
        assert "国服2.json" in failures[0]


class TestReadJson:
    """配置读取的容错边界

    只有「文件不存在」能当作空配置：把读取失败或内容损坏当成空，托管流程
    就会拿这个空对象去比对与恢复，运行结束后等于把用户的配置清空。
    """

    def test_missing_file_is_empty_dict(self, tmp_path: Path) -> None:
        assert read_json(tmp_path / "不存在.json") == {}

    def test_corrupted_content_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "损坏.json"
        path.write_text("{ 这不是 JSON", encoding="utf-8")

        with pytest.raises(ValueError):
            read_json(path)

    def test_non_object_top_level_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "数组.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError):
            read_json(path)

    def test_read_failure_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """读取被拒绝时必须抛出，不能退化成空配置"""

        path = tmp_path / "被占用.json"
        path.write_text('{"KEEP": 1}', encoding="utf-8")

        real_read_text = Path.read_text

        def boom(self: Path, *args: object, **kwargs: object) -> str:
            if self == path:
                raise PermissionError("模拟被其他程序占用")
            return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "read_text", boom)

        with pytest.raises(PermissionError):
            read_json(path)

    def test_bom_is_tolerated(self, tmp_path: Path) -> None:
        path = tmp_path / "带BOM.json"
        path.write_bytes('{"KEEP": 1}'.encode("utf-8-sig"))

        assert read_json(path) == {"KEEP": 1}


class TestLatestLogFile:
    """日志文件定位"""

    def test_picks_newest_after_start_time(self, tmp_path: Path) -> None:
        old_log = tmp_path / "log_2026-01-01-00-00-00.txt"
        old_log.write_text("old", encoding="utf-8")

        start_at = time.time()
        new_log = tmp_path / "log_2026-01-01-00-00-01.txt"
        new_log.write_text("new", encoding="utf-8")

        # 显式设定时间戳：同一秒内连续创建的两个文件在部分文件系统上
        # 无法靠写入顺序区分先后
        os.utime(old_log, (start_at - 10, start_at - 10))
        os.utime(new_log, (start_at + 1, start_at + 1))

        assert latest_log_file(tmp_path, start_at) == new_log

    def test_returns_none_when_no_recent_log(self, tmp_path: Path) -> None:
        (tmp_path / "log_old.txt").write_text("old", encoding="utf-8")
        assert latest_log_file(tmp_path, time.time() + 60) is None

    def test_returns_none_for_missing_dir(self, tmp_path: Path) -> None:
        assert latest_log_file(tmp_path / "missing", 0.0) is None


class TestLogTimestampRange:
    """日志时间戳切片

    区间由 LogMonitor 直接对整行做字符切片（``line[start:end]``），且必须按首行
    的实际排版推算：版本号位数会随版本变化，写死的区间一旦对不上，每一行都会解析
    失败并被静默丢弃 —— 任务照常跑，却一行日志都采集不到，也永远判不出成功标记。
    """

    # 真实日志行（BAAH 2.4.13 实测输出）
    REAL_LINE = "2.4.13 - 24:19 - INFO : 执行任务EnterGame"
    # 版本号多一位的假想行：写死区间会在这里失配
    LONGER_VERSION_LINE = "2.4.100 - 24:19 - INFO : 执行任务EnterGame"

    @staticmethod
    def _write_log(tmp_path: Path, line: str) -> Path:
        log_path = tmp_path / "log_2026-09-12-17-24-19.txt"
        log_path.write_text(line + "\n", encoding="utf-8")
        return log_path

    def test_slices_timestamp_from_real_line(self, tmp_path: Path) -> None:
        from app.task.BAAH.AutoProxy import BAAH_LOG_TIME_FORMAT

        log_path = self._write_log(tmp_path, self.REAL_LINE)
        time_range = resolve_log_time_range(log_path, BAAH_LOG_TIME_FORMAT)

        assert time_range is not None
        start, end = time_range
        assert self.REAL_LINE[start:end] == "24:19"

        parsed = datetime.strptime("24:19", BAAH_LOG_TIME_FORMAT)
        assert (parsed.minute, parsed.second) == (24, 19)

    def test_follows_longer_version_numbers(self, tmp_path: Path) -> None:
        """上游换成长版本号后仍要切到时间戳，不能沿用固定区间"""

        from app.task.BAAH.AutoProxy import BAAH_LOG_TIME_FORMAT

        log_path = self._write_log(tmp_path, self.LONGER_VERSION_LINE)
        time_range = resolve_log_time_range(log_path, BAAH_LOG_TIME_FORMAT)

        assert time_range is not None
        start, end = time_range
        assert self.LONGER_VERSION_LINE[start:end] == "24:19"

    def test_skips_leading_blank_lines(self, tmp_path: Path) -> None:
        from app.task.BAAH.AutoProxy import BAAH_LOG_TIME_FORMAT

        log_path = tmp_path / "log.txt"
        log_path.write_text("\n\n" + self.REAL_LINE + "\n", encoding="utf-8")

        time_range = resolve_log_time_range(log_path, BAAH_LOG_TIME_FORMAT)

        assert time_range is not None
        start, end = time_range
        assert self.REAL_LINE[start:end] == "24:19"

    def test_returns_none_without_separator(self, tmp_path: Path) -> None:
        from app.task.BAAH.AutoProxy import BAAH_LOG_TIME_FORMAT

        log_path = self._write_log(tmp_path, "这一行没有分隔符")

        assert resolve_log_time_range(log_path, BAAH_LOG_TIME_FORMAT) is None

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        from app.task.BAAH.AutoProxy import BAAH_LOG_TIME_FORMAT

        missing = tmp_path / "不存在.txt"

        assert resolve_log_time_range(missing, BAAH_LOG_TIME_FORMAT) is None

    def test_logmonitor_start_filter_accepts_line(self, tmp_path: Path) -> None:
        """模拟 LogMonitor 的起始过滤：真实日志行必须能被判为「晚于启动时刻」"""

        from app.task.BAAH.AutoProxy import BAAH_LOG_TIME_FORMAT
        from app.utils.LogMonitor import strptime as monitor_strptime

        log_path = self._write_log(tmp_path, self.REAL_LINE)
        time_range = resolve_log_time_range(log_path, BAAH_LOG_TIME_FORMAT)
        assert time_range is not None
        start, end = time_range

        log_start_time = datetime(2026, 9, 12, 17, 24, 16)
        parsed = monitor_strptime(
            self.REAL_LINE[start:end],
            BAAH_LOG_TIME_FORMAT,
            datetime(2026, 9, 12, 17, 24, 20),
        )

        assert parsed > log_start_time


class TestPushLogNodeRules:
    """任务节点采集规则

    行取自 BAAH 2.4.13 的真实运行日志。BAAH 每次运行都新建日志文件，MAS 在定位
    到该文件之后才开始采集，所以这里先写入「会话开始之前就有的内容」，再用追加
    写入模拟会话内新增的日志行，走完整链路（日志源 → 规则 → baah_resolve → sink）。
    """

    # 真实日志行（BAAH 2.4.13 实测输出）
    TRY_ENTER = "2.4.13 - 24:33 - INFO : 判断任务EnterGame是否可以执行"
    RUN_ENTER = "2.4.13 - 24:33 - INFO : 执行任务EnterGame"
    DONE_LOGIN = "2.4.13 - 26:01 - INFO : 任务Loginin执行结束"
    DONE_ENTER = "2.4.13 - 26:22 - INFO : 任务EnterGame执行结束"
    SKIP_CLOSE = (
        "2.4.13 - 26:21 - WARN : 任务CloseInform执行前条件不成立或超时，跳过此任务"
    )
    CRASH = (
        "2.4.13 - 26:24 - ERROR : 运行出错: 由于卡顿或其他原因，"
        "截图文件损坏，请尝试清理电脑内存后重启程序"
    )
    # 失败原因里带任务名（BAAH 2.2.14 的真实日志）
    CRASH_IN_TASK = (
        "2.2.14 - 43:46 - ERROR : 运行出错: 任务InCafe执行后条件不成立或超时，"
        "且无法正确返回主页，程序退出"
    )
    # 会话开始之前就写在日志里的任务行：采集从文件末尾起算，它不该进入结果
    BEFORE_SESSION = "2.4.13 - 24:19 - INFO : 执行任务CollectPower"

    @staticmethod
    def _write_log(tmp_path: Path, head: str) -> Path:
        log_path = tmp_path / "log_2026-09-12-17-24-19.txt"
        log_path.write_text(head, encoding="utf-8")
        return log_path

    @staticmethod
    def _collect(log_path: Path, new_lines: list[str]) -> list[tuple[str, str, float]]:
        """采集会话内新增的日志行并返回 sink 收到的结果"""

        from app.log_box import log_box
        from app.task.BAAH.tools import BAAH_PUSH_RULES, baah_resolve

        collected: list[tuple[str, str, float]] = []
        collect = log_box.get_collect(
            paths=[log_path],
            sink=lambda *item: collected.append(item),
            start_from_end=True,
        )
        collect.open()
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write("\n".join(new_lines) + "\n")
        for rule in BAAH_PUSH_RULES:
            collect.collect(*rule)
        collect.close(baah_resolve)
        return collected

    def _nodes(self, log_path: Path, new_lines: list[str]) -> list[str]:
        return [item[1] for item in self._collect(log_path, new_lines)]

    def test_extracts_task_nodes_from_real_lines(self, tmp_path: Path) -> None:
        """执行/结束/跳过三类行各自成节点，会话前的内容不进结果"""

        log_path = self._write_log(tmp_path, self.BEFORE_SESSION + "\n")

        collected = self._collect(
            log_path,
            [
                self.TRY_ENTER,
                self.RUN_ENTER,
                self.DONE_LOGIN,
                self.SKIP_CLOSE,
                self.DONE_ENTER,
            ],
        )

        ## 只钉「哪些节点、什么状态」：节点顺序按最后一次出现排列（BAAH 会把同一
        ## 任务重跑多次，报告呈现的是最后一次的流程顺序），顺序本身不是这里的契约。
        ## 「判断任务X是否可以执行」不产出节点；条目类型保持普通——节点级失败由文本
        ## 体现，不参与未完成用户过滤
        assert {(item[0], item[1]) for item in collected} == {
            ("普通", "✅ 成功: EnterGame"),
            ("普通", "✅ 成功: Loginin"),
            ("普通", "⏭ 跳过: CloseInform"),
        }
        assert all(item[2] > 0 for item in collected)

    def test_running_task_marked_failed_on_runtime_error(self, tmp_path: Path) -> None:
        """运行出错时仍在执行的任务按失败呈现，而不是开始标记的默认成功"""

        log_path = self._write_log(tmp_path, "")

        assert self._nodes(log_path, [self.RUN_ENTER, self.CRASH]) == [
            "❌ 失败: EnterGame"
        ]

    def test_error_becomes_node_when_no_task_running(self, tmp_path: Path) -> None:
        """一个任务都没进去就出错时，没有可归属的任务，输出上游给的原因"""

        log_path = self._write_log(tmp_path, "")

        assert self._nodes(log_path, [self.CRASH]) == [
            "❌ 失败: 由于卡顿或其他原因，截图文件损坏，请尝试清理电脑内存后重启程序"
        ]

    def test_error_reason_with_task_name_is_not_taken_as_task(
        self, tmp_path: Path
    ) -> None:
        """失败原因里含「任务X执行后…」时不能被任务正则当成正常节点行吞掉"""

        log_path = self._write_log(tmp_path, "")

        assert self._nodes(log_path, [self.CRASH_IN_TASK]) == [
            "❌ 失败: 任务InCafe执行后条件不成立或超时，且无法正确返回主页，程序退出"
        ]


class TestListConfigNames:
    """配置目录列举：下拉选项只来自目录里真实存在的配置"""

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        assert list_config_names(tmp_path / "BAAH_CONFIGS") == []

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "BAAH_CONFIGS"
        config_dir.mkdir()

        assert list_config_names(config_dir) == []

    def test_lists_json_names_without_suffix_sorted(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "BAAH_CONFIGS"
        config_dir.mkdir()
        for name in ["b活动", "日常", "a日常"]:
            (config_dir / f"{name}.json").write_text("{}", encoding="utf-8")

        assert list_config_names(config_dir) == ["a日常", "b活动", "日常"]

    def test_ignores_non_json_and_directories(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "BAAH_CONFIGS"
        config_dir.mkdir()
        (config_dir / "日常.json").write_text("{}", encoding="utf-8")
        (config_dir / "日常.json.tmp").write_text("{}", encoding="utf-8")
        (config_dir / "readme.txt").write_text("x", encoding="utf-8")
        (config_dir / "子目录.json").mkdir()

        assert list_config_names(config_dir) == ["日常"]
