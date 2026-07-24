# 证据索引

证据根目录：`D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\current-alpha-plugin-gate-20260724`

| 文件 | SHA-256 | 内容 |
| --- | --- | --- |
| `logs/01_wheelhouse_snapshot_strict.log` | `3add3e0216381dca3d10f249ad1571298699fdff9776568e0dacc8d69a61e370` | 当前 wheelhouse 严格快照验证 |
| `logs/02_tests_plugins.log` | `1eddd9b814564a0c866eb6422c34b038c2b1a658c460bd240a93649751209c0b` | `tests/plugins` |
| `logs/03_tests_plugin_blackbox.log` | `a10041b54136e1d3ad0a5eb5d697c550320eb54fe89bf4e411a1a7157854ebda` | 初次 `tests/plugin_blackbox` |
| `logs/03b_tests_plugin_blackbox_skip_reasons.log` | `3b2822653b39211ced5686036192a8fdad41699ca4dc383bf94c1ae9cf3b333a` | 相同测试及 skip 原因 |
| `logs/04_isolated_wheel_install.log` | `1a5dc2ad850cd7f36970d23b953231dc61637454dbbd95f5ecef1b08f8e79282` | 离线 venv 安装 127 wheel |
| `logs/05_safe_entrypoint_import.log` | `28f74c8bca263becaadf065c95445fdd00b4bc6f358f1f6bdc2a9588102cfad1` | 21 entry point 安全导入 |
| `safe_entrypoint_import.json` | `55eef8e66e99c9bb87f3dbbd82e4d68f5667b533af89da1cbffab670c5f83956` | 每个入口点的结构化结果 |
| `logs/06c_fake_host_lifecycle_retry2.log` | `b8437f188f6f12915d5194f8d404d2c456ffcecbb5272bb8a9e904f1bab034eb` | FakeHost 15 场景 |
| `fake_host_lifecycle_attempt3.json` | `a50e3503b56f3068f950b988049579615b006ea58de50b992d86b241bdfb77e3` | FakeHost 结构化汇总 |
| `logs/07_isolated_pip_check.log` | `bb9fb3b2a193142133a8d437df5d91ee1b8a247415380380c037a55dadff0170` | 隔离环境依赖闭合 |
| `logs/08_direct_reload_closed_repro.log` | `a648f18b2f46f15c71766fccaf7a4e08135d1b1316d38ce6a1f1880b89e2b3f4` | P1 mock-only 最小复现 |
| `direct_reload_closed_repro.json` | `d218feb10cf7af0167a8c5af76a29e19ce1a36bb09bfba208c826ade4d07ee5a` | P1 结构化结果 |

`fake_host_lifecycle.json`、`fake_host_lifecycle_attempt2.json` 记录了执行器初始对 Windows asyncio 本地 self-pipe 的过严 socket 防护失败；它们是测试基础设施失败，不是产品失败。最终有效生命周期结论只取 `attempt3` 及其 `06c` 日志。

隔离 venv、合成 fake wheel、缓存字节码均只位于证据根目录，未纳入索引的逐文件哈希不影响候选 wheelhouse 的原始哈希。
