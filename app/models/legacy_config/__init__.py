"""仅供 v1.8 历史升级使用的 JSON 容器；运行期不导入此模块。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from app.models.legacy_config.base import (
    ConfigBase,
    ConfigItem,
    DateTimeValidator,
    MultipleConfig,
    ValidatorBase,
)
from app.utils import io as _utils_io


class _LegacyValueValidator(ValidatorBase):
    """原样保留历史字段和密文，由 JSON→YAML 转换统一完成新字段校验。"""

    def validate(self, value: Any) -> bool:
        return True

    def correct(self, value: Any) -> Any:
        return value


class LegacyConfig(ConfigBase):
    """按历史载荷声明字段，复用旧 load、父级保存回调及同步落盘。"""

    async def connect(self, path: Path) -> None:
        # 旧 connect 对损坏 JSON 会回退默认值；升级必须先严格读取，禁止覆盖。
        _utils_io.read_dict_file(path)
        if not path.exists():
            # 先原子创建有效 JSON，避免旧 connect.touch 留下不可重试的空白文件。
            self.file = path
            await self.save()
        await super().connect(path)
        await self.save()

    async def load(self, data: dict) -> bool:
        if not isinstance(data, dict):
            raise ValueError("历史配置必须为映射")
        fields: dict[str, dict[str, ConfigItem]] = {}
        for group, values in data.items():
            if group == "SubConfigsInfo":
                continue
            if not isinstance(values, dict):
                raise ValueError(f"历史配置分组必须为映射：{group}")
            fields[group] = {}
            for name, value in values.items():
                validator: ValidatorBase = _LegacyValueValidator()
                if (type(self).__name__, group, name) == ("TimeSet", "Info", "Time"):
                    validator = DateTimeValidator("%H:%M")
                fields[group][name] = ConfigItem(
                    group=group,
                    name=name,
                    default=deepcopy(validator.correct(value)),
                    validator=validator,
                )
        subconfigs = data.get("SubConfigsInfo", {})
        if not isinstance(subconfigs, dict):
            raise ValueError("历史嵌套配置必须为映射")
        self._has_subconfigs = "SubConfigsInfo" in data
        self._config_item_index = fields
        self._multiple_config_index = {name: LegacyCollection() for name in subconfigs}
        changed = await super().load(data)
        # 重建的嵌套集合必须继续沿旧链路保存到聚合 JSON，不能只保留内存。
        for collection in self._multiple_config_index.values():
            for save_method in self._save_methods:
                await collection.add_save_method(save_method)
            if self.file is not None:
                await collection.add_save_method(self.save)
        return changed

    async def toDict(
        self, if_decrypt: bool = True, regenerate_uuids: bool = False
    ) -> dict[str, Any]:
        data = await super().toDict(
            if_decrypt=if_decrypt, regenerate_uuids=regenerate_uuids
        )
        for group in self._config_item_index:
            data.setdefault(group, {})
        if getattr(self, "_has_subconfigs", False):
            data.setdefault("SubConfigsInfo", {})
        return data

    async def get_collection(self, name: str) -> LegacyCollection:
        """取得历史嵌套集合；首次创建时接入父级保存链。"""
        if name not in self._multiple_config_index:
            collection = LegacyCollection()
            for save_method in self._save_methods:
                await collection.add_save_method(save_method)
            if self.file is not None:
                await collection.add_save_method(self.save)
            self._multiple_config_index[name] = collection
        return cast(LegacyCollection, self._multiple_config_index[name])


class LegacyCollection(MultipleConfig[LegacyConfig]):
    """保留历史类型名及 UUID，成员只负责承接 JSON，不复制业务字段表。"""

    def __init__(self) -> None:
        super().__init__([LegacyConfig])

    async def connect(self, path: Path) -> None:
        _utils_io.read_dict_file(path)
        if not path.exists():
            self.file = path
            await self.save()
        await super().connect(path)
        await self.save()

    async def load(self, data: dict) -> bool:
        if not isinstance(data, dict) or not isinstance(
            data.get("instances", []), list
        ):
            raise ValueError("历史集合索引无效")
        if data and "instances" not in data:
            raise ValueError("历史集合索引缺失")
        seen: set[UUID] = set()
        document = deepcopy(data)
        for item in data.get("instances", []):
            if not isinstance(item, dict):
                raise ValueError("历史集合索引项无效")
            uid = UUID(item["uid"])
            name = item["type"]
            if uid in seen or not isinstance(data.get(str(uid)), dict):
                raise ValueError("历史集合成员缺失或身份重复")
            if not isinstance(name, str) or not name:
                raise ValueError("历史集合类型名无效")
            seen.add(uid)
            # 旧 load 跳过空 dict；用原生的空嵌套块承接默认配置，保留其 UUID。
            if not document[str(uid)]:
                document[str(uid)] = {"SubConfigsInfo": {}}
            if name not in self.sub_config_type:
                # 旧 MultipleConfig 根据类名序列化类型；只创建无业务字段的临时类型。
                self.sub_config_type[name] = type(name, (LegacyConfig,), {})
        return await super().load(document)

    async def put(
        self, *, uid: UUID, type_name: str, payload: dict[str, Any]
    ) -> LegacyConfig:
        """按稳定身份写入并等待旧保存链完成，重试不重复创建成员。"""
        document = await self.toDict(if_decrypt=False)
        index = document["instances"]
        if uid in self:
            if type(self[uid]).__name__ != type_name:
                raise ValueError(f"历史迁移成员类型冲突：{uid}")
        else:
            cast(list, index).append({"uid": str(uid), "type": type_name})
        document[str(uid)] = payload
        # load 的 dirty 比较针对输入文档；新成员与载荷完全同形时仍须提交写入。
        if not await self.load(document):
            await self._commit_changes()
        return self[uid]
