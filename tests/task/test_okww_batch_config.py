"""批次重试只排除当前轮次已由上游标记成功的账号。"""

import json

import pytest

from app.task.Okww.tools.batch_config import completed_accounts, write_attempt


def test_attempt_resets_stale_results_and_only_accepts_current_success(tmp_path):
    accounts = [
        {"account_key": "1234567", "enabled": True, "task": None, "config": {}},
        {"account_key": "2345678", "enabled": True, "task": None, "config": {}},
    ]
    (tmp_path / "MultiAccountResults.json").write_text(
        json.dumps({"2345678": {"status": "success"}}), encoding="utf-8"
    )
    write_attempt(tmp_path, accounts)
    assert completed_accounts(tmp_path, {"1234567", "2345678"}) == set()
    (tmp_path / "MultiAccountResults.json").write_text(
        json.dumps({"1234567": {"status": "success"}, "2345678": {"status": "failed"}}),
        encoding="utf-8",
    )
    assert completed_accounts(tmp_path, {"1234567", "2345678"}) == {"1234567"}
    write_attempt(tmp_path, accounts[1:])
    assert completed_accounts(tmp_path, {"2345678"}) == set()
    assert (
        json.loads((tmp_path / "MultiAccountConfig.json").read_text(encoding="utf-8"))[
            "accounts"
        ]
        == accounts[1:]
    )


def test_invalid_and_duplicate_account_identifiers_fail_before_write(tmp_path):
    for accounts in (
        [{"account_key": "123****4567"}],
        [{"account_key": "123"}, {"account_key": "123"}],
    ):
        with pytest.raises(ValueError):
            write_attempt(tmp_path, accounts)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_batch_log_keeps_confirmed_success_when_later_account_fails(tmp_path):
    import asyncio
    from datetime import datetime
    from unittest.mock import AsyncMock

    from app.task.Okww.BatchProxy import BatchProxyTask
    from tests.runtime_support import RuntimeStub as SimpleNamespace

    proxy = BatchProxyTask.__new__(BatchProxyTask)
    proxy.task_name = "MultiAccountConfigTask"
    proxy.cur_user_log = SimpleNamespace(content=[], status="")
    proxy.cur_user_item = SimpleNamespace(status="运行")
    proxy.script_info = SimpleNamespace(log="", log_first_line=0)
    proxy.wait_event = asyncio.Event()
    proxy.okww_process_manager = SimpleNamespace(
        is_running=AsyncMock(return_value=True)
    )
    proxy.is_log_stalled = lambda *args, **kwargs: False
    proxy.script_config = SimpleNamespace(Run=SimpleNamespace(RunTimeLimit=30))
    proxy.script_config_path = tmp_path
    proxy.pending = {"A", "B"}
    proxy.succeeded = set()
    proxy.account_failures = {}
    proxy.attempted_accounts = set()
    proxy.account_users = {key: SimpleNamespace(status="运行") for key in proxy.pending}
    (tmp_path / "MultiAccountResults.json").write_text(
        json.dumps({"A": {"status": "success"}, "B": {"status": "failed"}}),
        encoding="utf-8",
    )
    await proxy.check_log(
        [
            "MultiAccountConfigTask:info_set 当前账号 B\n",
            "MultiAccountConfigTask:info_set 状态 执行失败\n",
        ],
        datetime.now(),
    )
    assert proxy.succeeded == {"A"}
    assert proxy.account_failures == {"B": "OK-WW 切换账号失败"}
    assert proxy.account_users["A"].status == "完成"
    assert proxy.wait_event.is_set()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("13012346220", "1306220"),
        ("130****6220", "1306220"),
        (" 1306220 ", "1306220"),
        ("Ab****12@example.com", "Ab12@example.com"),
        ("Some Name", "Some Name"),
    ],
)
def test_phone_normalization_matches_upstream_login_text(value, expected):
    from app.task.Okww.tools.batch_config import normalize_account_key

    assert normalize_account_key(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "6220",
        "1301234622",
        "12012346220",
        "130***6220",
        "abc@",
        "****@example.com",
        "130-1234-6220",
        "Some\x00Name",
    ],
)
def test_invalid_account_identifiers_are_rejected(value):
    from app.task.Okww.tools.batch_config import normalize_account_key

    with pytest.raises(ValueError):
        normalize_account_key(value)


