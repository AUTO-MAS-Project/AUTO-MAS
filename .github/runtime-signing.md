# Runtime 构建签名配置

`build-sign-runtime.yml` 只构建签名 Runtime，不执行桌面应用发版。
Runtime 的 tag workflow 以完整 Commit 和 run id/attempt 发起请求，主仓库固定 `main`
运行，要求源码已合入 Runtime main、tag 对应同一 Commit，签名后回传 artifact。
Runtime 验签后自行发布自己的 GitHub/CNB Release。

## 配置

1. 在 SignPath 现有组织 `787a1d5f-6177-4f30-9559-d2646473584a`、项目 `AUTO_MAA`
   下新增专用 artifact configuration，XML 使用 [runtime.xml](../.signpath/runtime.xml)。
   按用户确认的实际配置，slug 为 `AUTO-MAS_Runtime`（下划线），工作流固定使用这个专用配置。
   签名 action 固定为 `c92b958760219087e01f8d67a1669ed57afe2627`（v2.3），
   `github-artifact-id` 使用上传步骤输出，`output-artifact-directory` 为 `signed`。
   确认 `release-signing` 允许主仓库 main 构建 Runtime 子项目；保持原有审批要求。
2. 主仓库保留 `SIGNPATH_API_TOKEN`；新增 secret `RUNTIME_SENTRY_DSN`，值复制自 Runtime
   仓库的 `AUTO_MAS_SENTRY_DSN`。它只通过构建步骤的同名环境变量注入 Runtime EXE，
   主仓库已有的桌面应用/后端 Sentry 配置不修改。缺少该值阻止构建，避免静默丢失 Runtime 观测配置。
3. 从现有签名证书读取 SHA-1 thumbprint，在两仓库设置 variable
   `RUNTIME_SIGNING_CERTIFICATE_THUMBPRINT`，40 位十六进制，无空格。可对已签名主程序运行：

   ```powershell
   (Get-AuthenticodeSignature -LiteralPath './AUTO-MAS.exe').SignerCertificate.Thumbprint
   ```

4. 创建仅授权主仓库的细粒度 PAT，权限 Actions read/write、Contents read，存入 Runtime
   secret `AUTO_MAS_SIGNING_TOKEN`；主仓库不用保存这个 PAT，也不需要 Runtime 写权限。
   如组织要求 PAT 审批，须先批准。token 不要发聊天或提交到文件。
5. 本工作流先随 dev 提交，由维护者合入 main。workflow_dispatch 要求工作流已存在于默认
   分支；全部配置就绪后再推新的 Runtime tag。

缺配置、签名失败或审批超时都阻止 Runtime 发布。签名等待 60 分钟，整体回传等待 90 分钟。
回传 EXE 已签名，Runtime 对最终字节重算 SHA256SUMS。历史 Release 不改写。
证书换发时同步更新两仓库 thumbprint；运行中的签名请求需要与同一证书配置一致。

## Code signing policy

免费代码签名由 [SignPath.io](https://signpath.io/) 提供，证书由
[SignPath Foundation](https://signpath.org/) 提供。提交与审查由 AUTO-MAS 项目维护团队负责，
签名审批沿用 `AUTO_MAA` 的 `release-signing` 策略。

参考：[GitHub 集成](https://docs.signpath.io/trusted-build-systems/github)、
[来源校验](https://docs.signpath.io/origin-verification/)。
