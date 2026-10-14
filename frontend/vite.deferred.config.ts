import { configDefaults, defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@deferred': path.resolve(__dirname, 'deferred/src'),
    },
  },
  test: {
    include: ['deferred/**/*.test.ts'],
    exclude: configDefaults.exclude,
  },
})
