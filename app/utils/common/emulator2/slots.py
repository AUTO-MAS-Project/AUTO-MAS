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

"""设备号槽位表。

脚本用 ``(EmulatorId, EmulatorIndex)`` 绑定设备，而一条 Emulator 2.0 配置纳管多条
模拟器路径，各家的原生实例索引会撞号。这里把它们统一编排成配置内唯一的「设备号」。

三条不变量：

1. **设备号在本配置内单调递增分配**，移除路径、删除实例都写墓碑，号码**永不复用**。
   否则移除雷电路径后再加 MuMu，MuMu 会拿到雷电用过的号，已绑好的脚本静默指向别的设备。
2. **设备号只按「路径 + 原生索引」认设备，不做身份指纹**。在模拟器自己的多开器里删掉
   实例、又在同一原生索引重建，仍然是同一个设备号——这与用户心智一致（「我的 3 号模拟器」
   指的就是 3 号），且换成另一台设备时脚本会明显跑错，不是静默的数据损坏。
   在 MAS 里显式删除的实例不同：号码退役，之后占这个原生索引的新实例拿新号。
3. **一次枚举失败不等于实例被删除**。槽位是否可用由「当次枚举结果」决定，
   不写进持久化状态；持久化状态只有 ``active`` 与 ``tombstone``，后者只在
   用户显式移除路径或删除实例时写入。

两种墓碑：移除路径的墓碑**保留** ``pathId`` 与原生索引，重新添加同一路径时据此沿用原号
（``pathId`` 由规范化安装路径派生，所以会自动对上）；删除实例退役的号 ``pathId`` 与原生索引
都清空，不属于任何路径、不认领任何索引，也不随路径复活——清空 ``pathId`` 还能让回退到
旧版本时，旧代码同样不会把它当成那条路径的墓碑复活。
"""

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import PurePath
from typing import Iterable, Literal

SlotState = Literal["active", "tombstone"]


def normalize_install_path(install_path: str) -> str:
    """安装路径的规范化形式，用于派生 ``pathId`` 与判重。

    只做大小写与分隔符归一，不访问文件系统——槽位表要在模拟器不在线、
    甚至安装目录暂时不可达时也能读写。
    """
    text = str(install_path).strip().strip('"').replace("\\", "/").rstrip("/")
    return PurePath(text).as_posix().casefold()


def make_path_id(install_path: str) -> str:
    """由安装路径派生稳定的 ``pathId``。

    派生而非随机，是为了让「移除路径 → 重新添加同一路径」自动沿用原设备号；
    同时一条配置里同一个安装路径天然只能存在一条记录。
    """
    digest = hashlib.sha256(normalize_install_path(install_path).encode("utf-8"))
    return digest.hexdigest()[:12]


