import { describe, expect, it } from 'vitest'
import { HOME_GREETING_MESSAGES, pickHomeGreeting } from './homeGreeting'

describe('首页问候语', () => {
  // 「换一句」不能换出一模一样的句子，否则用户会以为按钮没生效
  it('换一句时不会抽到当前这句', () => {
    for (const current of HOME_GREETING_MESSAGES) {
      for (let round = 0; round < 20; round += 1) {
        expect(pickHomeGreeting(current.text).text).not.toBe(current.text)
      }
    }
  })

  it('抽到的句子一定来自文案池', () => {
    expect(HOME_GREETING_MESSAGES).toContain(pickHomeGreeting())
    expect(HOME_GREETING_MESSAGES).toContain(pickHomeGreeting('池子里没有的句子'))
  })
})
