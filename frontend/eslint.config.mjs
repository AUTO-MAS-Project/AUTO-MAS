// eslint.config.mjs
import path from 'path'
import { fileURLToPath } from 'url'

import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
import prettierPlugin from 'eslint-plugin-prettier'
import configPrettier from 'eslint-config-prettier'
import globals from 'globals'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default [
  // 基础 JS 推荐规则
  js.configs.recommended,

  // Vue 3 推荐规则（内部使用 vue-eslint-parser）
  ...vue.configs['flat/recommended'],

  // -------- 渲染端（Vite + Vue）类型感知 ----------
  {
    files: ['src/**/*.{ts,tsx,vue}', 'vite.config.ts'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        extraFileExtensions: ['.vue'],
        // 让 <script lang="ts"> 用 TS 解析器
        parser: tseslint.parser,
        project: [path.join(__dirname, 'tsconfig.app.json')],
        tsconfigRootDir: __dirname,
      },
    },
    plugins: { '@typescript-eslint': tseslint.plugin },
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },

  // -------- Electron 主进程/预加载 ----------
  {
    files: ['electron/**/*.ts'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: globals.node,
      parserOptions: {
        project: [path.join(__dirname, 'tsconfig.electron.json')],
        tsconfigRootDir: __dirname,
      },
    },
    plugins: { '@typescript-eslint': tseslint.plugin },
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },

  // -------- 公共 JS/配置文件 ----------
  {
    files: ['public/**/*.js', 'eslint.config.mjs'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
    },
  },

  // -------- 全局规则调整 ----------
  {
    rules: {
      // 关掉换行符报错
      'linebreak-style': 'off',
    },
  },

  // -------- Prettier 集成 ----------
  {
    plugins: { prettier: prettierPlugin },
    rules: {
      // Prettier 错误当成 ESLint 错误
      'prettier/prettier': ['error', { endOfLine: 'auto' }],
    },
  },
  configPrettier,

  // 忽略产物目录
  {
    ignores: ['dist/**', 'dist-electron/**', 'out/**', 'build/**', 'node_modules/**', '**/*.d.ts'],
  },
]
