import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// 读取主程序版本号
const versionJson = require('../res/version.json')

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
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
    chunkSizeWarningLimit: 5000,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Monaco 编辑器 (~3MB) 单独分包，不阻塞首屏
          if (id.includes('monaco-editor')) {
            return 'monaco'
          }
          // Ant Design Vue 组件库单独分包
          if (id.includes('ant-design-vue') || id.includes('@ant-design')) {
            return 'antd'
          }
          // Vue 生态核心库
          if (id.includes('node_modules/vue') || id.includes('node_modules/@vue')) {
            return 'vue-vendor'
          }
        },
      },
    },
  },
})
