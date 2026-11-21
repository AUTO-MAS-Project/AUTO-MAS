"""PE 文件头与导入表的只读解析（只用标准库，**不映射也不执行**文件）。"""

from __future__ import annotations

from pathlib import Path

_PE_SIGNATURE = bytes((0x50, 0x45, 0x00, 0x00))  # PE signature
# PE 头里的 machine 字段 -> 架构名。取值来自 PE/COFF 规范。
_PE_MACHINE_ARCHITECTURES = {
    0x014C: "x86",
    0x8664: "x64",
    0xAA64: "arm64",
}


def detect_pe_architecture(path: Path) -> str | None:
    """读出 PE 文件的目标架构，**不映射也不执行它**。

    只解析 DOS 头里的 e_lfanew 偏移、跳到 PE 签名、再读两字节 machine 字段。
    做法取自 mfwa 的 ``tools/runtime/probe.py``。

    Returns:
        ``"x86"`` / ``"x64"`` / ``"arm64"``；不是 PE 文件或读不出来时 None。
    """

    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                return None
            stream.seek(0x3C)
            offset_bytes = stream.read(4)
            if len(offset_bytes) != 4:
                return None
            stream.seek(int.from_bytes(offset_bytes, "little"))
            if stream.read(4) != _PE_SIGNATURE:
                return None
            machine = int.from_bytes(stream.read(2), "little")
    except (OSError, ValueError):
        return None
    return _PE_MACHINE_ARCHITECTURES.get(machine)


#: 导入表条目数的上限：超过就当这个文件读得不对，不下结论。
_MAX_PE_IMPORTS = 4096


def pe_imported_dlls(path: Path) -> list[str] | None:
    """PE 文件导入表里的 DLL 名（只读文件头与导入表，**不映射也不执行**）。

    只看普通导入（数据目录第 1 项）：延迟加载的依赖缺了 ``LoadLibrary`` 照样成功。
    不是 PE 文件或读不出来时 None。
    """

    def u16(raw: bytes, at: int) -> int:
        return int.from_bytes(raw[at : at + 2], "little")

    def u32(raw: bytes, at: int) -> int:
        return int.from_bytes(raw[at : at + 4], "little")

    try:
        with path.open("rb") as stream:
            head = stream.read(4096)
            if head[:2] != b"MZ" or len(head) < 0x40:
                return None
            pe = u32(head, 0x3C)
            stream.seek(pe)
            coff = stream.read(24)
            if coff[:4] != _PE_SIGNATURE:
                return None
            section_count = u16(coff, 6)
            optional_size = u16(coff, 20)
            optional = stream.read(optional_size)
            magic = u16(optional, 0)
            if magic == 0x20B:  # PE32+
                directories = 112
            elif magic == 0x10B:  # PE32
                directories = 96
            else:
                return None
            import_rva = u32(optional, directories + 8)
            if not import_rva:
                return []
            table = stream.read(40 * section_count)
            sections = [
                (
                    u32(table, 40 * i + 12),
                    max(u32(table, 40 * i + 8), u32(table, 40 * i + 16)),
                    u32(table, 40 * i + 20),
                )
                for i in range(section_count)
            ]

            def offset(rva: int) -> int | None:
                for address, size, raw in sections:
                    if address <= rva < address + size:
                        return rva - address + raw
                return None

            descriptor = offset(import_rva)
            if descriptor is None:
                return None
            names: list[str] = []
            while len(names) <= _MAX_PE_IMPORTS:
                stream.seek(descriptor)
                entry = stream.read(20)
                if len(entry) < 20:
                    return None
                if entry == bytes(20):
                    return names
                name_at = offset(u32(entry, 12))
                if name_at is None:
                    return None
                stream.seek(name_at)
                name = stream.read(260).split(b"\0", 1)[0]
                names.append(name.decode("ascii", errors="replace"))
                descriptor += 20
    except (OSError, ValueError):
        return None
    return None


__all__ = ["detect_pe_architecture", "pe_imported_dlls"]
