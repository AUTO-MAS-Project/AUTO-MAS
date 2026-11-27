import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { OnlineAppearanceItem, OnlineAppearanceListResult } from '@/types/appearance'
import type { AppearanceCategory } from '@/types/mascotPack'
import { loadAllOutdatedOnlineAppearances } from './appearanceCatalog'

const {
  saveConfigMock,
  setAppearanceMock,
  installOnlineThemeMock,
  messageSuccessMock,
  modalConfirmMock,
} = vi.hoisted(() => ({
  saveConfigMock: vi.fn(async (_patch?: { desktopMascotId?: string }) => undefined),
  setAppearanceMock: vi.fn(async (_id?: string) => undefined),
  installOnlineThemeMock: vi.fn(async (_token: string, _replace?: boolean) => ({
    success: true as boolean,
    code: undefined as string | undefined,
    existing: undefined as { id: string; name: string } | undefined,
    appearance: {
      id: 'theme-b',
      name: '主题 B',
      mode: 'light' as const,
      tokens: { colorPrimary: '#1677ff' },
    },
  })),
  messageSuccessMock: vi.fn(),
  modalConfirmMock: vi.fn((opts?: { onCancel?: () => void }) => {
    opts?.onCancel?.()
    return { destroy: vi.fn() }
  }),
}))

