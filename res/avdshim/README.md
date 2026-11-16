# ModAVD 的 MAA 截图组件

`external_renderer_ipc.dll` 是 [ModAVDExtras](https://github.com/ModAVD/ModAVDExtras) 发布的兼容外壳。它导出 MuMu 同名 DLL 的四个截图函数（`nemu_connect`、`nemu_disconnect`、`nemu_capture_display`、`nemu_get_display_id`），从 ModAVD 的截图共享内存取画面，让 MAA 走「MuMu 截图增强」。怎么用见 `app/task/MAA/tools/avd.py`。

- 版本：ModAVDExtras `v0.1.0`（提交 `ed7b8ad`），由该仓库的 release workflow 在 GitHub Actions 上编出：<https://github.com/ModAVD/ModAVDExtras/releases/tag/v0.1.0>
- SHA-256：`3e55150f1cc0c702e0b9b41dd9f248e99363aaa7c07d881660143f0cd36b4c45`（171,008 字节），和 Release 附件 `SHA256SUMS.txt` 里的一致。
- 许可证：LGPL-3.0-or-later。本目录的 `LICENSE` 是 LGPL-3.0 正文，`COPYING` 是它所补充的 GPL-3.0 正文，都取自 `v0.1.0` tag。
- 源码：<https://github.com/ModAVD/ModAVDExtras/tree/v0.1.0>（外壳在 `shim/mumu_shim.c`，截图代码在 `src/`）。
- 更新：从 ModAVDExtras 的 Release 下载新版替换本文件，并改上面的版本、提交和 SHA-256。`ensure_mumu_shim` 按内容比对，下次运行 MAA 前会把新文件放到各根目录的 `mumu-shim\shell\sdk\` 下。
