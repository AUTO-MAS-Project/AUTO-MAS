#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import json
import uuid
import win32com.client
from copy import deepcopy
from pathlib import Path
from typing import List, Any, Dict, Union, Optional


from app.utils import dpapi_encrypt, dpapi_decrypt
from app.utils.constants import RESERVED_NAMES, ILLEGAL_CHARS


class ConfigValidator:
    """基础配置验证器"""

    def validate(self, value: Any) -> bool:
        """验证值是否合法"""
        return True

    def correct(self, value: Any) -> Any:
        """修正非法值"""
        return value


class RangeValidator(ConfigValidator):
    """范围验证器"""

    def __init__(self, min: int | float, max: int | float):
        self.min = min
        self.max = max
        self.range = (min, max)

    def validate(self, value: Any) -> bool:
        if not isinstance(value, (int | float)):
            return False
        return self.min <= value <= self.max

    def correct(self, value: Any) -> int | float:
        if not isinstance(value, (int, float)):
            try:
                value = float(value)
            except TypeError:
                return self.min
        return min(max(self.min, value), self.max)


class OptionsValidator(ConfigValidator):
    """选项验证器"""

    def __init__(self, options: list):
        if not options:
            raise ValueError("可选项不能为空")

        self.options = options

    def validate(self, value: Any) -> bool:
        return value in self.options

    def correct(self, value: Any) -> Any:
        return value if self.validate(value) else self.options[0]


class UidValidator(ConfigValidator):
    """UID验证器"""

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        try:
            uuid.UUID(value)
            return True
        except (TypeError, ValueError):
            return False

    def correct(self, value: Any) -> Any:
        return value if self.validate(value) else None


class UUIDValidator(ConfigValidator):
    """UUID验证器"""

    def validate(self, value: Any) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (TypeError, ValueError):
            return False

    def correct(self, value: Any) -> Any:
        return value if self.validate(value) else str(uuid.uuid4())