vi.mock('ant-design-vue', () => ({
  message: {
    success: messageSuccessMock,
    warning: vi.fn(),
    error: vi.fn(),
  },
  Modal: {
    useModal: () => [
      {
        confirm: modalConfirmMock,
        info: vi.fn(() => ({ destroy: vi.fn() })),
      },
      () => null,
    ],
  },
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('@/i18n', () => ({
  translate: (key: string) => key,
}))

vi.mock('@/utils/analytics', () => ({
  beginAnalyticsOperation: () => ({ finish: vi.fn() }),
}))

vi.mock('@/utils/preferenceAnalytics', () => ({
  appearanceCategory: (category: string) => category,
}))

vi.mock('@/utils/config', () => ({
  saveConfig: saveConfigMock,
}))

vi.mock('@/stores/appearanceTryOn', () => ({
  useAppearanceTryOnStore: () => ({
    active: false,
    session: null,
    start: vi.fn(),
  }),
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({
    themeMode: { value: 'light' },
    themeColor: { value: 'blue' },
    themeColors: {},
    appearances: { value: [] },
    appearanceId: { value: 'theme-a' },
    activeAppearance: { value: null },
    setThemeMode: vi.fn(),
    setThemeColor: vi.fn(),
    resetTheme: vi.fn(),
    setAppearance: setAppearanceMock,
    importAppearance: vi.fn(),
    installOnlineAppearance: installOnlineThemeMock,
    removeAppearance: vi.fn(),
  }),
}))

const makeItem = (
  overrides: Partial<OnlineAppearanceItem> & { fileKey: string }
): OnlineAppearanceItem => ({
  displayName: overrides.fileKey,
  description: '',
  ownerUsername: 'tester',
  publishedVersionNo: 2,
  publishedAt: '2026-11-26T00:00:00Z',
  updatedAt: '2026-11-26T00:00:00Z',
  installed: null,
  hasCover: true,
  ...overrides,
})

describe('资源商店全量待更新扫描与批量更新边界', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    const logger = {
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    }
    ;(globalThis as unknown as { window: unknown }).window = {
      electronAPI: {
        getLogger: () => logger,
        listOnlineAppearances: vi.fn(),
        prepareOnlineAppearance: vi.fn(),
        installOnlineAppearance: vi.fn(),
        discardOnlineAppearance: vi.fn(async () => ({ success: true })),
      },
    }
  })

  it('全量扫描跨分类、跨分页收集全部待更新项，不受搜索词和首屏每页条数限制', async () => {
    const queries: Array<{ page?: number; pageSize?: number; keyword?: string; category: string }> =
      []
    const list = async (
      query: { page?: number; pageSize?: number; keyword?: string },
      category: AppearanceCategory
    ): Promise<OnlineAppearanceListResult> => {
      queries.push({ ...query, category })
      if (category === 'theme' && query.page === 1) {
        return {
          success: true,
          items: [
            makeItem({
              fileKey: 'theme-p1-outdated',
              publishedVersionNo: 3,
              installed: { appearanceId: 'theme-1', versionNo: 1 },
            }),
            makeItem({
              fileKey: 'theme-p1-current',
              publishedVersionNo: 2,
              installed: { appearanceId: 'theme-2', versionNo: 2 },
            }),
          ],
          pagination: { page: 1, pageSize: 50, total: 52, hasNext: true },
        }
      }
      if (category === 'theme' && query.page === 2) {
        return {
          success: true,
          items: [
            makeItem({
              fileKey: 'theme-p2-outdated',
              publishedVersionNo: 4,
              installed: { appearanceId: 'theme-3', versionNo: 2 },
            }),
          ],
          pagination: { page: 2, pageSize: 50, total: 52, hasNext: false },
        }
      }
      return {
        success: true,
        items: [
          makeItem({
            fileKey: 'mascot-b',
            publishedVersionNo: 2,
            installed: { appearanceId: 'mascot-b', versionNo: 1 },
          }),
          makeItem({
            fileKey: 'mascot-c',
            publishedVersionNo: 3,
            installed: { appearanceId: 'mascot-c', versionNo: 1 },
          }),
        ],
        pagination: { page: 1, pageSize: 50, total: 2, hasNext: false },
      }
    }

    const result = await loadAllOutdatedOnlineAppearances(list)
    expect(result.complete).toBe(true)
    expect(result.items.map(item => `${item.categoryKey}:${item.fileKey}`)).toEqual([
      'theme:theme-p1-outdated',
      'theme:theme-p2-outdated',
      'mascot:mascot-b',
      'mascot:mascot-c',
    ])
    expect(queries.every(query => query.keyword === undefined)).toBe(true)
  })

  it('批量更新多个未启用的桌宠与主题时更新包体但不覆盖当前选中的桌宠 A，单独安装仍保持切换行为', async () => {
    const installedVersions = new Map<string, number>([
      ['mascot-a', 1],
      ['mascot-b', 1],
      ['mascot-c', 1],
    ])
    let activeMascotId = 'mascot-a'

    saveConfigMock.mockImplementation(async (patch?: { desktopMascotId?: string }) => {
      if (patch?.desktopMascotId) activeMascotId = patch.desktopMascotId
    })

    const electronAPI = (
      globalThis as unknown as {
        window: {
          electronAPI: {
            listOnlineAppearances: ReturnType<typeof vi.fn>
            prepareOnlineAppearance: ReturnType<typeof vi.fn>
            installOnlineAppearance: ReturnType<typeof vi.fn>
          }
        }
      }
    ).window.electronAPI

    electronAPI.listOnlineAppearances.mockImplementation(
      async (_query: unknown, category: AppearanceCategory) => {
        if (category === 'theme') {
          return {
            success: true,
            items: [],
            pagination: { page: 1, pageSize: 50, total: 0, hasNext: false },
          }
        }
        return {
          success: true,
          items: [
            makeItem({
              fileKey: 'mascot-a',
              publishedVersionNo: 1,
              installed: {
                appearanceId: 'mascot-a',
                versionNo: installedVersions.get('mascot-a') ?? 1,
              },
            }),
            makeItem({
              fileKey: 'mascot-b',
              publishedVersionNo: 2,
              installed: {
                appearanceId: 'mascot-b',
                versionNo: installedVersions.get('mascot-b') ?? 1,
              },
            }),
            makeItem({
              fileKey: 'mascot-c',
              publishedVersionNo: 3,
              installed: {
                appearanceId: 'mascot-c',
                versionNo: installedVersions.get('mascot-c') ?? 1,
              },
            }),
          ],
          pagination: { page: 1, pageSize: 50, total: 3, hasNext: false },
        }
      }
    )

    electronAPI.prepareOnlineAppearance.mockImplementation(
      async (fileKey: string, versionNo: number) => ({
        success: true,
        token: `tok:${fileKey}:${versionNo}`,
        appearance: { id: fileKey, name: fileKey },
      })
    )

    electronAPI.installOnlineAppearance.mockImplementation(
      async (token: string, replace: boolean) => {
        const [, id, versionText] = token.split(':')
        if (!replace) {
          return { success: false, code: 'DUPLICATE_ID', existing: { id, name: id } }
        }
        installedVersions.set(id, Number(versionText))
        return { success: true, mascot: { id, name: id } }
      }
    )

    const { useAppearanceSettings } = await import('@/views/setting/useAppearanceSettings')
    const { useOutdatedAppearances } = await import('./useOutdatedAppearances')
    const { installPreparedOnlineAppearance } = useAppearanceSettings()
    const outdated = useOutdatedAppearances({
      install: (token, category, opts) => installPreparedOnlineAppearance(token, category, opts),
    })

    await outdated.refresh()
    expect(outdated.items.value.map(item => item.fileKey)).toEqual(['mascot-b', 'mascot-c'])

    const summary = await outdated.updateAll()
    expect(summary).toEqual({ succeeded: 2, failed: 0 })
    // B 和 C 都已升级到最新版本
    expect(installedVersions.get('mascot-b')).toBe(2)
    expect(installedVersions.get('mascot-c')).toBe(3)
    // 当前启用的桌宠仍是 A，批量更新不写入 desktopMascotId
    expect(activeMascotId).toBe('mascot-a')
    expect(saveConfigMock).not.toHaveBeenCalled()
    expect(outdated.items.value).toEqual([])

    // 批量更新主题时同样不改变当前生效主题
    const themeOutcome = await installPreparedOnlineAppearance('tok:theme-b:2', 'theme', {
      preserveCurrentSelection: true,
      allowReplaceId: 'theme-b',
    })
    expect(themeOutcome).toBe('installed')
    expect(setAppearanceMock).not.toHaveBeenCalled()

    // 单独安装桌宠（不传 preserveCurrentSelection）保留原有切换行为
    const singleOutcome = await installPreparedOnlineAppearance('tok:mascot-b:2', 'mascot', {
      allowReplaceId: 'mascot-b',
    })
    expect(singleOutcome).toBe('installed')
    expect(activeMascotId).toBe('mascot-b')
    expect(saveConfigMock).toHaveBeenCalledWith({ desktopMascotId: 'mascot-b' })
  })

  it('新版包 ID 与待升级的本机 ID 不一致时，批量流程拒绝静默覆盖另一份已有本机包', async () => {
    const electronAPI = (
      globalThis as unknown as {
        window: {
          electronAPI: {
            listOnlineAppearances: ReturnType<typeof vi.fn>
            prepareOnlineAppearance: ReturnType<typeof vi.fn>
            installOnlineAppearance: ReturnType<typeof vi.fn>
            discardOnlineAppearance: ReturnType<typeof vi.fn>
          }
        }
      }
    ).window.electronAPI

    electronAPI.listOnlineAppearances.mockImplementation(
      async (_query: unknown, category: AppearanceCategory) => {
        if (category === 'mascot') {
          return {
            success: true,
            items: [],
            pagination: { page: 1, pageSize: 50, total: 0, hasNext: false },
          }
        }
        return {
          success: true,
          items: [
            makeItem({
              fileKey: 'theme-b',
              publishedVersionNo: 2,
              installed: { appearanceId: 'theme-b', versionNo: 1 },
            }),
          ],
          pagination: { page: 1, pageSize: 50, total: 1, hasNext: false },
        }
      }
    )

    // 作者发布 v2 时把包 ID 改成了本机已存在的另一份资源 ID "other-theme"
    electronAPI.prepareOnlineAppearance.mockResolvedValue({
      success: true,
      token: 'tok:theme-b:2',
      appearance: { id: 'other-theme', name: '误改 ID 的新版' },
    })

    const { useAppearanceSettings } = await import('@/views/setting/useAppearanceSettings')
    const { useOutdatedAppearances } = await import('./useOutdatedAppearances')
    const { installPreparedOnlineAppearance } = useAppearanceSettings()
    const outdated = useOutdatedAppearances({
      install: (token, category, opts) => installPreparedOnlineAppearance(token, category, opts),
    })

    await outdated.refresh()
    const summary = await outdated.updateAll()

    // 批量入口跳过安装并丢弃临时包，绝不覆盖另一份本机包 other-theme
    expect(summary).toEqual({ succeeded: 0, failed: 1 })
    expect(installOnlineThemeMock).not.toHaveBeenCalled()
    expect(electronAPI.discardOnlineAppearance).toHaveBeenCalledWith('tok:theme-b:2', 'theme')

    // 下层安装函数兜底校验：即使直接调用且传入 allowReplaceId='theme-b'，冲突对象是 other-theme 时也不允许静默覆盖
    installOnlineThemeMock.mockImplementationOnce(async (_token, replace) => ({
      success: Boolean(replace),
      code: replace ? undefined : 'DUPLICATE_ID',
      existing: { id: 'other-theme', name: '另一份本机主题' },
      appearance: {
        id: 'other-theme',
        name: '另一份本机主题',
        mode: 'light' as const,
        tokens: { colorPrimary: '#1677ff' },
      },
    }))
    const directOutcome = await installPreparedOnlineAppearance('tok:theme-b:2', 'theme', {
      preserveCurrentSelection: true,
      allowReplaceId: 'theme-b',
    })
    expect(directOutcome).toBe('cancelled')
    expect(modalConfirmMock).toHaveBeenCalledTimes(1)
    expect(installOnlineThemeMock).toHaveBeenCalledTimes(1)
    expect(installOnlineThemeMock).toHaveBeenCalledWith('tok:theme-b:2', false)
  })

  it('输入新搜索词的防抖窗口内点加载更多不会吞掉新词首页或把新词第 2 页追加到旧列表', async () => {
    vi.useFakeTimers()
    try {
      const electronAPI = (
        globalThis as unknown as {
          window: {
            electronAPI: {
              listOnlineAppearances: ReturnType<typeof vi.fn>
              getOnlineAppearanceCover?: ReturnType<typeof vi.fn>
            }
          }
        }
      ).window.electronAPI

      electronAPI.getOnlineAppearanceCover = vi.fn(async () => ({ success: false }))
      electronAPI.listOnlineAppearances.mockImplementation(
        async (query: { page?: number; keyword?: string }) => {
          if (query.keyword === 'miku' && query.page === 1) {
            return {
              success: true,
              items: [makeItem({ fileKey: 'miku-1', hasCover: false })],
              pagination: { page: 1, pageSize: 48, total: 60, hasNext: true },
            }
          }
          if (query.keyword === 'miku' && query.page === 2) {
            return {
              success: true,
              items: [makeItem({ fileKey: 'miku-2', hasCover: false })],
              pagination: { page: 2, pageSize: 48, total: 60, hasNext: false },
            }
          }
          return {
            success: true,
            items: [makeItem({ fileKey: 'old-1', hasCover: false })],
            pagination: { page: 1, pageSize: 48, total: 60, hasNext: true },
          }
        }
      )

      const { useOnlineAppearance, ONLINE_APPEARANCE_SEARCH_DEBOUNCE } =
        await import('./useOnlineAppearance')
      const store = useOnlineAppearance({
        categoryKey: 'theme',
        install: async () => 'installed',
      })

      await store.loadList(1)
      expect(store.items.value.map(item => item.fileKey)).toEqual(['old-1'])
      expect(store.hasMore.value).toBe(true)

      // 用户输入新关键词，在 400ms 防抖期内尝试点加载更多
      store.keyword.value = 'miku'
      store.scheduleSearch()
      expect(store.hasMore.value).toBe(false)

      await store.loadMore()
      // 不能取消待执行的新词第 1 页搜索，也不能用旧页码去拉新词第 2 页
      expect(electronAPI.listOnlineAppearances).toHaveBeenCalledTimes(1)

      // 防抖到期后正确从第 1 页拉取新词结果并替换旧列表
      await vi.advanceTimersByTimeAsync(ONLINE_APPEARANCE_SEARCH_DEBOUNCE)
      expect(electronAPI.listOnlineAppearances).toHaveBeenLastCalledWith(
        { page: 1, pageSize: 48, keyword: 'miku' },
        'theme'
      )
      expect(store.items.value.map(item => item.fileKey)).toEqual(['miku-1'])
      expect(store.hasMore.value).toBe(true)

      // 新词第 1 页就绪后，再点加载更多才追加新词第 2 页
      await store.loadMore()
      expect(electronAPI.listOnlineAppearances).toHaveBeenLastCalledWith(
        { page: 2, pageSize: 48, keyword: 'miku' },
        'theme'
      )
      expect(store.items.value.map(item => item.fileKey)).toEqual(['miku-1', 'miku-2'])
    } finally {
      vi.useRealTimers()
    }
  })
})
