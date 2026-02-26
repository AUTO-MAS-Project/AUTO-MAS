#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from __future__ import annotations
import os
import json
import uuid
import shlex
import asyncio
import win32com.client
from copy import deepcopy
from urllib.parse import urlparse
from datetime import datetime
from contextlib import suppress
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Type, TypeVar, Generic, Callable, Coroutine


from app.utils import dpapi_encrypt, dpapi_decrypt
from app.utils.constants import RESERVED_NAMES, ILLEGAL_CHARS, DEFAULT_DATETIME


class ValidatorBase(ABC):
    """基础配置验证器"""

    @abstractmethod
    def validate(self, value: Any) -> bool:
        """验证值是否合法"""
        pass

    @abstractmethod
    def correct(self, value: Any) -> Any:
        """修正非法值"""
        pass


class StringValidator(ValidatorBase):
    """字符串验证器"""

    def validate(self, value):
        return isinstance(value, str)

    def correct(self, value):
        return value if self.validate(value) else ""


class RangeValidator(ValidatorBase):
    """范围验证器"""

    def __init__(self, min: int | float, max: int | float):
        self.min = min
        self.max = max
        self.range = (min, max)

    def validate(self, value):
        if not isinstance(value, (int, float)):
            return False
        return self.min <= value <= self.max

    def correct(self, value):
        if not isinstance(value, (int, float)):
            try:
                value = float(value)
            except TypeError:
                return self.min
        return min(max(self.min, value), self.max)


class OptionsValidator(ValidatorBase):
    """选项验证器"""

    def __init__(self, options: list):
        if not options:
            raise ValueError("可选项不能为空")

        self.options = options

    def validate(self, value):
        return value in self.options

    def correct(self, value):
        return value if self.validate(value) else self.options[0]


class MultipleOptionsValidator(ValidatorBase):
    """多选选项验证器"""

    def __init__(self, options: list):
        if not options:
            raise ValueError("可选项不能为空")

        self.options = options

    def validate(self, value):
        if not isinstance(value, list):
            return False

        return all(item in self.options for item in value)

    def correct(self, value):
        return value if self.validate(value) else []


class UUIDValidator(ValidatorBase):
    """UUID验证器"""

    def validate(self, value):
        try:
            uuid.UUID(value)
            return True
        except (TypeError, ValueError):
            return False

    def correct(self, value):
        return value if self.validate(value) else str(uuid.uuid4())


class MultipleUIDValidator(ValidatorBase):
    """多配置管理类UID验证器"""

    def __init__(
        self, default: Any, related_config: dict[str, MultipleConfig], config_name: str
    ):
        self.default = default
        self.related_config = related_config
        self.config_name = config_name

    def validate(self, value):
        if value == self.default:
            return True
        if not isinstance(value, str):
            return False
        try:
            uid = uuid.UUID(value)
        except (TypeError, ValueError):
            return False
        if uid in self.related_config.get(self.config_name, {}):
            return True
        return False

    def correct(self, value):
        if self.validate(value):
            return value
        return self.default


class DateTimeValidator(ValidatorBase):
    """日期时间验证器"""

    def __init__(self, date_format: str) -> None:
        if not date_format:
            raise ValueError("日期时间格式不能为空")
        self.date_format = date_format

    def validate(self, value):
        if not isinstance(value, str):
            return False
        try:
            datetime.strptime(value, self.date_format)
            return True
        except ValueError:
            return False

    def correct(self, value):
        if not isinstance(value, str):
            return DEFAULT_DATETIME.strftime(self.date_format)
        try:
            datetime.strptime(value, self.date_format)
            return value
        except ValueError:
            return DEFAULT_DATETIME.strftime(self.date_format)


class JSONValidator(ValidatorBase):
    def __init__(self, tpye: type[dict] | type[list] = dict) -> None:
        self.type = tpye

    def validate(self, value):
        if not isinstance(value, str):
            return False
        try:
            data = json.loads(value)
            if isinstance(data, self.type):
                return True
            else:
                return False
        except json.JSONDecodeError:
            return False

    def correct(self, value):
        return (
            value if self.validate(value) else ("{ }" if self.type == dict else "[ ]")
        )


class EncryptValidator(ValidatorBase):
    """加密数据验证器"""

    def validate(self, value):
        if not isinstance(value, str):
            return False
        try:
            dpapi_decrypt(value)
            return True
        except:
            return False

    def correct(self, value: Any) -> Any:
        return value if self.validate(value) else dpapi_encrypt("数据损坏, 请重新设置")