@dataclass(frozen=True)
class PathRecord:
    """一条被纳管的模拟器安装。"""

    path_id: str
    install_path: str
    alias: str
    type: str
    version: str

    @classmethod
    def create(
        cls, install_path: str, alias: str, type: str, version: str
    ) -> "PathRecord":
        return cls(
            path_id=make_path_id(install_path),
            install_path=install_path,
            alias=alias,
            type=type,
            version=version,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "PathRecord":
        install_path = str(data.get("installPath", ""))
        return cls(
            path_id=str(data.get("pathId") or make_path_id(install_path)),
            install_path=install_path,
            alias=str(data.get("alias", "")),
            type=str(data.get("type", "")),
            version=str(data.get("version", "")),
        )

    def to_dict(self) -> dict:
        return {
            "pathId": self.path_id,
            "installPath": self.install_path,
            "alias": self.alias,
            "type": self.type,
            "version": self.version,
        }


@dataclass(frozen=True)
class SlotRecord:
    """一个设备号。

    ``slot`` 与 ``native_index`` 都是数字字符串，与脚本侧 ``EmulatorIndex`` 的口径一致。
    """

    slot: str
    path_id: str
    native_index: str
    state: SlotState = "active"

    @classmethod
    def from_dict(cls, data: dict) -> "SlotRecord":
        state = str(data.get("state", "active"))
        return cls(
            slot=str(data.get("slot", "")),
            path_id=str(data.get("pathId", "")),
            native_index=str(data.get("nativeIndex", "")),
            state="tombstone" if state == "tombstone" else "active",
        )

    def to_dict(self) -> dict:
        return {
            "slot": self.slot,
            "pathId": self.path_id,
            "nativeIndex": self.native_index,
            "state": self.state,
        }


class SlotTable:
    """设备号槽位表。

    只做编排，不访问文件系统、不启动模拟器。当次枚举结果由调用方传进来。
    """

    def __init__(self, records: Iterable[SlotRecord] = ()) -> None:
        self._records: list[SlotRecord] = list(records)

    # ---- 持久化 ---------------------------------------------------------

    @classmethod
    def from_json(cls, raw: str | None) -> "SlotTable":
        """从配置里的 JSON 串还原。内容不可解析时按空表处理，不抛异常。"""
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return cls()
        if not isinstance(data, list):
            return cls()
        records = []
        for item in data:
            if not isinstance(item, dict):
                continue
            record = SlotRecord.from_dict(item)
            if record.slot.isdecimal():
                records.append(record)
        return cls(records)

    def to_json(self) -> str:
        return json.dumps(
            [record.to_dict() for record in self._records], ensure_ascii=False
        )

    # ---- 查询 -----------------------------------------------------------

    @property
    def records(self) -> list[SlotRecord]:
        return list(self._records)

    def resolve(self, slot: str) -> SlotRecord | None:
        """按设备号取记录。墓碑也会返回——调用方需要据此报「设备不可用」。"""
        target = str(slot)
        for record in self._records:
            if record.slot == target:
                return record
        return None

    def find(self, path_id: str, native_index: str) -> SlotRecord | None:
        target = str(native_index)
        for record in self._records:
            if record.path_id == path_id and record.native_index == target:
                return record
        return None

    def slots_of(self, path_id: str, *, include_tombstone: bool = False) -> list[str]:
        return [
            record.slot
            for record in self._records
            if record.path_id == path_id
            and (include_tombstone or record.state == "active")
        ]

    def next_slot(self) -> str:
        """下一个可分配的设备号：所有已存在号码（含墓碑）的最大值 + 1。"""
        used = [int(record.slot) for record in self._records if record.slot.isdecimal()]
        return str(max(used) + 1 if used else 0)

    # ---- 变更 -----------------------------------------------------------

    def sync_path(
        self, path_id: str, native_indexes: Iterable[str]
    ) -> list[SlotRecord]:
        """把一条**在用**路径当次枚举到的原生索引并进表，返回新分配的记录。

        只对在用的路径调用：已移除路径的墓碑要一直留着原生索引，重新添加时由
        :meth:`revive_path` 复活、沿用原号。先把这条路径上的存量墓碑退役（见
        :meth:`retire_tombstones`），不然模拟器把墓碑占着的索引分给新实例时，
        新实例拿不到号，设备表里看不见。

        - 已有记录的原生索引：**不动**。
        - 没有记录的原生索引：追加新设备号。
        - 表里有、这次没枚举到的：**不做任何持久化改动**——一次枚举失败不等于实例被删除，
          可用性由调用方按当次枚举结果判断。
        """
        self.retire_tombstones(path_id)
        added: list[SlotRecord] = []
        for native_index in native_indexes:
            text = str(native_index)
            if self.find(path_id, text) is not None:
                continue
            record = SlotRecord(
                slot=self.next_slot(),
                path_id=path_id,
                native_index=text,
                state="active",
            )
            self._records.append(record)
            added.append(record)
        return added

    def tombstone_path(self, path_id: str) -> list[str]:
        """移除一条路径：把它的 active 记录改成墓碑，返回被墓碑化的设备号。

        记录不删除，号码也不回收——保证以后不会分配给别的设备。
        """
        tombstoned: list[str] = []
        for position, record in enumerate(self._records):
            if record.path_id == path_id and record.state == "active":
                self._records[position] = replace(record, state="tombstone")
                tombstoned.append(record.slot)
        return tombstoned

    def tombstone_slot(self, slot: str) -> bool:
        """退役单个设备号：实例被显式删除时用。

        与 :meth:`tombstone_path` 一样**不删记录、不回收号码**——号码回收了，
        以后新建的实例就可能拿到同一个号，而某个脚本还绑着它，于是悄悄连到另一台设备上。

        但要和路径、原生索引脱钩：模拟器多半会把这个索引分给下一台新建的实例（雷电总是复用
        最小的空闲索引），那是另一台设备，要拿新号；墓碑占着索引，新实例就被挡在设备表外。
        移除再添加这条路径时，这个号也不该跟着复活。

        墓碑记录不进设备列表，所以删掉的实例不会继续在表里占一行「未找到」。
        """
        for position, record in enumerate(self._records):
            if record.slot == str(slot) and record.state == "active":
                self._records[position] = replace(
                    record, state="tombstone", path_id="", native_index=""
                )
                return True
        return False

    def retire_tombstones(self, path_id: str) -> list[str]:
        """把一条**在用**路径上的墓碑退役，返回退役的设备号。

        在用路径上的墓碑只可能来自删除实例（移除路径的墓碑在重新添加时已先复活）。
        早先版本删除实例时只写墓碑、没和路径脱钩，这里给存量补上，效果同 :meth:`tombstone_slot`。
        """
        retired: list[str] = []
        for position, record in enumerate(self._records):
            if record.path_id == path_id and record.state == "tombstone":
                self._records[position] = replace(record, path_id="", native_index="")
                retired.append(record.slot)
        return retired

    def revive_path(self, path_id: str) -> list[str]:
        """重新添加同一条路径：复活它的墓碑，沿用原设备号。

        删除实例退役的号已和路径脱钩，不在其列：那台实例已经不在了。
        """
        revived: list[str] = []
        for position, record in enumerate(self._records):
            if record.path_id == path_id and record.state == "tombstone":
                self._records[position] = replace(record, state="active")
                revived.append(record.slot)
        return revived
