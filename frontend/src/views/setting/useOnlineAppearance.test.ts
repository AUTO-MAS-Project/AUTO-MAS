import { beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  OnlineAppearanceDetailResult,
  OnlineAppearanceItem,
  OnlineAppearanceListResult,
  OnlineAppearancePrepareResult,
} from '@/types/appearance'

const listOnlineAppearances = vi.fn<(query?: unknown) => Promise<OnlineAppearanceListResult>>()
const getOnlineAppearance = vi.fn<(fileKey: string) => Promise<OnlineAppearanceDetailResult>>()
const prepareOnlineAppearance =
  vi.fn<(fileKey: string, versionNo: number) => Promise<OnlineAppearancePrepareResult>>()
const discardOnlineAppearance = vi.fn(async (_token: string) => ({ success: true }))

vi.stubGlobal('window', {
  electronAPI: {
    getLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
    listOnlineAppearances,
    getOnlineAppearance,
    prepareOnlineAppearance,
    discardOnlineAppearance,
  },
})

const { translate } = await import('@/i18n')
const {
  describeOnlineAppearanceError,
  formatAppearanceFileSize,
  getOnlineAppearanceStatus,
  pickDefaultVersion,
  useOnlineAppearance,
} = await import('./useOnlineAppearance')

const item = (overrides: Partial<OnlineAppearanceItem> = {}): OnlineAppearanceItem => ({
  fileKey: 'sakura',
  displayName: '樱花',
  description: '粉色主题',
  ownerUsername: 'alice',
  publishedVersionNo: 2,
  publishedAt: '2026-10-06T10:00:00Z',
  updatedAt: '2026-10-06T10:00:00Z',
  installed: null,
  ...overrides,
})

const versions = [
  { versionNo: 2, fileSize: 2048, sha256: 'b'.repeat(64), changeNote: '', createdAt: '' },
  { versionNo: 1, fileSize: 1024, sha256: 'a'.repeat(64), changeNote: '', createdAt: '' },
]

const preparedFor = (versionNo: number): OnlineAppearancePrepareResult => ({
  success: true,
  token: `token-v${versionNo}`,
  fileKey: 'sakura',
  versionNo,
  appearance: {
    id: 'sakura',
    name: `樱花 v${versionNo}`,
    mode: 'light',
    tokens: { colorPrimary: '#eb2f96' },
  },
  existing: null,
})

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

beforeEach(() => {
  listOnlineAppearances.mockReset()
  getOnlineAppearance.mockReset()
  prepareOnlineAppearance.mockReset()
  discardOnlineAppearance.mockClear()
  listOnlineAppearances.mockResolvedValue({
    success: true,
    items: [item()],
    pagination: { page: 1, pageSize: 12, total: 1, hasNext: false },
  })
  getOnlineAppearance.mockResolvedValue({ success: true, item: item(), versions })
  prepareOnlineAppearance.mockImplementation(async (_key, versionNo) => preparedFor(versionNo))
})

describe('online appearance helpers', () => {
  it('maps transport codes to local copy but keeps package validation reasons', () => {
    expect(describeOnlineAppearanceError({ code: 'CHECKSUM_MISMATCH' }, 'x')).toBe(
      translate('setting.onlineAppearance.error.checksum')
    )
    expect(describeOnlineAppearanceError({ code: 'TOO_LARGE', error: 'raw' }, 'x')).toBe(
      translate('setting.onlineAppearance.error.tooLarge')
    )
    expect(
      describeOnlineAppearanceError({ code: 'INVALID_PACKAGE', error: '缺少 theme.json' }, 'x')
    ).toBe('缺少 theme.json')
    expect(describeOnlineAppearanceError(undefined, 'setting.onlineAppearance.installFailed')).toBe(
      translate('setting.onlineAppearance.installFailed')
    )
  })

  it('distinguishes not installed, installed and older installed versions', () => {
    expect(getOnlineAppearanceStatus(item())).toBe('none')
    expect(
      getOnlineAppearanceStatus(item({ installed: { appearanceId: 's', versionNo: 2 } }))
    ).toBe('installed')
    expect(
      getOnlineAppearanceStatus(item({ installed: { appearanceId: 's', versionNo: 1 } }))
    ).toBe('outdated')
  })

  it('defaults to the published version and falls back to the newest one', () => {
    expect(pickDefaultVersion(versions, 1)).toBe(1)
    expect(pickDefaultVersion(versions, 9)).toBe(2)
    expect(pickDefaultVersion([], 1)).toBeNull()
  })

  it('formats package sizes', () => {
    expect(formatAppearanceFileSize(512)).toBe('512 B')
    expect(formatAppearanceFileSize(1536)).toBe('1.5 KB')
    expect(formatAppearanceFileSize(16 * 1024 * 1024)).toBe('16.0 MB')
  })
})

