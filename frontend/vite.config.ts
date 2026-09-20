import { configDefaults, defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import path from 'path'

// 读取主程序版本号
const versionJson = require('../res/version.json')
const sentryAuthToken = process.env.SENTRY_AUTH_TOKEN
const sentryOrg = process.env.SENTRY_ORG
const sentryProject = process.env.SENTRY_PROJECT
const sentryRelease = `auto-mas@${versionJson.version}`

if (sentryAuthToken && (!sentryOrg || !sentryProject)) {
  throw new Error('SENTRY_AUTH_TOKEN 存在时必须同时设置 SENTRY_ORG 和 SENTRY_PROJECT')
}

// 仅在构建环境提供 Sentry 凭据时上传，避免本地构建依赖 Sentry 认证。
const sentryUploadPlugin = sentryAuthToken
  ? sentryVitePlugin({
      org: sentryOrg,
      project: sentryProject,
      authToken: sentryAuthToken,
      release: {
        name: sentryRelease,
        setCommits: {
          auto: true,
          ignoreMissing: true,
          ignoreEmpty: true,
        },
      },
      sourcemaps: {
        filesToDeleteAfterUpload: ['dist/**/*.map'],
      },
    })
  : undefined

// 后端端口与 main.py、electron/services/instanceConfig.ts 保持一致：
// dev server 对应开发环境后端，构建产物对应正式版后端
const DEFAULT_HTTP_PORT = 36163
const DEV_HTTP_PORT = 36164
// 与 package.json 中 electron-dev 的 VITE_DEV_SERVER_URL 对齐，需要错开时用 vite --port 覆盖
const DEV_SERVER_PORT = 5173

const parsePort = (value: string | undefined): number | undefined => {
  if (!value || !/^\d+$/.test(value.trim())) {
    return undefined
  }
  const port = Number(value.trim())
  return port >= 1 && port <= 65535 ? port : undefined
}

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  const backendPort =
    parsePort(process.env.AUTO_MAS_HTTP_PORT) ??
    (command === 'serve' ? DEV_HTTP_PORT : DEFAULT_HTTP_PORT)

  return {
    plugins: [vue(), tailwindcss(), ...(sentryUploadPlugin ? [sentryUploadPlugin] : [])],
    base: './',
    resolve: {
      extensions: ['.js', '.ts', '.vue', '.json'],
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    define: {
      // 在编译时将版本号注入到环境变量中
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(versionJson.version),
      // res/ 不进 Electron 产物，当前版本的更新日志也在编译期注入；只打当前这一段
      'import.meta.env.VITE_APP_CHANGELOG': JSON.stringify(
        versionJson.version_info?.[versionJson.version] ?? {}
      ),
      // 合并即入账的条目先放在「未发布」段，开发构建里一并展示；发布构建来自 tag，没有这一段
      'import.meta.env.VITE_APP_CHANGELOG_UNRELEASED': JSON.stringify(
        versionJson.version_info?.['未发布'] ?? {}
      ),
      // 渲染进程兜底端点用，正常仍以 Electron 下发的端点为准
      'import.meta.env.VITE_AUTO_MAS_HTTP_PORT': JSON.stringify(String(backendPort)),
    },
    // 开发服务器配置
    server: {
      // 钉死 IPv4：localhost 解析随环境漂移（本机 vite 曾只绑 ::1，而 wait-on 经 Node 访问
      // IPv6 回环被拒），host 需与 electron-dev 的 wait-on/VITE_DEV_SERVER_URL 同为 127.0.0.1
      host: '127.0.0.1',
      port: DEV_SERVER_PORT,
      // 端口被占用时直接失败，避免静默换端口后 Electron 仍加载另一实例的页面
      strictPort: true,
      // dev 模块响应禁用一切 HTTP 缓存：no-cache 仍允许浏览器存储旧响应、部分场景
      // 不回源校验，曾导致渲染层加载陈旧模块（页面结构与最新代码拼接的诡异状态）
      headers: { 'Cache-Control': 'no-store' },
      watch: {
        // 只排除构建产物，environment 不会被 Vite 监听（因为没有被 import）
        ignored: ['**/node_modules/**', '**/dist/**', '**/dist-electron/**'],
      },
    },
    build: {
      // 优化构建性能
      chunkSizeWarningLimit: 5000, // 提高到 5MB，适合 Electron 应用
      sourcemap: 'hidden', // 生成供 Sentry 上传的 sourcemap，但不在生产 JS 中暴露引用
    },
    test: {
      // dist-electron 是 Electron 主进程的 CJS 编译产物（源测试在 electron/），
      // 编译后的 require('vitest') 无法运行，不排除会让 yarn test 随构建必然失败
      exclude: [...configDefaults.exclude, '**/dist-electron/**'],
    },
  }
})
