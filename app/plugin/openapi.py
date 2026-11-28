"""将当前插件声明的配置契约合入宿主 OpenAPI，类型来自实际配置模型。"""

from collections.abc import Iterable
from typing import Literal

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.config import ConfigEntry
from app.config.wire import config_contract
from app.plugin.base.game import GameAdapterPlugin, GameTypeDecl
from app.plugin.base.script import ScriptAdapterPlugin, ScriptTypeDecl


def extend_game_contracts(
    document: dict, declarations: Iterable[tuple[str, GameTypeDecl]]
) -> dict:
    """游戏及嵌套设备从已启用插件的真实配置生成契约。"""
    schemas = document["components"]["schemas"]
    if "GameGetOut" not in schemas:
        return document
    choices = []
    inputs = []
    device_inputs = []
    keys = []
    for key, declaration in declarations:
        keys.append(key)
        projections: tuple[
            tuple[type[ConfigEntry], Literal["input", "output"], list[dict[str, str]]],
            ...,
        ] = (
            (declaration.game_class, "output", choices),
            (declaration.game_class, "input", inputs),
            (declaration.device_class, "input", device_inputs),
        )
        for entry_type, mode, destination in projections:
            contract = config_contract(
                entry_type,
                mode=mode,
                include_collections=mode == "output",
                extra="forbid" if mode == "input" else "ignore",
            )
            schema = contract.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            schemas.update(schema.pop("$defs", {}))
            schemas[contract.__name__] = schema
            destination.append({"$ref": f"#/components/schemas/{contract.__name__}"})
    if choices:
        schemas["GameGetOut"]["properties"]["data"]["additionalProperties"] = {
            "anyOf": choices
        }
        schemas["GameCreateIn"]["properties"]["type"]["enum"] = keys
        schemas["GameCreateIn"]["properties"]["data"] = {"anyOf": inputs}
        schemas["GameUpdateIn"]["properties"]["data"] = {"anyOf": inputs}
        schemas["GameDeviceUpdateIn"]["properties"]["data"] = {"anyOf": device_inputs}
    return document


def extend_script_contracts(
    document: dict, declarations: Iterable[tuple[str, ScriptTypeDecl]]
) -> dict:
    """补入插件配置、输入投影与公共 CRUD 类型选项，生成端和运行端使用同一份声明。"""
    schemas = document["components"]["schemas"]
    bindings = {
        "script": [
            ("ScriptCreateOut", "data"),
            ("ScriptGetOut", "data", "additionalProperties"),
        ],
        "user": [
            ("UserCreateOut", "data"),
            ("UserGetOut", "data", "additionalProperties"),
        ],
        "plan": [("PlanConfigData",)],
    }

    def add_option(model, field, value):
        """向公开标识字段补入当前插件声明的取值，保留原有内置枚举顺序。"""
        values = schemas[model]["properties"][field].setdefault("enum", [])
        if value not in values:
            values.append(value)

    def add_contract(entry_type, kind):
        """从配置类生成输入、输出及嵌套组 schema，并加入对应公共响应联合。"""
        for mode in ("output", "input"):
            contract = config_contract(
                entry_type,
                mode=mode,
                extra="forbid" if kind == "plan" and mode == "input" else "ignore",
            )
            schema = contract.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            schemas.update(schema.pop("$defs", {}))
            schemas[contract.__name__] = schema
            targets = (
                bindings[kind]
                if mode == "output"
                else [("PlanConfigDataInput",)]
                if kind == "plan"
                else [
                    ("ScriptUpdateIn" if kind == "script" else "UserUpdateIn", "data")
                ]
            )
            for target in targets:
                slot = schemas[target[0]]
                if len(target) > 1:
                    slot = slot["properties"][target[1]]
                if len(target) > 2:
                    slot = slot[target[2]]
                choices = slot["anyOf"]
                choices[:] = [
                    item
                    for item in choices
                    if item != {"$ref": "#/components/schemas/BaseModel"}
                ]
                ref = {"$ref": f"#/components/schemas/{contract.__name__}"}
                if ref not in choices:
                    choices.append(ref)

    for key, decl in declarations:
        add_option("ScriptCreateIn", "type", key)
        add_option("ScriptIndexItem", "type", decl.script_type.__name__)
        add_option("UserIndexItem", "type", decl.user_type.__name__)
        add_contract(decl.script_type, "script")
        add_contract(decl.user_type, "user")
        if decl.plan_type is not None:
            add_contract(decl.plan_type, "plan")
            add_option("PlanIndexItem", "type", decl.plan_type.__name__)
            add_option("PlanCreateIn", "type", decl.plan_type.__name__)
    return document


def bind_openapi(app: FastAPI) -> None:
    """为宿主安装按当前启用声明生成的 OpenAPI，插件装卸会清除原有缓存。"""

    def openapi():
        """生成宿主端点与已启用插件的同源契约，缓存到下次插件装卸为止。"""
        from app.core.plugin import Plugin

        if app.openapi_schema is None:
            document = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
            schemas = document.get("components", {}).get("schemas", {})
            if "DeclarativeConfigUi" in schemas:
                variants = schemas["DeclarativeConfigUi"]["properties"]["blocks"][
                    "anyOf"
                ]
                blocks = next(
                    variant for variant in variants if variant["type"] == "array"
                )
                # TypeScript 生成器只识别数组项的引用和枚举，不解析内联 oneOf 与 const。
                union = blocks["items"]
                schemas["ConfigBlockOut"] = union
                blocks["items"] = {"$ref": "#/components/schemas/ConfigBlockOut"}
                for ref in union["discriminator"]["mapping"].values():
                    kind = schemas[ref.rsplit("/", 1)[-1]]["properties"]["kind"]
                    kind["enum"] = [kind.pop("const")]
            declarations = [
                (record._plugin_cls.script_type_key, Plugin.script_types[record.uid])
                for record in Plugin.list_plugins()
                if record.uid in Plugin.script_types
                and record._plugin_cls is not None
                and issubclass(record._plugin_cls, ScriptAdapterPlugin)
            ]
            document = extend_script_contracts(document, declarations)
            game_declarations = [
                (record._plugin_cls.game_type_key, Plugin.game_types[record.uid])
                for record in Plugin.list_plugins()
                if record.uid in Plugin.game_types
                and record._plugin_cls is not None
                and issubclass(record._plugin_cls, GameAdapterPlugin)
            ]
            app.openapi_schema = extend_game_contracts(document, game_declarations)
        return app.openapi_schema

    app.openapi = openapi
