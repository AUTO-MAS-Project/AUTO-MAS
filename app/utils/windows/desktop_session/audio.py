"""调整指定预览进程的 WASAPI 会话音量。"""

import ctypes as C
from ctypes import wintypes as W

from comtypes import CLSCTX_ALL, COMMETHOD, GUID, IUnknown
from comtypes.client import CreateObject

OUT = ["out"]
IN = ["in"]
HRESULT = C.HRESULT


class IMMDevice(IUnknown):
    _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "Activate",
            (IN, C.POINTER(GUID), "iid"),
            (IN, W.DWORD, "context"),
            (IN, C.c_void_p, "parameters"),
            (OUT, C.POINTER(C.POINTER(IUnknown)), "interface"),
        )
    ]


class IMMDeviceEnumerator(IUnknown):
    _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    _methods_ = [
        COMMETHOD([], HRESULT, "EnumAudioEndpoints"),
        COMMETHOD(
            [],
            HRESULT,
            "GetDefaultAudioEndpoint",
            (IN, C.c_int, "flow"),
            (IN, C.c_int, "role"),
            (OUT, C.POINTER(C.POINTER(IMMDevice)), "device"),
        ),
    ]


class IAudioSessionControl2(IUnknown):
    _iid_ = GUID("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
    _methods_ = [
        *(
            COMMETHOD([], HRESULT, name)
            for name in (
                "GetState",
                "GetDisplayName",
                "SetDisplayName",
                "GetIconPath",
                "SetIconPath",
                "GetGroupingParam",
                "SetGroupingParam",
                "RegisterAudioSessionNotification",
                "UnregisterAudioSessionNotification",
                "GetSessionIdentifier",
                "GetSessionInstanceIdentifier",
            )
        ),
        # 使用原始 HRESULT 区分多进程共享的音频会话。
        COMMETHOD([], HRESULT, "GetProcessId", (IN, C.POINTER(W.DWORD), "pid")),
    ]


class IAudioSessionEnumerator(IUnknown):
    _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount", (OUT, C.POINTER(C.c_int), "count")),
        COMMETHOD(
            [],
            HRESULT,
            "GetSession",
            (IN, C.c_int, "index"),
            (OUT, C.POINTER(C.POINTER(IUnknown)), "session"),
        ),
    ]


class IAudioSessionManager2(IUnknown):
    _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetAudioSessionControl"),
        COMMETHOD([], HRESULT, "GetSimpleAudioVolume"),
        COMMETHOD(
            [],
            HRESULT,
            "GetSessionEnumerator",
            (OUT, C.POINTER(C.POINTER(IAudioSessionEnumerator)), "sessions"),
        ),
    ]


class ISimpleAudioVolume(IUnknown):
    _iid_ = GUID("{87CE5498-68D6-44E5-9215-6DA47EF883D8}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "SetMasterVolume",
            (IN, C.c_float, "level"),
            (IN, C.POINTER(GUID), "context"),
        ),
    ]


def apply(pid: int, volume: int) -> int:
    enumerator = CreateObject(
        "{BCDE0395-E52F-467C-8E3D-C4579291692E}", interface=IMMDeviceEnumerator
    )
    device = enumerator.GetDefaultAudioEndpoint(0, 1)  # render / multimedia
    manager = device.Activate(C.byref(IAudioSessionManager2._iid_), CLSCTX_ALL, None)
    sessions = manager.QueryInterface(IAudioSessionManager2).GetSessionEnumerator()
    count = 0
    for index in range(sessions.GetCount()):
        session = sessions.GetSession(index)
        control = session.QueryInterface(IAudioSessionControl2)
        owner = W.DWORD()
        if control.GetProcessId(C.byref(owner)) == 0 and owner.value == pid:
            session.QueryInterface(ISimpleAudioVolume).SetMasterVolume(
                volume / 100, None
            )
            count += 1
    return count
