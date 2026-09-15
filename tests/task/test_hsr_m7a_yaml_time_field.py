"""HSR：M7A config.yaml 里未加引号的 ``HH:MM`` 必须按字符串读取。"""

from app.task.HSR.tools import m7a_config as m7a


def test_unquoted_time_stays_string():
    """PyYAML 默认把 ``4:00`` 按六十进制读成 240，M7A 拿到整数会崩。"""
    assert m7a.load_m7a_yaml("scheduled_time: 4:00\n") == {"scheduled_time": "4:00"}
    assert m7a.load_m7a_yaml("t: 23:59:59\n") == {"t": "23:59:59"}


def test_other_integer_forms_still_parse():
    assert m7a.load_m7a_yaml("a: 42\nb: -7\nc: 0x1F\nd: 1_000\ne: 010\n") == {
        "a": 42,
        "b": -7,
        "c": 31,
        "d": 1000,
        "e": 8,
    }


def test_empty_document_returns_empty_dict():
    assert m7a.load_m7a_yaml("") == {}
