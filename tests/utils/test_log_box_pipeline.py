"""纯文本内核：显式输入、元数据、前后处理和异常传播。"""

import re

import pytest

from app.utils import log_box
from app.utils.common.expression.parser import ExpressionError
from app.utils.common.log.patterns import MultiLineAggregator


def test_pipeline_has_no_source_user_or_delivery_interfaces(monkeypatch):
    monkeypatch.setenv("MAS_SCRIPT_LOG_PATH", "must-not-be-opened")
    assert not any(
        hasattr(log_box, name)
        for name in (
            "LogSpec",
            "EntrySpec",
            "LogBinding",
            "SessionResult",
            "LogCollect",
            "log_box",
        )
    )
    pipeline = log_box.LogPipeline()
    pipeline.add_rule("完成:", '"节点: " + $((?:完成: )(.+))', "自定义类型")
    pipeline.feed("完成: 邮件")
    assert pipeline.finish() == [log_box.LogEntry("自定义类型", "节点: 邮件", None)]


def test_preprocessing_first_match_and_caller_timestamp():
    pipeline = log_box.LogPipeline()
    pipeline.preprocessors.append(
        lambda line: None if "心跳" in line else line.replace("OK:", "完成:")
    )
    pipeline.add_rule("完成:", '"节点: " + $((?:完成: )(.+))', "普通")
    pipeline.add_rule("完成:", '"重复规则不得命中"', "普通")
    pipeline.feed("心跳", timestamp=1.0)
    pipeline.feed("OK: 邮件", timestamp=2.0)
    pipeline.feed("无关内容", timestamp=3.0)
    assert pipeline.finish() == [log_box.LogEntry("普通", "节点: 邮件", 2.0)]


def test_postprocessing_runs_once_and_result_list_cannot_mutate_cached_result():
    calls = []
    pipeline = log_box.LogPipeline()
    pipeline.add_rule(".+", "", "普通")
    pipeline.feed("甲", timestamp=1.0)
    pipeline.feed("乙", timestamp=2.0)

    def reverse(entries):
        calls.append(tuple(entries))
        return list(reversed(entries))

    pipeline.postprocessors.append(reverse)
    result = pipeline.finish()
    assert [entry.text for entry in result] == ["乙", "甲"]
    result.clear()
    assert len(pipeline.finish()) == 2
    assert len(calls) == 1
    with pytest.raises(RuntimeError):
        pipeline.feed("结束后的文本")


@pytest.mark.parametrize("rule", [("[", ""), ("valid", "$(invalid")])
def test_invalid_rules_raise_without_hidden_fallback(rule):
    pipeline = log_box.LogPipeline()
    with pytest.raises((ValueError, ExpressionError)):
        pipeline.add_rule(*rule, "普通")


@pytest.mark.parametrize("phase", ["pre", "post"])
def test_processor_errors_are_owned_by_caller(phase):
    def fail(value):
        raise RuntimeError("caller processor")

    pipeline = log_box.LogPipeline()
    pipeline.add_rule(".+", "", "普通")
    if phase == "pre":
        pipeline.preprocessors.append(fail)
        with pytest.raises(RuntimeError, match="caller processor"):
            pipeline.feed("文本")
    else:
        pipeline.feed("文本")
        pipeline.postprocessors.append(fail)
        with pytest.raises(RuntimeError, match="caller processor"):
            pipeline.finish()


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), True, "time"])
def test_returned_metadata_is_validated(timestamp):
    pipeline = log_box.LogPipeline()
    pipeline.add_rule(".+", "", "普通")
    pipeline.feed("文本", timestamp=timestamp)
    with pytest.raises(ValueError):
        pipeline.finish()


def test_multiline_flush_preserves_caller_metadata_and_instance_isolation():
    pipeline = log_box.LogPipeline()
    pipeline.scope_rules.append(
        MultiLineAggregator(start_re=re.compile("^BEGIN$"), end_re=None)
    )
    pipeline.feed("BEGIN", timestamp=1.0)
    pipeline.feed("内容", timestamp=2.0)
    assert pipeline.finish() == [log_box.LogEntry("普通", "BEGIN\n内容", 2.0)]
    assert log_box.LogPipeline().finish() == []


@pytest.mark.parametrize(
    "item", ["ab", ("普通",), ("普通", "文本", 1.0, "多余字段"), ["普通", "文本"]]
)
def test_processor_cannot_return_malformed_records(item):
    pipeline = log_box.LogPipeline()
    pipeline.postprocessors.append(lambda entries: [item])
    with pytest.raises(TypeError):
        pipeline.finish()
