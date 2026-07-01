import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// 读取package.json中的版本号
const packageJson = require('./package.json')

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  base: './',
  resolve: {
    extensions: ['.js', '.ts', '.vue', '.json'],
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  define: {
    // 在编译时将版本号注入到环境变量中
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(packageJson.version),
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
    sourcemap: false, // 生产环境不生成 sourcemap，加快构建
  },
})
