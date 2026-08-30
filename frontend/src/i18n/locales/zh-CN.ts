//   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
//   Copyright © 2025-2026 AUTO-MAS Team

/**
 * 中文词表（源语言）。
 *
 * 新增条目时按界面区域分组，key 用小驼峰。译文以本文件为准，
 * en-US.ts 缺失的 key 会自动回退到这里。
 */
export default {
  common: {
    language: '语言',
    languageTip: '界面显示语言',
    languageSaveFailed: '语言设置保存失败，已恢复原语言',
  },
  status: {
    waiting: '等待',
    running: '运行',
    done: '完成',
    error: '异常',
    idle: '空闲',
    finished: '结束',
  },
  locale: {
    'zh-CN': '简体中文',
    'en-US': 'English',
  },
}
