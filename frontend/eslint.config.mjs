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
  // 基础 JS
  js.configs.recommended,

  // Vue 3（这里已经把 parser 设成了 vue-eslint-parser，不要再覆盖它）
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
        // 关键：让 .vue 的 <script lang="ts"> 用 TS 解析器
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

  // -------- Electron 主进程/预加载（Node/CJS 输出） ----------
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
    // 对纯 .ts 文件，TS 解析器由 typescript-eslint 的 flat preset 自动处理；
    // 这里不重复指定 languageOptions.parser，避免与 vue 的 parser 冲突。
    plugins: { '@typescript-eslint': tseslint.plugin },
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },

  // -------- 仅 JS 的公共脚本/配置（用默认 espree 即可） ----------
  {
    files: ['public/**/*.js', 'eslint.config.mjs'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
    },
  },

  // Prettier 集成与去冲突
  { plugins: { prettier: prettierPlugin }, rules: { 'prettier/prettier': 'error' } },
  configPrettier,

  // 忽略产物
  {
    ignores: ['dist/**', 'dist-electron/**', 'out/**', 'build/**', 'node_modules/**', '**/*.d.ts'],
  },
]
