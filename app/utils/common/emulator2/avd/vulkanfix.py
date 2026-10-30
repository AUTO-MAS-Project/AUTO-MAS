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

"""客体 Vulkan 驱动补丁（bindlock2），逐字节照搬 aemu-lab ``tools/guest/bindlock.py``。

改的是 API 34 镜像自带的 ``/vendor/lib64/libvulkan_enc.so``（sha256 ``898c0bbc…``），两处：

1. khrfix（09-30，星铁普通模式）：``vkUpdateDescriptorSetWithTemplateKHR`` 的两个入口直接调原始编码器，
   无类型的 ``pData`` 只发出 1 个字节，宿主收不到描述符。两个 KHR 入口各改成一条 5 字节 ``jmp`` 跳到
   核心入口（核心入口会把模板数据线性化后再发）。
2. bindlock（10-16，终末地崩溃）：``ResourceTracker`` 的 ``on_vkBindImageMemory`` / ``on_vkBindImageMemory2``
   查 ``info_VkDeviceMemory`` / ``info_VkImage`` 两张哈希表时不拿 ``mLock``；别的线程加锁插删时一次
   rehash 就让合法句柄查不到，返回 ``VK_ERROR_OUT_OF_DEVICE_MEMORY``，终末地断言 ``ret == VK_SUCCESS``
   失败退出。补丁让两个实现的成功出口改成返回标记值 :data:`_MAGIC`，在 khrfix 腾出来的
   ``dynCheck_entry_vkUpdateDescriptorSetWithTemplateKHR`` 函数体里放两个包装函数：拿锁 → 调原实现
   （纯内存读、不阻塞）→ 放锁 → 是标记值就自己按原出口的参数调编码器。三个转发入口改跳包装函数。
   锁不跨宿主往返（第 1 版跨了，和 VulkanQueueSubmitWithCommands 的全局序号互等，3/10 冷启动卡死）。

改好的库只在用户电脑上从镜像自带的那份生成，**不分发**：原库、函数开头字节、改完的库哈希任一对不上
就抛 :class:`VulkanFixError`，不打补丁。
"""

from __future__ import annotations

import hashlib
import struct

#: 镜像自带的库与改好的库（bindlock2，含 khrfix）的 sha256。
VULKAN_ENC_ORIG_SHA256 = (
    "898c0bbc38077e4b19d112f6c66e2970f1e015fc440fae091974b8f06e40fefb"
)
VULKAN_ENC_FIX_SHA256 = (
    "d5258af6244679fd5ce50245b7dcc1f645d971a04f7e64fc9872fcfb9faa7ecb"
)

# 以下地址都是虚拟地址，取自 bindlock.py（含义见那里的注释）。
_TEXT_DELTA = 0x1000  # .text: vaddr 0x1fcee0，文件偏移 0x1fbee0
_KHR_CORE = 0x3D8FA0  # entry_vkUpdateDescriptorSetWithTemplate（khrfix 的跳转目标）
_KHR_ENTRY = 0x3DA5B0
_KHR_DYN, _KHR_DYN_END = 0x3B6ED0, 0x3B7000  # 函数体到 0x3b7000 前是 int3 填充
_LOCK, _UNLOCK = 0x3E7910, 0x3E7940  # pthread_mutex_lock@plt / pthread_mutex_unlock@plt
_ENC_BIND, _ENC_BIND2 = 0x3E8300, 0x3E8320  # VkEncoder::vkBindImageMemory(2)@plt
_IMPL_BIND, _IMPL_BIND2 = 0x212090, 0x2122D0
_FWD_BIND, _FWD_BIND2, _FWD_BIND2KHR = 0x212080, 0x2122C0, 0x212570
_FWD_BYTES = bytes.fromhex("488b7f08e9")  # mov 0x8(%rdi),%rdi; jmp rel32
_MAGIC = 0x4D415332  # 'MAS2'；两个实现本来只会返回 -2

