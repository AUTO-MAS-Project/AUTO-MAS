# 后端测试

后端测试统一使用 pytest 并按功能域组织。局部改动默认只运行受影响的文件或目录，不因提交 PR 自动运行全量测试。

## 目录

| 目录 | 覆盖范围 |
| --- | --- |
| `game_sign/` | 游戏签到、二维码登录、签到通知与定时触发 |
| `update/` | 更新 API、下载与更新源切换 |
| `notification/` | 通用通知服务 |
| `config/` | 配置基类与持久化 |
| `history/` | 历史记录与统计文件 |
| `runtime/` | 主程序启动与运行环境 |
| `scheduler/` | 任务停止、WebSocket 与调度生命周期 |
| `scripts/<type>/` | MAA、MaaEnd、Okww 等专项适配 |

同一功能跨越 API、core、service 或 tool 时仍放在同一功能域，不再按技术层拆散。

## 准入规则

测试文件应至少覆盖以下一项：

- 用户可观察缺陷的稳定回归场景；
- API、配置、持久化或任务生命周期的稳定契约；
- 容易在跨模块修改中再次破坏的关键流程。

以下内容不提交到仓库：

- 仅用于定位问题、试跑数据或验证迁移的一次性脚本；
- 只绑定当前实现细节且不代表稳定契约的断言；
- 已被同一功能域现有测试等价覆盖的重复用例。

测试应可离线、可重复执行，不依赖真实账号、外部服务或本机 GUI。生产代码改动不强制新增测试；已有覆盖足够或改动不适合自动化时，在 PR 中说明实际验证方式即可。

## 选择测试

按改动范围选择最小命令，并使用仓库内临时目录：

```powershell
# 单个行为
python -m pytest tests/<domain>/test_<feature>.py -q --basetemp=test-results/<scope>

# 一个功能域
python -m pytest tests/<domain> -q --basetemp=test-results/<domain>

# 一个专项
python -m pytest tests/scripts/<type> -q --basetemp=test-results/<type>
```

只有以下情况才在本地运行 `python -m pytest tests -q --basetemp=test-results/all`：

- 修改测试框架、目录结构或公共测试配置；
- 修改会影响多数功能域的全局基础设施；
- CI、维护者或任务明确要求全量验证。

跨域改动分别运行相关目录即可。PR 正文记录实际命令和结果；遇到既有失败时单独说明，不要为追求全绿扩大当前改动范围。
