// eslint.config.js
import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
import prettierPlugin from 'eslint-plugin-prettier'
import configPrettier from 'eslint-config-prettier'
import globals from 'globals'

export default [
  // JS 基础规则
  js.configs.recommended,

  // Vue 3 推荐（flat）
  ...vue.configs['flat/recommended'],

  // TS 推荐（flat，含 parser/overrides）
  ...tseslint.configs.recommended,

  // 通用语言选项
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        // 使用项目服务以正确处理多 tsconfig（比单个 project 性能更好）
        projectService: true,
        tsconfigRootDir: new URL('.', import.meta.url),
        extraFileExtensions: ['.vue'],
      },
    },
  },

  // .vue 中的 <script lang="ts"> 也交给 TS 解析（保险做法）
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },

  // 电子主进程/预加载（按你项目路径再调）
  {
    files: ['electron/**/*.ts', 'src/preload.ts', 'src/main.ts'],
    languageOptions: {
      globals: globals.node,
    },
  },

  // 自定义规则
  {
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },

  // Prettier 作为 ESLint 报错输出
  {
    plugins: { prettier: prettierPlugin },
    rules: {
      'prettier/prettier': 'error',
    },
  },

  // 关闭与 Prettier 冲突的所有规则（一定放在靠后）
  configPrettier,

  // 忽略项
  {
    ignores: ['dist/**', 'dist-electron/**', 'out/**', 'build/**', 'node_modules/**', '**/*.d.ts'],
  },
]