class VirtualConfigValidator(ValidatorBase):
    """虚拟配置验证器"""

    def __init__(self, function: Callable[[], str], default: str = "-"):
        self.function = function
        self.default = default

    def validate(self, value):
        return value == self.default

    def correct(self, value):
        try:
            return self.function()
        except Exception as e:
            return str(e)


class BoolValidator(ValidatorBase):
    """布尔值验证器"""

    def validate(self, value):
        if not isinstance(value, bool):
            return False
        return True

    def correct(self, value):
        return value if self.validate(value) else False


class FileValidator(ValidatorBase):
    """文件路径验证器"""

    def validate(self, value):
        if not isinstance(value, str):
            return False
        # 允许空字符串(表示未设置路径)
        if value == "":
            return True
        if not Path(value).is_absolute():
            return False
        if Path(value).suffix == ".lnk":
            return False
        return True

    def correct(self, value):
        if not isinstance(value, str):
            value = str(Path.cwd())
        # 空字符串直接返回
        if value == "":
            return ""
        if "%APPDATA%" in value:
            value = value.replace("%APPDATA%", os.getenv("APPDATA") or "")
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


class FolderValidator(ValidatorBase):
    """文件夹路径验证器"""

    def validate(self, value):
        if not isinstance(value, str):
            return False
        if not Path(value).is_absolute():
            return False
        if not Path(value).is_dir():
            return False
        return True

    def correct(self, value):
        if not isinstance(value, str):
            value = str(Path.cwd())
        if "%APPDATA%" in value:
            value = value.replace("%APPDATA%", os.getenv("APPDATA") or "")
        if not Path(value).is_dir():
            value = Path(value).with_suffix("")
        return Path(value).resolve().as_posix()


class UserNameValidator(ValidatorBase):
    """用户名验证器"""

    def validate(self, value):
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

    def correct(self, value):
        if not isinstance(value, str):
            value = "默认用户名"

        value = value.strip().strip(".")

        value = "".join(char for char in value if char not in ILLEGAL_CHARS)

        if value.upper() in RESERVED_NAMES or not value:
            value = "默认用户名"

        if len(value) > 255:
            value = value[:255]

        return value


class URLValidator(ValidatorBase):
    """URL格式验证器"""

    def __init__(
        self,
        schemes: list[str] | None = None,
        require_netloc: bool = True,
        default: str = "",
    ):
        """
        :param schemes: 允许的协议列表, 若为 None 则允许任意协议
        :param require_netloc: 是否要求必须包含网络位置, 如域名或IP
        """
        self.schemes = [s.lower() for s in schemes] if schemes else None
        self.require_netloc = require_netloc
        self.default = default

    def validate(self, value):
        if value == self.default:
            return True

        if not isinstance(value, str):
            return False

        try:
            parsed = urlparse(value)
        except Exception:
            return False

        # 检查协议
        if self.schemes is not None:
            if not parsed.scheme or parsed.scheme.lower() not in self.schemes:
                return False
        else:
            # 不限制协议仍要求有 scheme
            if not parsed.scheme:
                return False

        # 检查是否包含网络位置
        if self.require_netloc and not parsed.netloc:
            return False

        return True

    def correct(self, value):
        return value if self.validate(value) else self.default


class ArgumentValidator(ValidatorBase):

    def validate(self, value):
        if not isinstance(value, str):
            return False
        try:
            shlex.split(value.strip())
            return True
        except ValueError:
            return False

    def correct(self, value):

        return value if self.validate(value) else ""


class AdvancedArgumentValidator(ValidatorBase):

    def validate(self, value):
        if not isinstance(value, str):
            return False
        try:
            for segment in value.split("|"):
                segment = segment.strip()
                if not segment:
                    continue
                param_str = segment.split("%", 1)[-1].strip()
                shlex.split(param_str)
            return True
        except ValueError:
            return False

    def correct(self, value):

        return value if self.validate(value) else ""


