# 第三方许可与来源声明

本包（`app/services/gi_updater/`）是原神客户端更新引擎，按上游公开源码所描述的流程与
协议用 Python **重新实现**：命名分层与部分类型取自下列项目的公开源码，代码与文档中不包含
这些项目的源文件副本。本包的代码与后续改动由 AUTO-MAS 按 AGPL-3.0-or-later 发布。

下列项目均采用 MIT 许可。MIT 要求在所有副本或实质部分中保留版权声明与许可原文，
故在此逐份收录原文；同一声明也注释在本包入口 `__init__.py` 里，保证任何打包形态下
声明都随代码一起分发。

## Collapse Launcher

- 仓库：<https://github.com/CollapseLauncher/Collapse>
- 依据版本：`dc47259171794596331dffcf90db85a6ac0415ac`（`main`，2026-09-20）
- 参考范围：更新三段流程的编排与命名（`Classes/InstallManagement`、
  `Classes/GameManagement/Versioning`、`Classes/Helper/LauncherApiLoader/HoYoPlay`）
- 许可证：MIT

```text
MIT License

Copyright (c) neon-nyan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Hi3Helper.Sophon

- 仓库：<https://github.com/CollapseLauncher/Hi3Helper.Sophon>（Collapse 的子模块）
- 依据版本：`9189e990e2d8ef6a9ee5b3dfd77b41e1874f9cac`
- 参考范围：Sophon 清单与差分的字段结构、差分端点与补丁方式
  （`Protos/SophonPatchProto.proto`、`Protos/SophonManifestProto.proto`、`SophonPatch.cs`）
- 许可证：MIT

```text
MIT License

Copyright (c) 2024-2025 Collapse Launcher

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
