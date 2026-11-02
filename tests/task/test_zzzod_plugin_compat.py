"""插件可选扩展不能破坏内置任务目录、运行监控或进度保护。"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.task.ZzzOd.AutoProxy import (
    AutoProxyTask,
    _judge_after,
    _judge_baseline,
)
from app.task.ZzzOd.service import read_task_catalog
from app.task.ZzzOd.tools import catalog
from app.task.ZzzOd.tools import zzz_od_config as records


@pytest.fixture
def install(tmp_path):
    app_dir = tmp_path / "src/zzz_od/application/mail"
    app_dir.mkdir(parents=True)
    (app_dir / "mail_const.py").write_text(
        'APP_ID = "mail"\nAPP_NAME = "邮件"\nDEFAULT_GROUP = True\nPRIORITY = 1\n',
        encoding="utf-8",
    )
    return tmp_path


def plugin(root, name="extra", *, daily=True, internal=False):
    folder = root / "plugins" / name
    folder.mkdir(parents=True)
    # 若错误地导入工厂，测试应立刻失败。
    (folder / f"{name}_factory.py").write_text("raise RuntimeError('must not import')")
    (folder / f"{name}_const.py").write_text(
        f'APP_ID: str = "{name}"\nAPP_NAME = "插件"\n'
        f"DEFAULT_GROUP = {daily}\nINTERNAL_APP = {internal}\n",
        encoding="utf-8",
    )
    return folder


def test_plugins_share_catalog_without_execution_and_use_native_settings(install):
    plugin(install)
    plugin(install, "standalone", daily=False)
    plugin(install, "internal", daily=False, internal=True)
    items = {item["app_id"]: item for item in read_task_catalog(install)}
    assert set(items) == {"mail", "extra", "standalone", "internal"}
    assert items["extra"]["default_group"]
    assert items["extra"]["jump"] and not items["extra"]["configurable"]
    assert not items["standalone"]["default_group"]
    assert not items["internal"]["default_group"]


@pytest.mark.parametrize(
    "declaration",
    [
        "APP_ID = (",  # 更新中截断
        "APP_ID = compute_id()",  # 不执行动态声明
        'APP_ID = "bad"\nAPP_NAME = "坏插件"\nDEFAULT_GROUP = "True"',
        'APP_ID = "bad"\nAPP_NAME = "坏插件"\nDEFAULT_GROUP = True\nINTERNAL_APP = True',
        'APP_ID = "../mail"\nAPP_NAME = "坏插件"\nDEFAULT_GROUP = True',
    ],
)
def test_bad_plugin_is_logged_without_hiding_builtin_or_other_plugin(
    install, monkeypatch, declaration
):
    folder = plugin(install, "bad")
    (folder / "bad_const.py").write_text(declaration, encoding="utf-8")
    plugin(install)
    warnings = []
    monkeypatch.setattr(catalog, "logger", SimpleNamespace(warning=warnings.append))
    assert {item["app_id"] for item in catalog.list_app_catalog(install)} == {
        "mail",
        "extra",
    }
    assert warnings and "bad" in warnings[0]


def test_duplicate_plugin_cannot_override_builtin(install, monkeypatch):
    plugin(install, "mail")
    warnings = []
    monkeypatch.setattr(catalog, "logger", SimpleNamespace(warning=warnings.append))
    items = catalog.list_app_catalog(install)
    assert len(items) == 1 and items[0]["app_name"] == "邮件"
    assert warnings


def test_unreadable_plugin_root_does_not_break_builtin_catalog(install, monkeypatch):
    (install / "plugins").mkdir()
    original = type(install).iterdir

    def denied(path):
        if path == install / "plugins":
            raise PermissionError("blocked plugin directory")
        return original(path)

    monkeypatch.setattr(type(install), "iterdir", denied)
    assert [item["app_id"] for item in catalog.list_app_catalog(install)] == ["mail"]


def test_plugin_progress_survives_clear_restore_and_metadata_disappearance(install):
    plugin(install)
    record_dir = install / "config/1001/app_run_record"
    record_dir.mkdir(parents=True)
    (record_dir / "mail.yml").write_text("run_status: 1\n")
    target = record_dir / "extra.yml"
    target.write_bytes(b"run_status: 1\nopaque_progress: 2\n")
    backup = install / "backup"
    records.backup_instance(install, 1001, backup)
    # 声明突然失效，仍然保留未知任务的完整记录。
    (install / "plugins/extra/extra_const.py").write_text("broken (")
    records.clear_run_records(install, 1001)
    assert not (record_dir / "mail.yml").exists()
    before = records.snapshot_run_record_files(install, 1001)
    assert target.name in before
    assert _judge_baseline(install, 1001)["extra"] == 0
    assert _judge_after(install, 1001, before)["extra"] == 0
    target.write_bytes(b"run_status: 1\nopaque_progress: 3\n")
    assert _judge_after(install, 1001, before)["extra"] == 1
    current = records.snapshot_run_record_files(install, 1001)
    records.restore_instance(install, 1001, backup)
    records.restore_run_record_files(install, 1001, current)
    assert target.read_bytes() == b"run_status: 1\nopaque_progress: 3\n"


def test_malformed_plugin_record_does_not_hide_builtin_result(install, monkeypatch):
    record_dir = install / "config/1001/app_run_record"
    record_dir.mkdir(parents=True)
    (record_dir / "extra.yml").write_text("- unexpected\n")
    (record_dir / "mail.yml").write_text("run_status: 1\n")
    warnings = []
    monkeypatch.setattr(records, "logger", SimpleNamespace(warning=warnings.append))
    assert records.snapshot_run_records(install, 1001) == {"extra": 0, "mail": 1}
    assert warnings and "extra.yml" in warnings[0]


@pytest.mark.parametrize("suffix", [".json", ".bak", ".txt"])
def test_plugin_sidecar_does_not_erase_failure_and_is_still_preserved(install, suffix):
    record_dir = install / "config/1001/app_run_record"
    record_dir.mkdir(parents=True)
    target = record_dir / "extra.yml"
    target.write_bytes(b"run_status: 0\n")
    sidecar = record_dir / f"extra{suffix}"
    sidecar.write_bytes(b"opaque plugin data")
    before = records.snapshot_run_record_files(install, 1001)
    target.write_bytes(b"run_status: 2\n")
    (record_dir / "mail.yml").write_bytes(b"run_status: 1\n")
    after = _judge_after(install, 1001, before)
    assert after == {"extra": 2, "mail": 1}
    assert (
        records.snapshot_run_record_files(install, 1001)[sidecar.name]
        == sidecar.read_bytes()
    )
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_log = SimpleNamespace(status="")
    proxy.cur_user_item = SimpleNamespace(status="运行")
    proxy.script_info = SimpleNamespace(log="")
    proxy._app_name_book = {"mail": "邮件", "extra": "插件"}
    proxy._plugin_app_ids = frozenset({"extra"})
    # 缺少应用终态日志时仍应采信上游记录，不能被其他任务成功掩盖。
    proxy._judge_final({"extra": 0}, after, "")
    assert not proxy.run_book
    assert proxy.cur_user_item.status == "异常"
    assert "插件" in proxy.cur_user_log.status


def test_one_plugin_record_write_failure_does_not_block_other_records(
    install, monkeypatch
):
    original = records._utils_io.atomic_write
    warnings = []

    def write(path, payload):
        if path.name == "bad.yml":
            raise PermissionError("plugin record locked")
        return original(path, payload)

    monkeypatch.setattr(records._utils_io, "atomic_write", write)
    monkeypatch.setattr(records, "logger", SimpleNamespace(warning=warnings.append))
    records.restore_run_record_files(
        install, 1001, {"bad.yml": b"locked", "extra.yml": b"opaque progress"}
    )
    assert (
        install / "config/1001/app_run_record/extra.yml"
    ).read_bytes() == b"opaque progress"
    assert warnings and "bad.yml" in warnings[0]


@pytest.mark.asyncio
async def test_plugin_failure_does_not_release_running_workflow():
    import asyncio

    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_log = SimpleNamespace(content=[], status="")
    proxy.script_info = SimpleNamespace(log="", log_first_line=0)
    proxy.script_config = SimpleNamespace(Run=SimpleNamespace(RunTimeLimit=10))
    proxy.launcher_process_manager = SimpleNamespace(is_running=running)
    proxy.wait_event = asyncio.Event()
    proxy.is_log_stalled = lambda *args, **kwargs: False
    await proxy.check_log(["指令[ 插件 ] 执行失败\n"], datetime.now())
    assert not proxy.wait_event.is_set()
    assert proxy.cur_user_log.status == "ZZZ-OD 正常运行中"


async def running():
    return True


def test_plugin_failure_is_reported_without_retrying_completed_builtins():
    from app.utils.common.constants import BASE_INDEPENDENT

    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_log = SimpleNamespace(status="Success!")
    proxy.cur_user_item = SimpleNamespace(status="运行")
    proxy.script_info = SimpleNamespace(log="")
    proxy._app_name_book = {"mail": "邮件", "extra": "插件"}
    proxy._plugin_app_ids = frozenset({"extra"})
    proxy._futile_app_ids = frozenset()
    proxy.base = BASE_INDEPENDENT
    proxy.account_switch = "单实例切换"
    complete = "指令[ 插件 ] 执行失败\n指令[ 一条龙 ] 执行成功"
    proxy._judge_final({}, {"mail": 1, "extra": 2}, complete)
    assert not proxy.run_book
    assert proxy.cur_user_item.status == "异常"
    assert "插件" in proxy.cur_user_log.status
    assert proxy._all_failures_futile(complete)
    assert not proxy._all_failures_futile("指令[ 插件 ] 执行失败")
    proxy._failed_app_ids = ["extra", "mail"]
    assert not proxy._all_failures_futile(complete)


def test_real_upstream_fatal_error_is_not_hidden_by_plugin_compatibility():
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_log = SimpleNamespace(status="Success!")
    proxy.cur_user_item = SimpleNamespace(status="运行")
    proxy.script_info = SimpleNamespace(log="")
    proxy._judge_final({}, {"mail": 1}, "运行应用 one_dragon 失败")
    assert not proxy.run_book
    assert proxy.cur_user_item.status == "异常"
