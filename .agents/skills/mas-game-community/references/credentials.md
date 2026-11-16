# 游戏社区凭据、日志与错误消息边界

社区是本仓少数直接持有**用户账号密码**的路径，规则从严。凭据相关模块：`app/tools/common/community/credentials.py`（外形解析与本地校验分派）、`app/tools/common/community/sign.py`（`read_community_token`）、各平台适配器（真实上游认证与刷新）。

## 凭据规则

1. 所有凭据字段（含米游社设备 ID/指纹）必须加密落盘，新增字段没有例外：`Annotated[str, encrypted()]`。
2. 一次性登录请求的密码字段用 `SecretStr`，用 `.get_secret_value()` 取值，**不落盘、不进日志**。
3. 登录路由的 `except Exception` 分支**禁止** `exc_info` / `logger.exception` / 回显上游响应，只返回固定文案（参见 `login_taygedo` 的注释）。
4. 只有 `ValueError` 允许把消息带给用户（凭据不完整、格式错误等可预期原因）；其他异常统一返回泛化文案。
5. 登录成功后必须**校验凭据完整性**再落盘（塔吉多校验 `accessToken`/`refreshToken`/`uid`，森空岛校验 `oauthToken`/`token`/`cred`），缺字段视为登录失败。
6. 凭据刷新走 `_ProviderRun.credential_updates`：runner 内**不要**直接写配置；即时回写通过 `on_credential_update` 回调，收尾由编排层统一比对并重试。收尾写回前先重读存量，发现已被别的链路轮换即跳过写入。
7. 读取凭据统一用 `read_community_token()`：容忍旧账号对象缺少新增字段（`AttributeError` / `KeyError` 返回空串）。直接 `account.get(...)` 会在旧配置上炸。
8. 便笺链路只读：不得写回凭据、不得触发签到、不得改动 `LastSignDate`；快照里不允许出现凭据、Cookie、设备值。

## 日志与提示

1. 日志只允许出现凭据**字段名**与状态，不允许出现凭据值、Cookie 或上游原始响应；异常栈同理。
2. 上游异常原文可能带 Cookie：便笺侧只允许 `format_exception_reason(..., include_message=False)` 加上「调用位置」这类定位信息（见 `query_configured_community_activity` 的 `traceback.extract_tb` 用法）。
3. 扫码 `/check` 回传的单行状态文案是**唯一**允许的上游文本透传（仅限短状态文案），详见 [sign-in.md](sign-in.md) 的「已知不一致 6」。
4. 渠道级失败必须走系统提示（`Notify.push_system_notice`），不能只写日志：用户看不到日志就等于没有通知。
5. `results_saved=False` 时文案不得声称结果已保存；「结果无法确认」与「空结果」是两种终态，不要合并成「签到失败」。
