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

// https://vite.dev/config/
export default defineConfig({
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
  },
  // 开发服务器配置
  server: {
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
})
