import { describe, expect, it, vi } from 'vitest'
import {
  BACKGROUND_IMAGE_PROPERTY,
  INLINE_STYLE_VALUE_MAX,
  createAppearanceBackgroundApplier,
  dataUrlToBlob,
} from './appearanceBackground'

const SMALL = 'data:image/webp;base64,AAAA'
// 约 300 万字符，和 #1275 里那张 2.2 MB 的 PNG 同一量级
const LARGE = `data:image/png;base64,${'A'.repeat(3_000_000)}`

// 照 Chromium 的行为：超过上限的内联声明静默丢弃，旧值留着
function chromiumStyle() {
  const values = new Map<string, string>()
  return {
    setProperty: vi.fn((name: string, value: string) => {
      if (value.length <= INLINE_STYLE_VALUE_MAX) values.set(name, value)
    }),
    getPropertyValue: (name: string) => values.get(name) ?? '',
  }
}

function setup(style = chromiumStyle()) {
  let next = 0
  const createObjectURL = vi.fn((_blob: Blob): string => `blob:test/${++next}`)
  const revokeObjectURL = vi.fn((_url: string) => undefined)
  const logger = { error: vi.fn((_message: string) => undefined) }
  const apply = createAppearanceBackgroundApplier({ createObjectURL, revokeObjectURL, logger })
  const current = () => style.getPropertyValue(BACKGROUND_IMAGE_PROPERTY)
  return { style, apply, createObjectURL, revokeObjectURL, logger, current }
}

describe('dataUrlToBlob', () => {
  it('decodes base64 bytes and keeps the MIME type', async () => {
    const blob = dataUrlToBlob('data:image/png;base64,AQID')
    expect(blob?.type).toBe('image/png')
    expect([...new Uint8Array(await blob!.arrayBuffer())]).toEqual([1, 2, 3])
  })

  it('rejects anything that is not a base64 data URL', () => {
    expect(dataUrlToBlob('https://example.invalid/bg.png')).toBeNull()
    expect(dataUrlToBlob('data:image/png,raw')).toBeNull()
    expect(dataUrlToBlob('data:image/png;base64,***')).toBeNull()
  })
})

describe('createAppearanceBackgroundApplier', () => {
  it('switches from a small to an oversized background instead of keeping the old one', () => {
    const { style, apply, createObjectURL, current } = setup()
    apply(style, SMALL)
    expect(current()).toBe('url("blob:test/1")')

    apply(style, LARGE)
    expect(current()).toBe('url("blob:test/2")')

    // 交给 createObjectURL 的是解码后的图片本身：MIME 对、字节数对
    const [smallBlob, largeBlob] = createObjectURL.mock.calls.map(([blob]) => blob)
    expect(smallBlob.type).toBe('image/webp')
    expect(smallBlob.size).toBe(3)
    expect(largeBlob.type).toBe('image/png')
    expect(largeBlob.size).toBe(2_250_000)
  })

  it('does not rewrite the same background and releases the replaced object URL', () => {
    const { style, apply, revokeObjectURL, current } = setup()
    apply(style, SMALL)
    apply(style, SMALL)
    expect(style.setProperty).toHaveBeenCalledTimes(1)
    // 重复应用不能释放还在用的那个 URL
    expect(revokeObjectURL).not.toHaveBeenCalled()

    apply(style, LARGE)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test/1')
    apply(style, undefined)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test/2')
    expect(current()).toBe('none')
  })

  it('clears a write that did not take and retries on the next apply', () => {
    const values = new Map<string, string>()
    const style = {
      // 只认 none，模拟任何原因导致的写入没生效
      setProperty: vi.fn((name: string, value: string) => {
        if (value === 'none') values.set(name, value)
      }),
      getPropertyValue: (name: string) => values.get(name) ?? '',
    }
    const { apply, logger, revokeObjectURL, current } = setup(style)
    values.set(BACKGROUND_IMAGE_PROPERTY, 'url("blob:stale")')

    apply(style, SMALL)
    expect(current()).toBe('none')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test/1')
    expect(logger.error).toHaveBeenCalledTimes(1)

    style.setProperty.mockClear()
    apply(style, SMALL)
    expect(style.setProperty).toHaveBeenCalledWith(BACKGROUND_IMAGE_PROPERTY, 'url("blob:test/2")')
  })

  it('clears the old background when converting the new one throws, then retries', () => {
    const { style, apply, createObjectURL, revokeObjectURL, logger, current } = setup()
    apply(style, SMALL)
    createObjectURL.mockImplementationOnce(() => {
      throw new RangeError('Array buffer allocation failed')
    })

    expect(() => apply(style, LARGE)).not.toThrow()
    expect(current()).toBe('none')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test/1')
    expect(logger.error).toHaveBeenCalledTimes(1)

    apply(style, LARGE)
    expect(current()).toBe('url("blob:test/2")')
  })

  it('writes none first when there is no background', () => {
    const { style, apply, createObjectURL, current } = setup()
    apply(style, undefined)
    expect(current()).toBe('none')
    expect(createObjectURL).not.toHaveBeenCalled()
  })
})
