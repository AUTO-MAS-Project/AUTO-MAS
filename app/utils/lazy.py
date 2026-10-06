#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


#   Contact: DLmaster_361@163.com



"""惰性代理：给服务模块一个可延迟解析的模块级全局名。"""

from __future__ import annotations

from typing import Any


class LazyProxy:
    """惰性代理：首次属性访问时才导入真实对象，避免初始化期间的循环导入。

    与模块级 ``__getattr__`` 不同，它绑定为一个真实的模块全局名，因此函数内的
    裸全局名引用（LOAD_GLOBAL）也能正常解析；同时转发属性读写，保证
    ``Config.xxx = yyy`` 这类赋值落到真实对象上。
    """

    def __init__(self, module: str, name: str) -> None:
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_obj", None)

    def _resolve(self) -> Any:
        obj = self.__dict__["_obj"]
        if obj is None:
            from importlib import import_module

            obj = getattr(
                import_module(self.__dict__["_module"]), self.__dict__["_name"]
            )
            object.__setattr__(self, "_obj", obj)
        return obj

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._resolve(), attr)

    def __setattr__(self, attr: str, value: Any) -> None:
        setattr(self._resolve(), attr, value)

    def __delattr__(self, attr: str) -> None:
        # 与 __setattr__ 对称：只转发读写不转发删除，会让 mock.patch 的
        # 退出路径（setattr 进真对象、delattr 回代理）拿不到属性而炸
        delattr(self._resolve(), attr)
