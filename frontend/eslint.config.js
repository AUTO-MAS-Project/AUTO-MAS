const vue = require('eslint-plugin-vue');
const ts = require('@typescript-eslint/eslint-plugin');
const tsParser = require('@typescript-eslint/parser');
const prettier = require('eslint-plugin-prettier');

module.exports = [
  // 推荐的 vue3 配置
  vue.configs['vue3-recommended'],
  // 推荐的 ts 配置
  ts.configs.recommended,
  // 推荐的 prettier 配置
  prettier.configs.recommended,
  // 自定义规则和文件范围
  {
    files: ['**/*.js', '**/*.ts', '**/*.vue'],
    ignores: ['dist/**', 'node_modules/**'],
    languageOptions: {
      parser: tsParser,
      ecmaVersion: 2021,
      sourceType: 'module',
    },
    plugins: {
      vue,
      '@typescript-eslint': ts,
      prettier,
    },
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      // 如果你希望 prettier 报错，取消注释下面一行
      // 'prettier/prettier': 'error',
    },
  },
];
