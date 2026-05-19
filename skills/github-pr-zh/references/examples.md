# Pull Request 示例

规范见 [guide.md](./guide.md)。

---

## 冗长版（应避免）

多段背景、架构说明、变更文件列表、详细 Test plan 十项 checkbox。

---

## 精简版（推荐）

```markdown
## 摘要

- 用户编辑页新增「打开配置文件夹」，调用后端解析路径并用 Electron 打开资源管理器
- 新增 `POST /api/scripts/user/config-dir`
- 通用 / MAA / SRC / MaaEnd 用户编辑页均已接入

Closes #185
```
