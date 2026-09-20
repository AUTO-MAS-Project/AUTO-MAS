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

"""配置守卫：以 MAS 这边存的设置为准，启动前和关闭后各核验一次。

模拟器自己会改用户的设置——升级、崩溃恢复、在多开器里手滑、甚至某些版本关机时
按内存态整体写回。守卫的做法是把**用户在 MAS 里定的那份**记为基准，
启动前对一次、关闭后再对一次，对不上就按基准写回去。

**与旧的雷电配置守卫不是一回事。** 旧的（``LDManager._capture_instance_config``）
是「开机拍一张快照、关机还原成那张快照」，保的是「这次运行期间别被改」，
而且只有雷电有、还挂在全局「屏蔽广告」开关下面。这里保的是「用户定的值别被改」，
两家都管，自己一个开关。

**基准只记用户显式设过的字段。** 没设过的项没有「应该是什么」可言，
守卫不该替用户决定——见 :func:`capture`。
"""

import json

from .settings import FIELDS, InstanceSettings


def load_baselines(raw: str | None) -> dict[str, dict[str, int]]:
    """从配置里的 JSON 串还原基准表。内容不可用时按空表处理。"""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    result: dict[str, dict[str, int]] = {}
    for slot, fields in data.items():
        if not isinstance(fields, dict):
            continue
        clean = {
            name: int(value)
            for name, value in fields.items()
            if name in FIELDS and isinstance(value, int) and not isinstance(value, bool)
        }
        if clean:
            result[str(slot)] = clean
    return result


def dump_baselines(baselines: dict[str, dict[str, int]]) -> str:
    return json.dumps(baselines, ensure_ascii=False, sort_keys=True)


def capture(settings: InstanceSettings) -> dict[str, int]:
    """把一台设备当前的设置记成基准。

    **只记 ``saved`` 的项。** ``default`` 是模拟器自己的默认值、``unset`` 是压根没设过——
    把它们写进基准，等于替用户决定「这个值以后就该是这样」，而他从没表达过这个意思。
    以后他在模拟器里调了这一项，守卫还会给他改回去。
    """
    return {
        name: item.value
        for name, item in settings.fields.items()
        if item.state == "saved" and item.value is not None
    }


def drift(baseline: dict[str, int], current: InstanceSettings) -> dict[str, int]:
    """算出偏离了基准的字段，返回**该写回去的值**（即基准值）。

    读不出来的字段（``unreadable``）不算偏离：那是没问到，不是被改了，
    这时候硬写回去是拿一份可能过期的基准去覆盖一份根本没看清的现状。
    """
    changes: dict[str, int] = {}
    for name, expected in baseline.items():
        item = current.fields.get(name)
        if item is None or item.state == "unreadable":
            continue
        if item.value != expected:
            changes[name] = expected
    return changes