describe('useOnlineAppearance', () => {
  it('loads the list and reports failures instead of showing an empty list', async () => {
    const store = useOnlineAppearance({ install: vi.fn() })
    store.open()
    await flush()
    expect(store.items.value).toHaveLength(1)
    expect(store.listError.value).toBeNull()

    listOnlineAppearances.mockResolvedValueOnce({ success: false, code: 'NETWORK', error: 'x' })
    await store.loadList(1)
    expect(store.items.value).toEqual([])
    expect(store.listError.value).toBe(translate('setting.onlineAppearance.error.network'))
  })

  it('previews the published version and pins later downloads to the chosen version', async () => {
    const install = vi.fn(async () => 'installed' as const)
    const store = useOnlineAppearance({ install })
    await store.openDetail(item())

    expect(prepareOnlineAppearance).toHaveBeenLastCalledWith('sakura', 2)
    expect(store.prepared.value?.appearance.name).toBe('樱花 v2')

    store.selectVersion(1)
    await flush()
    expect(discardOnlineAppearance).toHaveBeenCalledWith('token-v2')
    expect(prepareOnlineAppearance).toHaveBeenLastCalledWith('sakura', 1)
    expect(store.prepared.value?.versionNo).toBe(1)

    await expect(store.install()).resolves.toBe('installed')
    expect(install).toHaveBeenCalledWith('token-v1')
    expect(prepareOnlineAppearance).toHaveBeenCalledTimes(2)
  })

  it('keeps the verified download when the user declines to replace the same ID', async () => {
    const store = useOnlineAppearance({ install: vi.fn(async () => 'cancelled' as const) })
    await store.openDetail(item())
    await store.install()
    expect(store.prepared.value?.token).toBe('token-v2')
    expect(discardOnlineAppearance).not.toHaveBeenCalled()
  })

  it('drops a failed install so the next attempt downloads again', async () => {
    const store = useOnlineAppearance({ install: vi.fn(async () => 'failed' as const) })
    await store.openDetail(item())
    await store.install()
    expect(store.prepared.value).toBeNull()
    expect(discardOnlineAppearance).toHaveBeenCalledWith('token-v2')
  })

  it('discards a preview that finishes after the user switched versions', async () => {
    let releaseFirst: (value: OnlineAppearancePrepareResult) => void = () => undefined
    prepareOnlineAppearance.mockImplementationOnce(
      () => new Promise(resolve => (releaseFirst = resolve))
    )
    const store = useOnlineAppearance({ install: vi.fn() })
    const opening = store.openDetail(item())
    await flush()
    store.selectVersion(1)
    await flush()
    releaseFirst(preparedFor(2))
    await opening
    expect(store.prepared.value?.versionNo).toBe(1)
    expect(discardOnlineAppearance).toHaveBeenCalledWith('token-v2')
  })

  it('shows download failures and does not install without a verified package', async () => {
    prepareOnlineAppearance.mockResolvedValueOnce({ success: false, code: 'CHECKSUM_MISMATCH' })
    const install = vi.fn()
    const store = useOnlineAppearance({ install })
    await store.openDetail(item())
    expect(store.prepareError.value).toBe(translate('setting.onlineAppearance.error.checksum'))

    prepareOnlineAppearance.mockResolvedValueOnce({ success: false, code: 'TOO_LARGE' })
    await expect(store.install()).resolves.toBe('failed')
    expect(install).not.toHaveBeenCalled()
  })

  it('returning to the list releases the pending download', async () => {
    const store = useOnlineAppearance({ install: vi.fn() })
    await store.openDetail(item())
    store.backToList()
    expect(store.view.value).toBe('list')
    expect(store.prepared.value).toBeNull()
    expect(discardOnlineAppearance).toHaveBeenCalledWith('token-v2')
  })
})
