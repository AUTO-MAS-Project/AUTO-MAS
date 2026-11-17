"""插件声明只读：兼容原生文件名且不执行第三方代码。"""

import pytest

from app.task.ZzzOd.tools.catalog import list_app_catalog


def test_plugin_catalog_reads_native_metadata_without_executing_plugins(tmp_path):
    (tmp_path / "src/zzz_od/application").mkdir(parents=True)
    for directory, prefix, priority in [
        ("graphics_low", "", 50),
        ("legacy", "legacy_", 2900),
    ]:
        plugin = tmp_path / "plugins" / directory
        plugin.mkdir(parents=True)
        (plugin / f"{prefix}const.py").write_text(
            f'APP_ID = "{directory}"\nAPP_NAME = "中文名称"\nDEFAULT_GROUP = True\n',
            encoding="utf-8",
        )
        # 执行任一声明文件都应失败；排序只读取构造函数内的直接字面量。
        with (plugin / f"{prefix}const.py").open("a", encoding="utf-8") as stream:
            stream.write('raise RuntimeError("must not execute")\n')
        (plugin / f"{prefix}factory.py").write_text(
            'raise RuntimeError("must not execute")\n'
            "class PluginFactory(ApplicationFactory):\n"
            "    def __init__(self):\n"
            f"        self.priority: int | None = {priority}\n",
            encoding="utf-8",
        )
    catalog = list_app_catalog(tmp_path)
    assert [
        (item["app_id"], item["app_name"], item["priority"]) for item in catalog
    ] == [
        ("graphics_low", "中文名称", 50),
        ("legacy", "中文名称", 2900),
    ]
    assert all(item["is_plugin"] and item["default_group"] for item in catalog)


@pytest.mark.parametrize("expression, expected", [("-OFFSET", 75), ("-50", -50)])
def test_optional_factory_priority_preserves_plugin_metadata(
    tmp_path, expression, expected
):
    (tmp_path / "src/zzz_od/application").mkdir(parents=True)
    plugin = tmp_path / "plugins/example"
    plugin.mkdir(parents=True)
    (plugin / "const.py").write_text(
        'APP_ID="example"\nAPP_NAME="示例插件"\nDEFAULT_GROUP=True\nPRIORITY=75\n',
        encoding="utf-8",
    )
    (plugin / "factory.py").write_text(
        "from . import const\n"
        "OFFSET=50\n"
        "class Example(ApplicationFactory):\n"
        "    def __init__(self):\n"
        "        super().__init__(const)\n"
        f"        self.priority = {expression}\n",
        encoding="utf-8",
    )
    catalog = list_app_catalog(tmp_path)
    assert [
        (item["app_id"], item["app_name"], item["priority"]) for item in catalog
    ] == [("example", "示例插件", expected)]
