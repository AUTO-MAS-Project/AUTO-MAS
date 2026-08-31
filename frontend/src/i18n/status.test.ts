import { describe, expect, it } from 'vitest'

import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

// useStatusLabel 依赖 Vue 组件上下文（useI18n），这里直接校验它依赖的词表契约：
// 每个状态值都要能在两套词表里找到对应条目，否则渲染时会退回显示原始中文。
const STATUS_VALUES = ['等待', '运行', '完成', '异常', '空闲', '结束'] as const
const STATUS_KEYS = ['waiting', 'running', 'done', 'error', 'idle', 'finished'] as const

describe('状态词表', () => {
  it('中文词表里每个 key 的译文就是后端/调度台实际使用的值', () => {
    // 这一条同时保证：切到中文时界面显示与改造前逐字一致
    const zh = zhCN.status as Record<string, string>
    expect(STATUS_KEYS.map(k => zh[k])).toEqual([...STATUS_VALUES])
  })

  it('英文词表覆盖了全部状态 key，没有漏项', () => {
    const en = enUS.status as Record<string, string>
    for (const key of STATUS_KEYS) {
      expect(en[key], `en-US 缺少 status.${key}`).toBeTruthy()
    }
  })

  it('两套词表的 status key 集合一致', () => {
    expect(Object.keys(enUS.status).sort()).toEqual(Object.keys(zhCN.status).sort())
  })
})
