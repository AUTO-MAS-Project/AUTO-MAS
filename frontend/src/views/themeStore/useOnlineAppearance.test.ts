import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import type { OnlineAppearanceItem } from '@/types/appearance'
import { useOnlineAppearance } from './useOnlineAppearance'

vi.mock('@/utils/preferenceAnalytics', () => ({ appearanceCategory: (kind: string) => kind }))
vi.mock('@/utils/dateDisplay', () => ({ formatBackendDateTime: (value: string) => value }))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('@/utils/analytics', () => ({ beginAnalyticsOperation: () => ({ finish: vi.fn() }) }))

afterEach(() => vi.unstubAllGlobals())

describe('资源商店按需下载', () => {
  it('浏览详情和切换版本只取封面，安装才准备所选版本并复用缓存', async () => {
    const item: OnlineAppearanceItem = {
      fileKey: 'example',
      displayName: 'Example',
      description: '',
      ownerUsername: 'author',
      publishedVersionNo: 2,
      publishedAt: '',
      updatedAt: '',
      installed: null,
      hasCover: true,
    }
    const prepare = vi.fn(async () => ({
      success: true,
      token: 'prepared',
      appearance: { id: 'example', name: 'Example' },
    }))
    const cover = vi.fn(async () => ({ success: true, dataUrl: 'data:image/png;base64,preview' }))
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => ({ warn: vi.fn(), error: vi.fn() }),
        getOnlineAppearance: async () => ({
          success: true,
          item,
          versions: [1, 2].map(versionNo => ({
            versionNo,
            fileSize: 100,
            sha256: 'a'.repeat(64),
            createdAt: '',
            changeNote: '',
            hasCover: true,
          })),
        }),
        getOnlineAppearanceCover: cover,
        prepareOnlineAppearance: prepare,
        discardOnlineAppearance: vi.fn(),
      },
    })
    const install = vi.fn(async () => 'cancelled' as const)
    const store = useOnlineAppearance({ install, categoryKey: 'mascot' })
    await store.openDetail(item)
    store.selectVersion(1)
    await Promise.resolve()
    expect(cover).toHaveBeenCalledWith('example', 1, 'mascot')
    expect(prepare).not.toHaveBeenCalled()
    await store.install()
    expect(prepare).toHaveBeenCalledExactlyOnceWith('example', 1, 'mascot')
    expect(install).toHaveBeenCalledWith('prepared')
    await store.install()
    expect(prepare).toHaveBeenCalledTimes(1)
    store.reset()
  })
})
