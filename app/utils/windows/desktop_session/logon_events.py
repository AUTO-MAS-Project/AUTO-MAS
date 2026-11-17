"""查找与本次分身登录相关的 Windows 安全事件。"""

import os
from datetime import datetime
from ipaddress import IPv6Address, ip_address
from xml.etree import ElementTree

import win32evtlog
from pywintypes import error as Win32Error

from .native import handle_scope

_NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}


def _local_address(value: str) -> bool:
    try:
        address = ip_address(value)
    except ValueError:
        return False
    if isinstance(address, IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_loopback


def matching_failure(
    xml: str, started: datetime, account: str, sid: str, *, remote: bool
) -> dict[str, str] | None:
    event = ElementTree.fromstring(xml)
    timestamp = event.find("e:System/e:TimeCreated", _NS)
    if timestamp is None:
        return None
    occurred = datetime.fromisoformat(timestamp.attrib["SystemTime"])
    if occurred < started:
        return None
    data = {
        node.attrib["Name"]: node.text or ""
        for node in event.findall("e:EventData/e:Data", _NS)
    }
    target_sid = data.get("TargetUserSid", "")
    domain, _, user = account.rpartition("\\")
    if target_sid != sid and (
        target_sid not in {"", "S-1-0-0"}
        or data.get("TargetUserName", "").casefold() != user.casefold()
        or data.get("TargetDomainName", "").casefold()
        not in {"", "-", ".", domain.casefold()}
    ):
        return None
    if remote:
        if data.get("LogonType") not in {"3", "10"} or not _local_address(
            data.get("IpAddress", "")
        ):
            return None
    elif (
        data.get("LogonType") != "2"
        or int(data.get("ProcessId", "0"), 16) != os.getpid()
    ):
        return None
    return {
        "time": occurred.isoformat(),
        "status": f"0x{int(data['Status'], 16):08X}",
        "substatus": f"0x{int(data['SubStatus'], 16):08X}",
    }


def recent_failure(
    started: datetime, account: str, sid: str, *, remote: bool
) -> dict[str, str] | None:
    since = started.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    query = f"*[System[EventID=4625 and TimeCreated[@SystemTime >= '{since}']]]"
    try:
        with handle_scope(
            win32evtlog.EvtQuery(
                "Security",
                win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection,
                query,
            )
        ) as results:
            for event in win32evtlog.EvtNext(results, 16, 0, 0):
                with handle_scope(event):
                    xml = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
                try:
                    failure = matching_failure(
                        xml, started, account, sid, remote=remote
                    )
                except (ElementTree.ParseError, ValueError, KeyError):
                    continue
                if failure:
                    return failure
    except Win32Error:
        # 安全日志的访问权限和登录失败审计策略由 Windows 管理。
        return None
    return None
