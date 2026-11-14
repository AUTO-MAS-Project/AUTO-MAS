"""市场、安装包及源码发现统一读取 README 多语言声明。"""

import importlib.metadata
import json

import pytest
from packaging.requirements import Requirement
from pyproject_metadata import StandardMetadata

from app.plugin.runtime.discover import (
    _parse_installed_package,
    _parse_source_package,
)
from app.plugin.runtime.metadata import parse_to_plugin_meta, parse_to_plugin_record


@pytest.fixture
def plugin_metadata_source(tmp_path):
    """创建不允许导入执行的插件及其真实构建元数据，所有入口只读取声明。"""
    display = {
        "display_name_i18n": {"zh_CN": "示例专项", "en": "Demo Adapter"},
        "description_i18n": {"zh_CN": "示例适配插件", "en": "Demo script adapter"},
        "tags_i18n": {"zh_CN": ["专项适配"], "en": ["Adapter"]},
    }
    readme = (
        "<!-- auto-mas:i18n\n"
        + json.dumps(display, ensure_ascii=False)
        + "\n-->\n\n# Demo\n\nPlugin documentation.\n"
    )
    project = {
        "name": "auto-mas-demo",
        "version": "0.1.0",
        "description": "Demo script adapter",
        "readme": {"file": "README.md", "content-type": "text/markdown"},
        "keywords": ["auto-mas-plugin", "auto-mas-id:demo_adapter", "adapter"],
        "dependencies": ["auto-mas-core>=5.8,<5.9"],
        "authors": [{"name": "Demo Team"}],
        "license": "AGPL-3.0-or-later",
        "urls": {
            "Home page": "https://example.org/demo",
            "DOCUMENTATION": "https://example.org/docs",
            "Source Code": "https://example.org/source",
        },
    }
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    source = tmp_path / "plugin"
    package = source / "src/demo_adapter"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        'raise RuntimeError("Metadata discovery must not execute plugin code")\n',
        encoding="utf-8",
    )
    (source / "README.md").write_text(readme, encoding="utf-8")
    import tomli_w

    (source / "pyproject.toml").write_text(
        tomli_w.dumps({"project": project}), encoding="utf-8"
    )
    return project, readme, display, source


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["pypi", "installed", "local"])
async def test_readme_i18n_matches_across_discovery_sources(
    plugin_metadata_source, tmp_path, origin
):
    """使用实际源码及发行版发现入口，保证尚未安装时也能显示相同的多语言信息。"""
    project, readme, display, source = plugin_metadata_source
    if origin == "pypi":
        item = parse_to_plugin_meta(
            {
                "info": {
                    "name": project["name"],
                    "version": project["version"],
                    "summary": project["description"],
                    "description": readme,
                    "keywords": ",".join(project["keywords"]),
                    "project_urls": project["urls"],
                    "requires_dist": project["dependencies"],
                    "author": "Demo Team",
                    "license_expression": project["license"],
                }
            }
        )
    elif origin == "local":
        item = await _parse_source_package(source)
    else:
        installed = tmp_path / "site"
        dist_info = installed / "auto_mas_demo-0.1.0.dist-info"
        dist_info.mkdir(parents=True)
        package = installed / "demo_adapter"
        package.mkdir()
        (package / "__init__.py").write_text(
            'raise RuntimeError("Do not import during discovery")\n', encoding="utf-8"
        )
        message = StandardMetadata.from_pyproject(
            {"project": project}, project_dir=source
        ).as_rfc822()
        (dist_info / "METADATA").write_text(message.as_string(), encoding="utf-8")
        (dist_info / "RECORD").write_text(
            "demo_adapter/__init__.py,,\n"
            "auto_mas_demo-0.1.0.dist-info/METADATA,,\n"
            "auto_mas_demo-0.1.0.dist-info/RECORD,,\n",
            encoding="utf-8",
        )
        dist = next(iter(importlib.metadata.distributions(path=[str(installed)])))
        item = await _parse_installed_package(dist)
    assert item is not None
    assert item.info.package_name == "auto-mas-demo"
    assert item.info.plugin_name == "demo_adapter"
    assert item.info.version == "0.1.0"
    assert item.info.homepage == "https://example.org/demo"
    assert item.info.docs_url == "https://example.org/docs"
    assert item.info.repository == "https://example.org/source"
    assert item.info.author == "Demo Team"
    assert item.info.license == "AGPL-3.0-or-later"
    assert [str(Requirement(value)) for value in item.info.requires_dist] == [
        "auto-mas-core<5.9,>=5.8"
    ]
    for field, expected in display.items():
        assert getattr(item.info, field) == expected


@pytest.mark.parametrize(
    "readme",
    [
        "# Plugin without listing translations",
        "<!-- auto-mas:i18n\n{invalid json}\n-->",
        '<!-- auto-mas:i18n\n{"display_name_i18n": {"en": "Demo"}}\n-->',
        '<!-- auto-mas:i18n\n{"display_name_i18n": [], '
        '"description_i18n": {"en": "Demo"}, "tags_i18n": {"en": ["Adapter"]}}\n-->',
    ],
)
def test_invalid_readme_is_excluded_from_market_without_hiding_installed_plugin(readme):
    """不完整或损坏的市场声明不能入目录，安装记录仍保留标准元数据与身份。"""
    metadata = {
        "name": "auto-mas-demo",
        "version": "0.1.0",
        "summary": "Demo script adapter",
        "description": readme,
        "keywords": ["auto-mas-plugin", "auto-mas-id:demo_adapter"],
    }
    assert parse_to_plugin_meta(metadata) is None
    record = parse_to_plugin_record(
        metadata, import_name="demo_adapter", source="installed"
    )
    assert record is not None
    assert record.info.display_name_i18n == {"en": "demo_adapter"}
    assert record.info.description_i18n == {"en": "Demo script adapter"}
    assert record.info.tags_i18n == {}
