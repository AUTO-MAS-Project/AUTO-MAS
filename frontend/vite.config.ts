import { defineConfig } from 'vite'
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
      // 渲染进程兜底端点用，正常仍以 Electron 下发的端点为准
      'import.meta.env.VITE_AUTO_MAS_HTTP_PORT': JSON.stringify(String(backendPort)),
    },
    // 开发服务器配置
    server: {
      port: DEV_SERVER_PORT,
      // 端口被占用时直接失败，避免静默换端口后 Electron 仍加载另一实例的页面
      strictPort: true,
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
  }
})
