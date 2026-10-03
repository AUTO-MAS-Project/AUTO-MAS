import { describe, expect, it } from 'vitest'

import { isWaitingWithoutUsers } from './taskTreePresentation'

describe('任务总览脚本状态', () => {
  it('空用户表的等待脚本显示为等待运行', () => {
    expect(isWaitingWithoutUsers({ status: '等待', user_list: [] })).toBe(true)
  })

  it('真实账号名为暂未加载时仍按真实账号处理', () => {
    expect(
      isWaitingWithoutUsers({
        status: '等待',
        user_list: [{ name: '暂未加载' }],
      })
    ).toBe(false)
  })

  it('已有用户或已跳过脚本不显示等待运行', () => {
    expect(isWaitingWithoutUsers({ status: '跳过', user_list: [] })).toBe(false)
    expect(isWaitingWithoutUsers({ status: '等待', user_list: [{ name: '真实用户' }] })).toBe(false)
  })
})
