# AUTO-MAS v6 Alpha 全插件自动门禁：快照

## 边界

- 审计工作树：`D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration`
- 分支：`integration/dev-v2-dev-all-plugins`
- 基线 HEAD：`b5e872815a3ea5eef81fc3fd34eb0dc71db32d4e`
- 运行窗口：2026-07-24 03:24–03:42（Asia/Shanghai）
- 冻结 r6：只读，未访问写入路径。
- 写入范围：仅 `_alpha_build\a1\current-alpha-plugin-gate-20260724` 与本目录；未修改共享源码、正式 wheelhouse、dist 或 release。

## 共享工作树状态

开始时工作树已经很脏，且存在并行开发。03:36 的再次采样仍为同一 HEAD，但有 262 条 `git status --short` 记录，状态文本 SHA-256 为：

`9abe6177cf9a34ce50b943e625f1c903b64625ac418aad9176cc653f64d9d1cb`

因此，所有结论只绑定下列实测输入哈希；任何相关文件变化后都应重跑受影响门禁，不能把本报告直接沿用为新源码的通过证明。

| 输入 | 字节 | SHA-256 |
| --- | ---: | --- |
| `res/integration-snapshot.json` | 2,089 | `cdee8f17a13f5a86d27ad5c771a830aa02b6cb99cfaf4c9bfee939dbb2a91a4a` |
| `plugins/wheels/manifest.json` | 116,067 | `ca3ad7891abc169a572d2f37292fa08491faa4be8034adcdd7c29e87dfc96bee` |
| `plugins/wheels/runtime-lock.json` | 94,091 | `f15269a82e41a728638d47404c380e36624290b7feb2f2beb24062798fbfb981` |
| `pyproject.toml` | 3,203 | `ece387a38139507fd906f4200efd1b47527bb711be5c18afc81f5c484655758a` |
| `scripts/verify_wheelhouse_snapshot.py` | 12,064 | `2bff40cd131644e3f30fdba70368223434ead25540c56e8f23639fae962f2902` |

## P1 调用链源码固定点

| 文件 | SHA-256 |
| --- | --- |
| `app/plugins/loader.py` | `0d9ed05ed612e1e0828c5b17f46df1b9c1ec6991456eef3395b628fdb768ec19` |
| `app/plugins/manager.py` | `9198223e38cddd34246454ad9b70db096a0aa61c2ff9a31ab28a68ab83e01e22` |
| `app/api/plugins.py` | `12c71a025d441d9a4bafc8508f5f4d4f7d17577320723bdd2a50ef52628fc54b` |
| `tests/chaos/test_plugin_lifecycle.py` | `6753e896a9e3de6c76e96a524a58a3d25742363803d4f1f148c7dbe1d25640eb` |
| `tests/plugins/test_plugin_lifecycle_fixes.py` | `3ecbe7ca20da0dd8b153d6679dd68135baeea373563899e4d98e8680bcc1bdd9` |
| `tests/plugin_blackbox/harness/case_runner.py` | `dba7b592710ea090793ecb1d9c25233dd46715e4992f7bf70228173fea00e345` |
