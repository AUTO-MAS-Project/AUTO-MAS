# Runtime 构建与签名配置

`.github/workflows/build-sign-runtime.yml` 专门负责构建并签名 Runtime（不执行桌面端发版）。Runtime 仓库的 tag 工作流携带完整 Commit SHA 与 run id/attempt 触发主仓库 `main` 分支执行签名，回传产物后由 Runtime 仓库验签并自行发布 GitHub / CNB Release。

## 一次性接入配置

1. **SignPath Artifact 配置**：在 SignPath 组织 `787a1d5f-6177-4f30-9559-d2646473584a` / 项目 `AUTO_MAA` 下使用 [.signpath/runtime.xml](../.signpath/runtime.xml) 创建专用配置，slug 固定为 `AUTO-MAS_Runtime`；确认 `release-signing` 策略允许主仓库 `main` 构建并保持审批要求。
2. **主仓库 Secrets**：保留 `SIGNPATH_API_TOKEN`，新增 `RUNTIME_SENTRY_DSN`（值取自 Runtime 仓库的 `AUTO_MAS_SENTRY_DSN`，构建时注入 Runtime EXE；缺失则阻止构建）。
3. **证书指纹 Variable**：在两个仓库均设置 `RUNTIME_SIGNING_CERTIFICATE_THUMBPRINT`（40 位无空格十六进制 SHA-1），可从已签名主程序读取：

   ```powershell
   (Get-AuthenticodeSignature -LiteralPath './AUTO-MAS.exe').SignerCertificate.Thumbprint
   ```

4. **跨仓触发 Token**：创建仅授权主仓库 `Actions: read/write`、`Contents: read` 的细粒度 PAT，存入 Runtime 仓库 secret `AUTO_MAS_SIGNING_TOKEN`（主仓库无需保存）。
5. **启用顺序**：工作流需由维护者合入主仓库默认分支 `main` 后，再推送新的 Runtime tag。

> 签名等待超时 60 分钟，整体回传超时 90 分钟；任一配置缺失、签名失败或审批超时都会阻断发布。证书换发时须同步更新两个仓库的 thumbprint。

## Code Signing Policy

免费代码签名由 [SignPath.io](https://signpath.io/) 提供，证书由 [SignPath Foundation](https://signpath.org/) 提供，审批沿用 AUTO-MAS 维护团队的 `release-signing` 策略。

参考：[SignPath GitHub 集成](https://docs.signpath.io/trusted-build-systems/github) · [来源校验](https://docs.signpath.io/origin-verification/)
