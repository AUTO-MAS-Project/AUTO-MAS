import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// 读取主程序版本号
const versionJson = require('../res/version.json')

/** Keep optional heavy runtimes outside the application entry chunk. */
export function resolveVendorChunk(moduleId: string): string | undefined {
  const normalizedId = moduleId.replace(/\\/g, '/')
  if (!normalizedId.includes('/node_modules/')) {
    return undefined
  }
  if (
    normalizedId.includes('/monaco-editor/') ||
    normalizedId.includes('/@guolao/vue-monaco-editor/')
  ) {
    return 'vendor-monaco'
  }
  if (normalizedId.includes('/three/')) {
    return 'vendor-three'
  }
  if (normalizedId.includes('/matter-js/')) {
    return 'vendor-matter'
  }
  if (normalizedId.includes('/markdown-it/')) {
    return 'vendor-markdown'
  }
  // Vue and Ant Design Vue share runtime helpers. Splitting them into two
  // explicit chunks can make Rollup emit a vendor-vue <-> vendor-antd cycle,
  // which crashes the packaged renderer before Vue mounts.
  if (
    normalizedId.includes('/ant-design-vue/') ||
    normalizedId.includes('/@ant-design/icons-vue/') ||
    normalizedId.includes('/vue/') ||
    normalizedId.includes('/vue-router/') ||
    normalizedId.includes('/@vueuse/') ||
    normalizedId.includes('/pinia/')
  ) {
    return 'vendor-ui'
  }
  return undefined
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  base: './',
  resolve: {
    extensions: ['.js', '.ts', '.vue', '.json'],
    alias: {
      '@': path.resolve(__dirname, './src'),
      'ant-design-vue': path.resolve(__dirname, './node_modules/ant-design-vue'),
      vue: path.resolve(__dirname, './node_modules/vue/dist/vue.runtime.esm-bundler.js'),
    },
  },
  define: {
    // 在编译时将版本号注入到环境变量中
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(versionJson.version),
  },
  // 开发服务器配置
  server: {
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
    watch: {
      // 只排除构建产物，environment 不会被 Vite 监听（因为没有被 import）
      ignored: ['**/node_modules/**', '**/dist/**', '**/dist-electron/**'],
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: resolveVendorChunk,
      },
    },
  },
})
