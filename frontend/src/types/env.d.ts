/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 编译期从 res/version.json 注入的主程序版本号（见 vite.config.ts define） */
  readonly VITE_APP_VERSION: string
  /** 编译期注入的当前版本更新日志：分类 -> 条目，res/version.json 里没有该版本段时为空对象 */
  readonly VITE_APP_CHANGELOG: Record<string, string[]>
  /** 编译期注入的「未发布」段（合并即入账、还没进任何版本的条目），没有时为空对象 */
  readonly VITE_APP_CHANGELOG_UNRELEASED: Record<string, string[]>
  /** 渲染进程兜底的后端端口 */
  readonly VITE_AUTO_MAS_HTTP_PORT: string
}