class EncryptValidator(ConfigValidator):
    """加密数据验证器"""

    def validate(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            dpapi_decrypt(value)
            return True
        except:
            return False

    def correct(self, value: Any) -> Any:
        return value if self.validate(value) else dpapi_encrypt("数据损坏, 请重新设置")


class BoolValidator(OptionsValidator):
    """布尔值验证器"""

    def __init__(self):
        super().__init__([True, False])


class FileValidator(ConfigValidator):
    """文件路径验证器"""

    def validate(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        if not Path(value).is_absolute():
            return False
        if Path(value).suffix == ".lnk":
            return False
        return True

    def correct(self, value: Any) -> str:
        if not isinstance(value, str):
            value = str(Path.cwd())
        if not Path(value).is_absolute():
            value = Path(value).resolve().as_posix()
        if Path(value).suffix == ".lnk":
            try:
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortcut(value)
                value = shortcut.TargetPath
            except:
                pass
        return Path(value).resolve().as_posix()


class FolderValidator(ConfigValidator):
    """文件夹路径验证器"""

    def validate(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        if not Path(value).is_absolute():
            return False
        return True

    def correct(self, value: Any) -> str:
        if not isinstance(value, str):
            value = str(Path.cwd())
        return Path(value).resolve().as_posix()


class UserNameValidator(ConfigValidator):
    """用户名验证器"""

    def validate(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False

        if not value or not value.strip():
            return False

        if value != value.strip() or value != value.strip("."):
            return False

        if any(char in ILLEGAL_CHARS for char in value):
            return False

        if value.upper() in RESERVED_NAMES:
            return False
        if len(value) > 255:
            return False

        return True

    def correct(self, value: Any) -> str:
        if not isinstance(value, str):
            value = "默认用户名"

        value = value.strip().strip(".")

        value = "".join(char for char in value if char not in ILLEGAL_CHARS)

        if value.upper() in RESERVED_NAMES or not value:
            value = "默认用户名"

        if len(value) > 255:
            value = value[:255]

        return value


class ConfigItem:
    """配置项"""

    def __init__(
        self,
        group: str,
        name: str,
        default: Any,
        validator: Optional[ConfigValidator] = None,
    ):
        """
        Parameters
        ----------
        group: str
            配置项分组名称

        name: str
            配置项字段名称

        default: Any
            配置项默认值

        validator: ConfigValidator
            配置项验证器, 默认为 None, 表示不进行验证
        """
        super().__init__()
        self.group = group
        self.name = name
        self.value: Any = default
        self.validator = validator or ConfigValidator()
        self.is_locked = False

        if not self.validator.validate(self.value):
            raise ValueError(
                f"配置项 '{self.group}.{self.name}' 的默认值 '{self.value}' 不合法"
            )

    def setValue(self, value: Any):
        """
        设置配置项值, 将自动进行验证和修正

        Parameters
        ----------
        value: Any
            要设置的值, 可以是任何合法类型
        """

        if (
            dpapi_decrypt(self.value)
            if isinstance(self.validator, EncryptValidator)
            else self.value
        ) == value:
            return

        if self.is_locked:
            raise ValueError(f"配置项 '{self.group}.{self.name}' 已锁定, 无法修改")

        # deepcopy new value
        try:
            self.value = deepcopy(value)
        except:
            self.value = value

        if isinstance(self.validator, EncryptValidator):
            if self.validator.validate(self.value):
                self.value = self.value
            else:
                self.value = dpapi_encrypt(self.value)

        if not self.validator.validate(self.value):
            self.value = self.validator.correct(self.value)

    def getValue(self) -> Any:
        """
        获取配置项值
        """

        if isinstance(self.validator, EncryptValidator):
            return dpapi_decrypt(self.value)
        return self.value

    def lock(self):
        """
        锁定配置项, 锁定后无法修改配置项值
        """
        self.is_locked = True

    def unlock(self):
        """
        解锁配置项, 解锁后可以修改配置项值
        """
        self.is_locked = False


class ConfigBase:
    """
    配置基类

    这个类提供了基本的配置项管理功能, 包括连接配置文件、加载配置数据、获取和设置配置项值等。

    此类不支持直接实例化, 必须通过子类来实现具体的配置项, 请继承此类并在子类中定义具体的配置项。
    若将配置项设为类属性, 则所有实例都会共享同一份配置项数据。
    若将配置项设为实例属性, 则每个实例都会有独立的配置项数据。
    子配置项可以是 `MultipleConfig` 的实例。
    """

    def __init__(self, if_save_multi_config: bool = True):

        self.file: None | Path = None
        self.if_save_multi_config = if_save_multi_config
        self.is_locked = False

    async def connect(self, path: Path):
        """
        将配置文件连接到指定配置文件

        Parameters
        ----------
        path: Path
            配置文件路径, 必须为 JSON 文件, 如果不存在则会创建
        """

        if path.suffix != ".json":
            raise ValueError("配置文件必须是扩展名为 '.json' 的 JSON 文件")

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        self.file = path

        if not self.file.exists():
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.touch()

        with self.file.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}

        await self.load(data)

    async def load(self, data: dict):
        """
        从字典加载配置数据

        这个方法会遍历字典中的配置项, 并将其设置到对应的 ConfigItem 实例中。
        如果字典中包含 "SubConfigsInfo" 键, 则会加载子配置项, 这些子配置项应该是 MultipleConfig 的实例。

        Parameters
        ----------
        data: dict
            配置数据字典
        """

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        # update the value of config item
        if data.get("SubConfigsInfo"):
            for k, v in data["SubConfigsInfo"].items():
                if hasattr(self, k):
                    sub_config = getattr(self, k)
                    if isinstance(sub_config, MultipleConfig):
                        await sub_config.load(v)
            data.pop("SubConfigsInfo")

        for group, info in data.items():
            for name, value in info.items():
                if hasattr(self, f"{group}_{name}"):
                    configItem = getattr(self, f"{group}_{name}")
                    if isinstance(configItem, ConfigItem):
                        configItem.setValue(value)

        if self.file:
            await self.save()

    async def toDict(
        self, ignore_multi_config: bool = False, if_decrypt: bool = True
    ) -> Dict[str, Any]:
        """将配置项转换为字典"""

        data = {}
        for name in dir(self):
            item = getattr(self, name)

            if isinstance(item, ConfigItem):

                if not data.get(item.group):
                    data[item.group] = {}
                if item.name:
                    data[item.group][item.name] = (
                        item.getValue() if if_decrypt else item.value
                    )

            elif not ignore_multi_config and isinstance(item, MultipleConfig):

                if not data.get("SubConfigsInfo"):
                    data["SubConfigsInfo"] = {}
                data["SubConfigsInfo"][name] = await item.toDict()

        return data

    def get(self, group: str, name: str) -> Any:
        """获取配置项的值"""

        if not hasattr(self, f"{group}_{name}"):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        configItem = getattr(self, f"{group}_{name}")
        if isinstance(configItem, ConfigItem):
            return configItem.getValue()
        else:
            raise TypeError(f"配置项 '{group}.{name}' 不是 ConfigItem 实例")

    async def set(self, group: str, name: str, value: Any):
        """
        设置配置项的值

        Parameters
        ----------
        group: str
            配置项分组名称
        name: str
            配置项名称
        value: Any
            配置项新值
        """

        if not hasattr(self, f"{group}_{name}"):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        configItem = getattr(self, f"{group}_{name}")
        if isinstance(configItem, ConfigItem):
            configItem.setValue(value)
            if self.file:
                await self.save()
        else:
            raise TypeError(f"配置项 '{group}.{name}' 不是 ConfigItem 实例")

    async def save(self):
        """保存配置"""

        if not self.file:
            raise ValueError("文件路径未设置, 请先调用 `connect` 方法连接配置文件")

        self.file.parent.mkdir(parents=True, exist_ok=True)
        with self.file.open("w", encoding="utf-8") as f:
            json.dump(
                await self.toDict(not self.if_save_multi_config, if_decrypt=False),
                f,
                ensure_ascii=False,
                indent=4,
            )

    async def lock(self):
        """
        锁定配置项, 锁定后无法修改配置项值
        """

        self.is_locked = True

        for name in dir(self):
            item = getattr(self, name)
            if isinstance(item, ConfigItem):
                item.lock()
            elif isinstance(item, MultipleConfig):
                await item.lock()

    async def unlock(self):
        """
        解锁配置项, 解锁后可以修改配置项值
        """

        self.is_locked = False

        for name in dir(self):
            item = getattr(self, name)
            if isinstance(item, ConfigItem):
                item.unlock()
            elif isinstance(item, MultipleConfig):
                await item.unlock()


class MultipleConfig:
    """
    多配置项管理类

    这个类允许管理多个配置项实例, 可以添加、删除、修改配置项, 并将其保存到 JSON 文件中。
    允许通过 `config[uuid]` 访问配置项, 使用 `uuid in config` 检查是否存在配置项, 使用 `len(config)` 获取配置项数量。

    Parameters
    ----------
    sub_config_type: List[type]
        子配置项的类型列表, 必须是 ConfigBase 的子类
    """

    def __init__(self, sub_config_type: List[type]):

        if not sub_config_type:
            raise ValueError("子配置项类型列表不能为空")

        for config_type in sub_config_type:
            if not issubclass(config_type, ConfigBase):
                raise TypeError(
                    f"配置类型 {config_type.__name__} 必须是 ConfigBase 的子类"
                )

        self.sub_config_type = sub_config_type
        self.file: None | Path = None
        self.order: List[uuid.UUID] = []
        self.data: Dict[uuid.UUID, ConfigBase] = {}
        self.is_locked = False

    def __getitem__(self, key: uuid.UUID) -> ConfigBase:
        """允许通过 config[uuid] 访问配置项"""
        if key not in self.data:
            raise KeyError(f"配置项 '{key}' 不存在")
        return self.data[key]

    def __contains__(self, key: uuid.UUID) -> bool:
        """允许使用 uuid in config 检查是否存在"""
        return key in self.data

    def __len__(self) -> int:
        """允许使用 len(config) 获取配置项数量"""
        return len(self.data)

    def __repr__(self) -> str:
        """更好的字符串表示"""
        return f"MultipleConfig(items={len(self.data)}, types={[t.__name__ for t in self.sub_config_type]})"

    def __str__(self) -> str:
        """用户友好的字符串表示"""
        return f"MultipleConfig with {len(self.data)} items"

    async def connect(self, path: Path):
        """
        将配置文件连接到指定配置文件

        Parameters
        ----------
        path: Path
            配置文件路径, 必须为 JSON 文件, 如果不存在则会创建
        """

        if path.suffix != ".json":
            raise ValueError("配置文件必须是带有 '.json' 扩展名的 JSON 文件。")

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        self.file = path

        if not self.file.exists():
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.touch()

        with self.file.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}

        await self.load(data)

    async def load(self, data: dict):
        """
        从字典加载配置数据

        这个方法会遍历字典中的配置项, 并将其设置到对应的 ConfigBase 实例中。
        如果字典中包含 "instances" 键, 则会加载子配置项, 这些子配置项应该是 ConfigBase 子类的实例。
        如果字典中没有 "instances" 键, 则清空当前配置项。

        Parameters
        ----------
        data: dict
            配置数据字典
        """

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        if not data.get("instances"):
            self.order = []
            self.data = {}
            return

        self.order = []
        self.data = {}

        for instance in data["instances"]:

            if not isinstance(instance, dict) or not data.get(instance.get("uid")):
                continue

            type_name = instance.get("type", self.sub_config_type[0].__name__)

            for class_type in self.sub_config_type:

                if class_type.__name__ == type_name:
                    self.order.append(uuid.UUID(instance["uid"]))
                    self.data[self.order[-1]] = class_type()
                    await self.data[self.order[-1]].load(data[instance["uid"]])
                    break

            else:

                raise ValueError(f"未知的子配置类型: {type_name}")

        if self.file:
            await self.save()

    async def toDict(self) -> Dict[str, Union[list, dict]]:
        """
        将配置项转换为字典

        返回一个字典, 包含所有配置项的 UID 和类型, 以及每个配置项的具体数据。
        """

        data: Dict[str, Union[list, dict]] = {
            "instances": [
                {"uid": str(_), "type": type(self.data[_]).__name__} for _ in self.order
            ]
        }
        for uid, config in self.items():
            data[str(uid)] = await config.toDict()
        return data

    async def get(self, uid: uuid.UUID) -> Dict[str, Union[list, dict]]:
        """
        获取指定 UID 的配置项

        Parameters
        ----------
        uid: uuid.UUID
            要获取的配置项的唯一标识符
        Returns
        -------
        Dict[str, Union[list, dict]]
            对应的配置项数据字典
        """

        if uid not in self.data:
            raise ValueError(f"配置项 '{uid}' 不存在。")

        data: Dict[str, Union[list, dict]] = {
            "instances": [
                {"uid": str(_), "type": type(self.data[_]).__name__}
                for _ in self.order
                if _ == uid
            ]
        }
        data[str(uid)] = await self.data[uid].toDict()

        return data

    async def save(self):
        """保存配置"""

        if not self.file:
            raise ValueError("文件路径未设置, 请先调用 `connect` 方法连接配置文件")

        self.file.parent.mkdir(parents=True, exist_ok=True)
        with self.file.open("w", encoding="utf-8") as f:
            json.dump(await self.toDict(), f, ensure_ascii=False, indent=4)

    async def add(self, config_type: type) -> tuple[uuid.UUID, ConfigBase]:
        """
        添加一个新的配置项

        Parameters
        ----------
        config_type: type
            配置项的类型, 必须是初始化时已声明的 ConfigBase 子类

        Returns
        -------
        tuple[uuid.UUID, ConfigBase]
            新创建的配置项的唯一标识符和实例
        """

        if config_type not in self.sub_config_type:
            raise ValueError(f"配置类型 {config_type.__name__} 不被允许")

        uid = uuid.uuid4()
        self.order.append(uid)
        self.data[uid] = config_type()

        if self.file:
            await self.save()

        return uid, self.data[uid]

    async def remove(self, uid: uuid.UUID):
        """
        移除配置项

        Parameters
        ----------
        uid: uuid.UUID
            要移除的配置项的唯一标识符
        """

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        if uid not in self.data:
            raise ValueError(f"配置项 '{uid}' 不存在")

        if self.data[uid].is_locked:
            raise ValueError(f"配置项 '{uid}' 已锁定, 无法移除")

        self.data.pop(uid)
        self.order.remove(uid)

        if self.file:
            await self.save()

    async def setOrder(self, order: List[uuid.UUID]):
        """
        设置配置项的顺序

        Parameters
        ----------
        order: List[uuid.UUID]
            新的配置项顺序
        """

        if set(order) != set(self.data.keys()):
            raise ValueError("顺序与当前配置项不匹配")

        self.order = order

        if self.file:
            await self.save()

    async def lock(self):
        """
        锁定配置项, 锁定后无法修改配置项值
        """

        self.is_locked = True

        for item in self.values():
            await item.lock()

    async def unlock(self):
        """
        解锁配置项, 解锁后可以修改配置项值
        """

        self.is_locked = False

        for item in self.values():
            await item.unlock()

    def keys(self):
        """返回配置项的所有唯一标识符"""

        return iter(self.order)

    def values(self):
        """返回配置项的所有实例"""

        if not self.data:
            return iter([])

        return iter([self.data[_] for _ in self.order])

    def items(self):
        """返回配置项的所有唯一标识符和实例的元组"""

        return zip(self.keys(), self.values())
