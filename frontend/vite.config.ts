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
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(packageJson.version)
  }
})