class ConfigItem:
    """配置项"""

    def __init__(
        self,
        group: str,
        name: str,
        default: Any,
        validator: ValidatorBase = StringValidator(),
        legacy_group: str | None = None,
        legacy_name: str | None = None,
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

        validator: ValidatorBase
            配置项验证器, 默认为 None, 表示不进行验证
        """
        self.group = group
        self.name = name
        self.value: Any = default
        self.validator = validator
        self.legacy_group_name = (
            (legacy_group or group, legacy_name or name)
            if legacy_group or legacy_name
            else None
        )
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

    def getValue(self, if_decrypt: bool = True) -> Any:
        """
        获取配置项值
        """

        v = (
            self.value
            if self.validator.validate(self.value)
            else self.validator.correct(self.value)
        )

        if isinstance(self.validator, EncryptValidator) and if_decrypt:
            return dpapi_decrypt(v)
        return v

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


class ConfigBase(ABC):
    """
    配置基类

    这个类提供了基本的配置项管理功能, 包括连接配置文件、加载配置数据、获取和设置配置项值等。

    此类不支持直接实例化, 必须通过子类来实现具体的配置项,
    请继承此类并在子类中定义具体的配置项, 并在定义完成后调用父类的 `__init__` 方法。
    若将配置项设为类属性, 则所有实例都会共享同一份配置项数据。
    若将配置项设为实例属性, 则每个实例都会有独立的配置项数据。
    子配置项可以是 `MultipleConfig` 的实例。
    """

    def __init__(self):
        self.file: Path | None = None
        self.is_locked = False
        self._save_methods: list[Callable[[], Coroutine[Any, Any, None]]] = []

        # 配置项索引
        self._config_item_index: dict[str, dict[str, ConfigItem]] = {}
        self._multiple_config_index: dict[str, MultipleConfig] = {}
        for name in dir(self):
            item = getattr(self, name)

            if isinstance(item, ConfigItem):
                if not self._config_item_index.get(item.group):
                    self._config_item_index[item.group] = {}
                self._config_item_index[item.group][item.name] = item

            elif isinstance(item, MultipleConfig):
                self._multiple_config_index[name] = item

    async def connect(self, path: Path):
        """
        将配置数据绑定到指定配置文件

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

        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}

        await self.load(data)

        await self.add_save_method(self.save)

    async def add_save_method(
        self, save_method: Callable[[], Coroutine[Any, Any, None]]
    ):
        """
        添加父配置项的保存方法

        Parameters
        ----------
        save_method: Callable[[], Coroutine[Any, Any, None]]
            保存方法
        """

        if save_method != self.save:
            self._save_methods.append(save_method)

        for sub_config in self._multiple_config_index.values():
            await sub_config.add_save_method(save_method)

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

        # 加载多配置项类型数据
        sub_configs = data.pop("SubConfigsInfo", {})
        if not isinstance(sub_configs, dict):
            sub_configs = {}
        for name, sub_config in self._multiple_config_index.items():
            data_for_sub_config = sub_configs.get(name)
            if isinstance(data_for_sub_config, dict):
                await sub_config.load(data_for_sub_config)

        for group, info in self._config_item_index.items():
            for name, item in info.items():
                try:
                    item.setValue(data[group][name])
                except:
                    if item.legacy_group_name is not None:
                        with suppress(Exception):
                            item.setValue(
                                data[item.legacy_group_name[0]][
                                    item.legacy_group_name[1]
                                ]
                            )

        if self.file:
            await self.save()

        await asyncio.gather(*(_() for _ in self._save_methods))

    async def toDict(self, if_decrypt: bool = True) -> dict[str, Any]:
        """将配置项转换为字典"""

        data = {}

        for group, info in self._config_item_index.items():
            for name, item in info.items():
                data.setdefault(group, {})[name] = item.getValue(if_decrypt)

        for name, item in self._multiple_config_index.items():
            if not data.get("SubConfigsInfo"):
                data["SubConfigsInfo"] = {}
            data["SubConfigsInfo"][name] = await item.toDict(if_decrypt)

        return data

    def get(self, group: str, name: str) -> Any:
        """获取配置项的值"""

        if not self._config_item_index.get(group, {}).get(name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        return self._config_item_index[group][name].getValue()

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

        if not self._config_item_index.get(group, {}).get(name):
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        self._config_item_index[group][name].setValue(value)

        if self.file:
            await self.save()

        await asyncio.gather(*(_() for _ in self._save_methods))

    async def save(self) -> None:
        """保存配置"""

        if not self.file:
            raise ValueError("文件路径未设置, 请先调用 `connect` 方法连接配置文件")

        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(
            json.dumps(
                await self.toDict(if_decrypt=False), ensure_ascii=False, indent=4
            ),
            encoding="utf-8",
        )

    async def lock(self):
        """
        锁定配置项, 锁定后无法修改配置项值
        """

        self.is_locked = True

        for group in self._config_item_index.values():
            for item in group.values():
                item.lock()
        for config in self._multiple_config_index.values():
            await config.lock()

    async def unlock(self):
        """
        解锁配置项, 解锁后可以修改配置项值
        """

        self.is_locked = False

        for group in self._config_item_index.values():
            for item in group.values():
                item.unlock()
        for config in self._multiple_config_index.values():
            await config.unlock()


T = TypeVar("T", bound="ConfigBase")


class MultipleConfig(Generic[T]):
    """
    多配置项管理类

    这个类允许管理多个配置项实例, 可以添加、删除、修改配置项, 并将其保存到 JSON 文件中。
    允许通过 `config[uuid]` 访问配置项, 使用 `uuid in config` 检查是否存在配置项, 使用 `len(config)` 获取配置项数量。

    Parameters
    ----------
    sub_config_type: List[type]
        子配置项的类型列表, 必须是 ConfigBase 的子类
    """

    def __init__(self, sub_config_type: list[Type[T]]):
        if not sub_config_type:
            raise ValueError("子配置项类型列表不能为空")

        for config_type in sub_config_type:
            if not issubclass(config_type, ConfigBase):
                raise TypeError(
                    f"配置类型 {config_type.__name__} 必须是 ConfigBase 的子类"
                )

        self.sub_config_type: dict[str, Type[T]] = {
            _.__name__: _ for _ in sub_config_type
        }
        self.file: Path | None = None
        self.order: list[uuid.UUID] = []
        self.data: dict[uuid.UUID, T] = {}
        self.is_locked = False
        self._save_methods: list[Callable[[], Coroutine[Any, Any, None]]] = []

    def __getitem__(self, key: uuid.UUID) -> T:
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
        return f"MultipleConfig(items={len(self.data)}, types={list(self.sub_config_type.keys())})"

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

        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}

        await self.load(data)

        await self.add_save_method(self.save)

    async def add_save_method(
        self, save_method: Callable[[], Coroutine[Any, Any, None]]
    ):
        """
        添加父配置项的保存方法

        Parameters
        ----------
        save_method: Callable[[], Coroutine[Any, Any, None]]
            保存方法, 必须是一个协程函数, 无参数, 无返回值
        """

        if save_method != self.save:
            self._save_methods.append(save_method)

        for sub_config in self.data.values():
            await sub_config.add_save_method(save_method)

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

        self.order = []
        self.data = {}

        if not data.get("instances"):
            return

        for instance in data["instances"]:
            if not isinstance(instance, dict) or not data.get(instance.get("uid")):
                continue

            type_name = instance.get("type")

            if type_name in self.sub_config_type:
                self.order.append(uuid.UUID(instance["uid"]))
                self.data[self.order[-1]] = self.sub_config_type[type_name]()
                await self.data[self.order[-1]].load(data[instance["uid"]])

        if self.file:
            await self.save()

        await asyncio.gather(*(_() for _ in self._save_methods))

    async def toDict(self, if_decrypt: bool = True) -> dict[str, list | dict]:
        """
        将配置项转换为字典

        返回一个字典, 包含所有配置项的 UID 和类型, 以及每个配置项的具体数据。
        """

        data: dict[str, list | dict] = {
            "instances": [
                {"uid": str(_), "type": type(self.data[_]).__name__} for _ in self.order
            ]
        }
        for uid, config in self.items():
            data[str(uid)] = await config.toDict(if_decrypt)
        return data

    async def get(self, uid: uuid.UUID) -> dict[str, list | dict]:
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

        data: dict[str, list | dict] = {
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
        self.file.write_text(
            json.dumps(
                await self.toDict(if_decrypt=False), ensure_ascii=False, indent=4
            ),
            encoding="utf-8",
        )

    async def add(self, config_type: Type[T]) -> tuple[uuid.UUID, T]:
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

        if config_type not in self.sub_config_type.values():
            raise ValueError(f"配置类型 {config_type.__name__} 不被允许")

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        uid = uuid.uuid4()
        self.order.append(uid)
        self.data[uid] = config_type()

        for save_method in self._save_methods:
            await self.data[uid].add_save_method(save_method)

        if self.file:
            await self.data[uid].add_save_method(self.save)
            await self.save()

        await asyncio.gather(*(_() for _ in self._save_methods))

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

        await asyncio.gather(*(_() for _ in self._save_methods))

    async def setOrder(self, order: list[uuid.UUID]):
        """
        设置配置项的顺序

        Parameters
        ----------
        order: List[uuid.UUID]
            新的配置项顺序
        """

        if set(order) != set(self.data.keys()):
            raise ValueError("顺序与当前配置项不匹配")

        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        self.order = order

        if self.file:
            await self.save()

        await asyncio.gather(*(_() for _ in self._save_methods))

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
            return iter(())

        return (self.data[_] for _ in self.order)

    def items(self):
        """返回配置项的所有唯一标识符和实例的元组"""

        return zip(self.keys(), self.values())
