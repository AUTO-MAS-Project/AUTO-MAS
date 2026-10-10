import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./HomeCommandCard.vue', import.meta.url), 'utf8')

const styleRule = (selector: string) =>
  source.match(new RegExp(`\\${selector}\\s*\\{[^}]*\\}`))?.[0] ?? ''

describe('HomeCommandCard 底栏布局', () => {
  it('底栏撑满宽度、作者名吃掉剩余空间，刷新按钮不随作者名长短左右移动', () => {
    // 「换一句」换掉的是作者名，它是底栏里唯一会变宽的元素。底栏要是跟着伸缩，
    // 按钮就会被推着左右移动，鼠标停在按钮上的 tooltip 拿不到 mouseleave 而残留。
    const footer = styleRule('.command-footer')
    expect(footer).toContain('left: 0')
    expect(footer).toContain('right: 0')

    const author = styleRule('.command-author')
    expect(author).toContain('flex: 1')
  })
})
