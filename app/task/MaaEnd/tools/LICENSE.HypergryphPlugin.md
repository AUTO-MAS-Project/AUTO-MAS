# 第三方许可与来源声明

本目录的 `game_update.py`（连同它的两个入口 `MaaEndManager._ensure_game_client_updated`
与 `MaaEnd/Update.py`，以及 `app/utils/constants.py` 里的 `ENDFIELD_SERVER_PRESETS`）按
下列项目的公开源码所描述的流程与协议用 Python **重新实现**：差量落地的顺序与编排、更新
接口的响应与清单字段语义、渠道参数取自它的公开源码，代码与文档中不包含该项目的源文件
副本，也不使用它的任何二进制。本模块与后续改动由 AUTO-MAS 按 AGPL-3.0-or-later 发布。

下列项目采用 MIT 许可。MIT 要求在所有副本或实质部分中保留版权声明与许可原文，故在此收录
原文；同一声明也注释在本包入口 `__init__.py` 里，保证任何打包形态下声明都随代码一起分发。

## Hi3Helper.Plugin.Hypergryph

- 仓库：<https://github.com/misaka10843/Hi3Helper.Plugin.Hypergryph>（Collapse Launcher 的第三方插件）
- 依据版本：`9d893eba669cb01bb667e16095e6e28bf1ce546b`（`main`，2026-09-12）
- 参考范围：差量落地的顺序与编排
  （`Hi3Helper.Hypergryph.Core/Management/HgGameInstaller.Install.cs`）、更新接口的响应
  与清单字段（`Hi3Helper.Hypergryph.Core/Management/Api/HgApiStructs.cs`）、安装目录配置
  与游戏资源的读取处理（`Hi3Helper.Hypergryph.Core/Utils/`）、终末地的四套渠道参数
  （`Hi3Helper.Plugin.Endfield/Management/PresetConfig/` 下 Cn/Bili/Global/Play 四份）
- 许可证：MIT
- 版权行：`Copyright (c) 2025 Collapse Launcher`

```text
MIT License

Copyright (c) 2025 Collapse Launcher

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
