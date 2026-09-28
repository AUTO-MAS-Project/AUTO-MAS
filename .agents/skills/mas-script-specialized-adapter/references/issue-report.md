# 问题包导出（专项诊断 ZIP）

各专项的「导出问题包」是 MAS 领域能力：收集 MAS 自身日志/历史与专项的日志、
配置快照，打包供用户反馈。共享原语与各专项服务都在 `frontend/electron/services`
（`issueReportCore.ts` 是唯一事实来源，原语签名现场读代码，本文只写不变量与反模式）。

## 不变量

1. **多安装按实例收集，禁止跨实例取全局最新**。一个专项类型可有多个安装（多个
   脚本实例指向不同 RootPath，`discoverInstallations` 去重后逐个给出），每个安装
   的证据归档在各自的 `<前缀>/<label>/` 下。反模式：跨安装比 mtime 只留全局一份
   「最新」——其他安装的失败证据会静默丢失。该反模式曾在 ok-ww / ok-nte / zzz-od /
   BetterGI / Whimbox 五个服务重复出现，靠评审才暴露。
2. **后端 `debug/` 只收声明方自己的诊断子目录**。专项在 `debug/<专项目录>/` 落盘的
   切号/登录诊断必须登记进 `ADAPTER_DEBUG_SUBDIRS`；**未登记目录会被所有问题包
   收录（互相混入）**，漏登记即混入事故。
3. **新专项服务以核心现有原语为起点**。并行开发期核心可能已演进——新增服务前先读
   `issueReportCore.ts` 当前导出，不要照抄旧服务的收集循环（Whimbox 服务即因照抄
   旧模式漏掉了当时刚合入的 debug 过滤）。

## 收集形态

- **固定日志路径**（脚本目录内相对路径不变）：用 `addPerInstallationFile`。
- **滚动日志目录**（按天/按序滚动，无固定文件名）：每安装扫描目录取 mtime 最新
  一份，`latest` 声明在安装循环内。
- **专项 debug 诊断**：`addDebugDirectory` + 自身目录登记。
- 历史记录型证据（按用户/按次落盘）按各自专项布局收集，不适用「安装」概念。

## 接入清单

- 安装发现：`discoverInstallations` 的 configType / pathField / labelPrefix 与该专项
  配置读取口径保持同步。
- 归档路径：一律 `<前缀>/<label>/...`，跨平台用 posix join。
- 大小上限、脱敏、截断由核心原语统一处理，服务层不要自建。
- 碎片：问题包导出按专项归属记 changelog；「已发布」判据以 ok-nte 在 5.5.0 正式版的
  问题包条目为锚点（见根目录 `AGENTS.md` 的碎片规则）。
