# HSR 候选与 r10 wheelhouse 晋升记录

状态：`observed`，记录时间 2026-07-23。

## 源与版本

- 独立源仓库：`D:\trae_projects\AUTO-MAS-Projects\plugins\automas-hsr`
- Git HEAD：`2430286c09ff3dd8cdd1d2e8aec8a96f49799b28`
- 仓库包含未提交的 HSR/SRA/M7A 培养目标、更新契约和托管更新事务修改，因此 Git HEAD 不是完整源码身份；完整源码摘要以 r10 `manifest.json` 中各项目的 source digest 为准。
- `automas-hsr`：0.1.5
- `automas-script-hsr`：0.1.4
- `automas-hsr-adapter-sra`：0.1.4
- `automas-hsr-adapter-m7a`：0.1.5

## 自动验证

- HSR 仓库完整 unittest：190/190 通过。
- `uv lock --check`：通过。
- r6/r7 两次独立构建的 4 个 wheel 文件名、大小与 SHA256 全部一致。
- r6 产物通过 `twine check`、metadata-only、local-adapter-resolution、local-meta-resolution smoke。
- r10 完整 wheelhouse 生成完成：127 wheels，其中 95 个 host runtime、9 个 plugin runtime、23 个 plugin distributions，声明 21 个唯一插件入口点。
- 前端发布链 validator：通过，并与 `res/integration-snapshot.json` 严格绑定。
- 后端 `verify_wheelhouse_snapshot.py --strict`：通过。

## HSR wheel 身份

| distribution | version | bytes | SHA256 |
| --- | --- | ---: | --- |
| automas-hsr | 0.1.5 | 13673 | `2b4cc7b4eaf9530564f9e4a8a26de98af497a0c2a2969347375a50072104c46b` |
| automas-hsr-adapter-m7a | 0.1.5 | 32268 | `d7837c5aa2c61e39f80ed10fc1af71f9d38df2190e9d7caa9653fef65b2d78d4` |
| automas-hsr-adapter-sra | 0.1.4 | 30409 | `ca75b93ed9ec423925623d86117fa3e38ccb8d1edbc704e3987ff20c1ae3703c` |
| automas-script-hsr | 0.1.4 | 98708 | `1bb10ac859549fa845932aff489f915f7990c5142c19910b0e0cebe9341d34de` |

## r10 正式工作树契约

- Snapshot ID：`nexus-overdrive-all-plugins-v6.0.0-alpha.20260723.r10`
- Wheel manifest SHA256：`ca3ad7891abc169a572d2f37292fa08491faa4be8034adcdd7c29e87dfc96bee`
- Runtime lock SHA256：`f15269a82e41a728638d47404c380e36624290b7feb2f2beb24062798fbfb981`
- 晋升前 wheelhouse 备份：`D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\codex-wheelhouse-pre-r10-20260723`
- r10 构建与日志：`D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\codex-wheelhouse-r10-20260723`
- 冻结 r6 未被读取后写回、覆盖或删除。

## 已知边界

- wheel 已做到字节级可复现；4 个 sdist 仍未做到字节级可复现，不能宣称所有 Python 产物完全可复现。
- SRA 与 M7A 的托管更新 descriptor 仍明确为 `managed_enabled=False`；本次只交付了事务引擎和安全边界，未启用自动接管更新。
- 未启动真实游戏、真实 SRA/M7A、真实 GUI，也未模拟存储控制器断电；这些仍属于人工/硬件验证。
- r10 是当前源码快照的 wheelhouse 晋升，不代表 Config v2 authoritative、A 测安装包或正式候选已经完成。
