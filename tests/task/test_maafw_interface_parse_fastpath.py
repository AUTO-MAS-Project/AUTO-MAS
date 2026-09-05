import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.core  # noqa: F401
from app.task.MaaFW.tools.core.automas_maafw_interface import loader as loader_module
from app.task.MaaFW.tools.core.automas_maafw_interface.loader import parse_json_text


class ParseJsonTextTest(unittest.TestCase):
    """先严格 JSON、失败再 JSON5。

    json5 是纯 Python 递归下降解析器，比 C 实现的 json 慢三个数量级——MaaEnd
    那份 108KB 的 zh_cn.json，json.loads 0.3ms，json5.loads 392ms。整个
    interface 要合并四十多个文件，差距就是 4.8 秒和零点几秒。快路径不能以牺牲
    JSON5 兼容为代价，这组用例守的就是这一点。
    """

    def test_strict_json_takes_the_fast_path(self) -> None:
        with patch.object(loader_module.json5, "loads") as json5_loads:
            self.assertEqual(
                parse_json_text('{"a": [1, 2], "b": null}'), {"a": [1, 2], "b": None}
            )
        # 严格 JSON 不得落到 json5——那正是要绕开的慢路径。
        json5_loads.assert_not_called()

    def test_comments_still_parse(self) -> None:
        text = """{
            // 行注释
            "a": 1, /* 块注释 */
            "b": 2,
        }"""
        self.assertEqual(parse_json_text(text), {"a": 1, "b": 2})

    def test_trailing_comma_and_unquoted_key_still_parse(self) -> None:
        self.assertEqual(
            parse_json_text("{ a: 1, b: [2, 3,], }"), {"a": 1, "b": [2, 3]}
        )

    def test_single_quotes_still_parse(self) -> None:
        self.assertEqual(parse_json_text("{'a': 'x'}"), {"a": "x"})

    def test_both_parsers_agree_on_strict_json(self) -> None:
        payload = {
            "name": "MaaEnd",
            "task": [{"name": "打开游戏", "entry": "启动游戏", "option": ["a"]}],
            "nested": {"深": {"层": [1, 2.5, True, None, "中文"]}},
        }
        text = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(parse_json_text(text), payload)
        self.assertEqual(loader_module.json5.loads(text), payload)

    def test_broken_input_still_raises(self) -> None:
        # 两个解析器都失败时不能静默吞掉——上层要靠异常报「解析 interface 失败」。
        with self.assertRaises(Exception):
            parse_json_text("{ not json at all ")


class ReadJsonDictUsesFastPathTest(unittest.TestCase):
    """真实文件读取也要走快路径，且行为与旧实现一致。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)

    def test_reads_strict_json_without_json5(self) -> None:
        path = self.root / "interface.json"
        path.write_text(json.dumps({"name": "x", "task": []}), encoding="utf-8")
        with patch.object(loader_module.json5, "loads") as json5_loads:
            data = loader_module._read_json_dict(path)
        self.assertEqual(data, {"name": "x", "task": []})
        json5_loads.assert_not_called()

    def test_reads_json5_file(self) -> None:
        path = self.root / "interface.json"
        path.write_text('{ /* c */ name: "x", task: [], }', encoding="utf-8")
        self.assertEqual(loader_module._read_json_dict(path), {"name": "x", "task": []})

    def test_missing_file_message_is_unchanged(self) -> None:
        with self.assertRaises(loader_module.MaaFWInterfaceLoadError) as ctx:
            loader_module._read_json_dict(self.root / "nope.json")
        self.assertIn("找不到 interface 配置文件", str(ctx.exception))

    def test_non_object_root_is_rejected(self) -> None:
        path = self.root / "interface.json"
        path.write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(loader_module.MaaFWInterfaceLoadError) as ctx:
            loader_module._read_json_dict(path)
        self.assertIn("必须是 JSON 对象", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