@pytest.mark.asyncio
async def test_batch_check_rejects_normalized_duplicates(monkeypatch):
    import uuid
    from unittest.mock import AsyncMock

    from app.models.config.script import OkwwUserConfig
    from app.task.Okww.AutoProxy import AutoProxyTask
    from app.task.Okww.BatchProxy import BatchProxyTask
    from tests.runtime_support import RuntimeStub as SimpleNamespace

    ids = [uuid.uuid4(), uuid.uuid4()]
    proxy = BatchProxyTask.__new__(BatchProxyTask)
    proxy.participants = [
        SimpleNamespace(user_id=str(uid), name=f"用户{index}")
        for index, uid in enumerate(ids)
    ]
    proxy.user_config = {
        ids[0]: OkwwUserConfig.model_validate({"Info": {"Id": "13012346220"}}),
        ids[1]: OkwwUserConfig.model_validate({"Info": {"Id": "130****6220"}}),
    }
    monkeypatch.setattr(AutoProxyTask, "check", AsyncMock(return_value="Pass"))
    result = await proxy.check()
    assert result != "Pass"
    assert "13012346220" not in result
    proxy.user_config[ids[1]] = OkwwUserConfig.model_validate(
        {"Info": {"Id": "13912347052"}}
    )
    assert await proxy.check() == "Pass"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("login", "failure", "expected"),
    [
        (False, True, "切换账号"),
        (True, True, "账号任务"),
        (True, False, None),
    ],
)
async def test_batch_nodes_route_terminal_failure_to_account(login, failure, expected):
    from app.models.task import LogRecord
    from app.task.Okww.BatchProxy import BatchProxyTask
    from tests.runtime_support import RuntimeStub as SimpleNamespace

    lines = [
        "MultiAccountConfigTask:info_set 状态 执行中\n",
        "MultiAccountConfigTask:info_set 当前账号 A\n",
        "MultiAccountConfigTask:ComboBox 切号失败，回退 OCR：WaitFailedException\n",
    ]
    if login:
        lines.append("MultiAccountConfigTask:A logged in successfully\n")
    if failure:
        lines.append("MultiAccountConfigTask:info_set 状态 执行失败\n")
    # 新一轮的前置日志不能继续归属上一轮的 A。
    lines += [
        "MultiAccountConfigTask:info_set 状态 执行中\n",
        "MultiAccountConfigTask:正在返回登录界面\n",
    ]
    proxy = BatchProxyTask.__new__(BatchProxyTask)
    proxy.batch_nodes_collected = False
    proxy.user_state = lambda user: user
    proxy.account_failures = {}
    proxy.attempted_accounts = set()
    proxy.account_users = {
        key: SimpleNamespace(user_id=key, push_log_mode="汇总", push_log=[])
        for key in ["A", "B"]
    }
    proxy.batch_records = {key: LogRecord() for key in ["A", "B"]}
    proxy._log_source = SimpleNamespace(read_new=lambda: iter(lines))
    await proxy._collect_log_details()
    a_nodes = [entry[1] for entry in proxy.account_users["A"].push_log]
    if expected:
        assert f"❌ 失败: {expected}" in a_nodes
        assert proxy.account_failures == {"A": f"OK-WW {expected}失败"}
    else:
        assert not any("失败" in node for node in a_nodes)
        assert proxy.account_failures == {}
    assert proxy.account_users["B"].push_log == []
    assert proxy.batch_records["B"].content == []
    assert not any(
        "正在返回登录界面" in line for line in proxy.batch_records["A"].content
    )
