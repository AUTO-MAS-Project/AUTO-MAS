"""MaaFW 第一层·外部运行：把 interface.json 映射成外壳自己的实例配置。

不加载项目 DLL，而是写项目外壳能识别的配置文件后裸启动外壳。本包只负责
「生成配置 dict」的纯逻辑，不写文件、不删实例、不起进程。
"""

from .shell import ShellFamily, detect_shell_family

__all__ = [
    "ShellFamily",
    "detect_shell_family",
]