# 两个实现的成功出口（原字节，到跳编码器的 jmp 为止）
_EXIT_BIND = 0x21228E
_EXIT_BIND_ORIG = bytes.fromhex(
    "4889f7 4889ce 4c89c2 4c89c9 4d89d0 41b901000000 5b 415c 415d 415e 415f 5d e94e601d00"
)
_EXIT_BIND2 = 0x21254A
_EXIT_BIND2_ORIG = bytes.fromhex(
    "4889f7 488b7424f8 4489c2 4c89c9 41b801000000 5b 415c 415d 415e 415f 5d e9b35d1d00"
)
# 换成：mov $MAGIC,%eax; pop %rbx; pop %r12; pop %r13; pop %r14; pop %r15; pop %rbp; ret
_EXIT_MAGIC = (
    b"\xb8" + struct.pack("<I", _MAGIC) + bytes.fromhex("5b 415c 415d 415e 415f 5d c3")
)


class VulkanFixError(RuntimeError):
    """补丁打不了：库不是预期的那个版本，或改完哈希不对。"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Asm:
    def __init__(self, base: int) -> None:
        self.base = base
        self.buf = bytearray()

    def here(self) -> int:
        return self.base + len(self.buf)

    def raw(self, hexs: str) -> None:
        self.buf += bytes.fromhex(hexs)

    def call(self, target: int) -> None:
        self.buf += b"\xe8" + struct.pack("<i", target - (self.here() + 5))


def _prologue_lock(a: _Asm, frame: int, save: str) -> None:
    a.raw("53 55 4154 4155 4156 4157")  # push rbx, rbp, r12, r13, r14, r15
    a.raw(f"4883ec{frame:02x}")  # sub rsp, frame（调用时 rsp 16 字节对齐）
    a.raw("488b5f08")  # mov rbx, [rdi+8]   ; Impl*
    a.raw(save)  # 参数存进被调用者保存的寄存器
    a.raw("488dbb60060000")  # lea rdi, [rbx+0x660]  ; &Impl::mLock
    a.call(_LOCK)


def _unlock_check(a: _Asm) -> int:
    a.raw("4189c5")  # mov r13d, eax      ; 实现的返回值
    a.raw("488dbb60060000")  # lea rdi, [rbx+0x660]
    a.call(_UNLOCK)
    a.raw("4489e8")  # mov eax, r13d      ; 不调编码器时返回它（-2 或 MAGIC）
    a.raw("3d" + struct.pack("<I", _MAGIC).hex())  # cmp eax, MAGIC
    a.raw("7500")  # jne .out           ; rel8 由 _epilogue 填
    return len(a.buf) - 1


def _epilogue(a: _Asm, frame: int, rel8_at: int) -> None:
    rel = len(a.buf) - (rel8_at + 1)  # .out 在这里；编码器的返回值已在 eax
    if not 0 < rel < 0x80:
        raise VulkanFixError(f"jne 跳不到（{rel}）")
    a.buf[rel8_at] = rel
    a.raw(f"4883c4{frame:02x}")  # .out: add rsp, frame
    a.raw("415f 415e 415d 415c 5d 5b c3")  # pop r15, r14, r13, r12, rbp, rbx; ret


def _wrapper_bind(base: int) -> bytes:
    # on_vkBindImageMemory(this, context, input_result, device, image, memory, memoryOffset[栈])
    # 保存：r12=context r14=device r15=image rbp=memory；memoryOffset 在 [rsp+0x50]（入口时 [rsp+8]）
    a = _Asm(base)
    _prologue_lock(a, 0x18, "4989f4 4989ce 4d89c7 4c89cd")
    a.raw(
        "488b442450 48890424"
    )  # mov rax,[rsp+0x50]; mov [rsp],rax ; 实现的第 7 个参数
    a.raw(
        "4889df 4c89e6 4c89f1 4d89f8 4989e9"
    )  # rdi=Impl rsi=context rcx=device r8=image r9=memory
    a.call(_IMPL_BIND)
    rel8 = _unlock_check(a)
    # 同原出口：vkBindImageMemory(enc=context, device, image, memory, memoryOffset, doLock=1)
    a.raw("4c89e7 4c89f6 4c89fa 4889e9 4c8b442450 41b901000000")
    a.call(_ENC_BIND)
    _epilogue(a, 0x18, rel8)
    return bytes(a.buf)


def _wrapper_bind2(base: int) -> bytes:
    # on_vkBindImageMemory2(this, context, input_result, device, bindingCount, pBindInfos)：全在寄存器
    # 保存：r12=context r14=device r15=bindingCount rbp=pBindInfos
    a = _Asm(base)
    _prologue_lock(a, 0x08, "4989f4 4989ce 4d89c7 4c89cd")
    a.raw(
        "4889df 4c89e6 4c89f1 4d89f8 4989e9"
    )  # rdi=Impl rsi=context rcx=device r8=bindingCount r9=pBindInfos
    a.call(_IMPL_BIND2)
    rel8 = _unlock_check(a)
    # 同原出口：vkBindImageMemory2(enc=context, device, bindingCount, pBindInfos, doLock=1)
    a.raw("4c89e7 4c89f6 4489fa 4889e9 41b801000000")
    a.call(_ENC_BIND2)
    _epilogue(a, 0x08, rel8)
    return bytes(a.buf)


def _jmp(src: int, dst: int) -> bytes:
    return b"\xe9" + struct.pack("<i", dst - (src + 5))


def patch_vulkan_encoder(original: bytes) -> bytes:
    """返回改好的库（bindlock2，含 khrfix）。原库哈希、各处原字节、改完的哈希任一对不上就抛
    :class:`VulkanFixError`。"""
    digest = sha256(original)
    if digest != VULKAN_ENC_ORIG_SHA256:
        raise VulkanFixError(f"客体驱动库 sha256 {digest} 不是预期版本")
    data = bytearray(original)

    def put(va: int, blob: bytes, expect: bytes | None, name: str) -> None:
        off = va - _TEXT_DELTA
        if expect is not None and bytes(data[off : off + len(expect)]) != expect:
            raise VulkanFixError(
                f"{name}（0x{va:x}）原字节不符: {bytes(data[off : off + len(expect)]).hex()}"
            )
        data[off : off + len(blob)] = blob

    # 1. khrfix：两个 KHR 入口跳核心入口
    put(
        _KHR_ENTRY,
        _jmp(_KHR_ENTRY, _KHR_CORE),
        bytes.fromhex("4157415641554154"),
        "entry_vkUpdateDescriptorSetWithTemplateKHR",
    )
    put(
        _KHR_DYN,
        _jmp(_KHR_DYN, _KHR_CORE),
        bytes.fromhex("5541574156415541"),
        "dynCheck_entry_vkUpdateDescriptorSetWithTemplateKHR",
    )

    # 2. 两个实现的成功出口返回 MAGIC（出口剩下的字节填 int3）
    for va, orig, name in (
        (_EXIT_BIND, _EXIT_BIND_ORIG, "on_vkBindImageMemory 实现出口"),
        (_EXIT_BIND2, _EXIT_BIND2_ORIG, "on_vkBindImageMemory2 实现出口"),
    ):
        put(va, _EXIT_MAGIC + b"\xcc" * (len(orig) - len(_EXIT_MAGIC)), orig, name)

    # 3. 两个包装函数放进 dynCheck 的死代码里（剩下的填 int3）
    cave1 = _KHR_DYN + 5
    w1 = _wrapper_bind(cave1)
    cave2 = cave1 + len(w1)
    w2 = _wrapper_bind2(cave2)
    if cave2 + len(w2) > _KHR_DYN_END:
        raise VulkanFixError(
            f"包装函数（{len(w1)} + {len(w2)} 字节）放不进 {_KHR_DYN_END - cave1} 字节"
        )
    put(cave1, w1 + w2 + b"\xcc" * (_KHR_DYN_END - cave2 - len(w2)), None, "包装函数")

    # 4. 三个转发入口跳包装函数（包装函数自己取 this->mImpl）
    for va, target, name in (
        (_FWD_BIND, cave1, "ResourceTracker::on_vkBindImageMemory"),
        (_FWD_BIND2, cave2, "ResourceTracker::on_vkBindImageMemory2"),
        (_FWD_BIND2KHR, cave2, "ResourceTracker::on_vkBindImageMemory2KHR"),
    ):
        put(va, _jmp(va, target), _FWD_BYTES, name)

    patched = bytes(data)
    digest = sha256(patched)
    if digest != VULKAN_ENC_FIX_SHA256:
        raise VulkanFixError(f"改完的库 sha256 {digest} 不是预期值")
    return patched


__all__ = [
    "VULKAN_ENC_FIX_SHA256",
    "VULKAN_ENC_ORIG_SHA256",
    "VulkanFixError",
    "patch_vulkan_encoder",
    "sha256",
]
