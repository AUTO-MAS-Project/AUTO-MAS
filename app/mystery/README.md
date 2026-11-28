# 神秘小功能

本目录提供神秘入口所需的设备指纹与后端源码指纹计算。入口位于客户端「设置 → 功能设置」底部右侧，仅提供密钥输入（不展示或复制指纹）；解锁后可主动重新锁定，并于每日北京时间零点自动锁回。

## 8 位密钥协议

密钥仅作为可复算的本地轻量解锁门槛，不承担身份认证：

1. **设备指纹（`deviceHash`）**：取有效的 Windows SMBIOS UUID（小写标准格式），对 `auto-mas:mystery:device:v1|smbios|<UUID>` 计算 UTF-8 SHA-256。空值、全零、全 F 或读取失败时直接拒绝解锁。
2. **源码指纹（`backendHash`）**：扫描实际运行后端源码根目录下的 `main.py` 与 `app/**/*.py`（排除 `__pycache__`）。按 `/` 相对路径排序，换行统一为 LF，逐文件计算 SHA-256 后按 `相对路径 + NUL + 小写文件哈希 + LF` 拼入清单，以 `auto-mas:mystery:backend:v1\n` 为首段计算整体 SHA-256。
3. **密钥生成**：拼接 `mystery-v1|<deviceHash>|<backendHash>|<issuedAt>`（`issuedAt` 为十进制 UTC Unix 秒时间戳），计算 UTF-8 SHA-256，取前 6 字节做无填充 Base64URL 编码，得到区分大小写的 8 位密钥。
4. **有效期与状态复用**：
   - Electron 主进程校验当前秒至前 1799 秒（30 分钟内有效，拒绝未来时间）；解锁成功后将北京时间日期与两项指纹写入 `config/frontend_config.json`，当日零点前有效。
   - 后端读取同一份 `config/frontend_config.json` 复核解锁状态，使需要授权的附属插件（如 Token 获取）与入口页保持一致，未解锁时既不显示于市场也无法安装。

## 关联页面与实现位置

- 神秘入口首页与「Token 获取」子页面共用每日解锁状态（直接访问子页面同样要求已解锁）。
- 米游社、森空岛扫码登录及塔吉多账密登录前端位于 `frontend/src/views/mystery/tokens/`，复用现有社区登录接口（模型在 `app/models/schema.py`，路由在 `app/api/`），凭据直接保存至所选社区账号组。
- 库街区凭据获取引导用户使用 [Better-MAS-Tools（BMT）](https://github.com/Lance0174/Better-MAS-Tools)。
