import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { defineComponent, h, nextTick } from 'vue'
import {
  GetService,
  Service,
  type HistoryBucket,
  type HistorySearchOut,
  type SettingGetOut,
} from '@/api'
import { deferred, testView } from '../../../tests/vueRenderer'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('ant-design-vue', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/utils/featureAnalytics', () => ({
  apiOutcome: () => 'success',
  observeFeature: (_name: string, _props: unknown, run: () => Promise<unknown>) => run(),
}))
vi.mock('@/utils/analytics', () => ({ analyticsCountBucket: () => '0' }))
vi.mock('@/composables/useAudioPlayer', () => ({
  useAudioPlayer: () => ({ playSound: vi.fn() }),
}))
vi.mock('@/composables/useLogHighlight', async () => {
  const { ref } = await import('vue')
  return {
    useLogHighlight: () => ({
      registerLogLanguage: vi.fn(),
      editorTheme: ref('vs-dark'),
      editorConfig: ref({ fontSize: 13, lineHeight: 1.5 }),
      setEditorConfig: vi.fn(),
    }),
  }
})

type Logic = ReturnType<(typeof import('./useHistoryLogic'))['useHistoryLogic']>
type Presets = (typeof import('./useHistoryLogic'))['timePresets']

// 后端按时间正序返回同一天、同一用户的记录条目
function bucket(date: string, times: string[]): HistoryBucket {
  return {
    index: times.map((time, order) => ({
      id: `${date}-${order}`,
      time: `${date}T${time}:00+08:00`,
      username: 'user',
      script_name: 'script',
      status: 'success',
      message: '',
    })),
    data: {},
    aggregate_errors: [],
  } as unknown as HistoryBucket
}

const searchReply = (date: string, times: string[]): HistorySearchOut =>
  ({
    code: 200,
    status: 'success',
    message: '',
    data: { [date]: { user: bucket(date, times) } },
  }) as unknown as HistorySearchOut

const settingsReply = (order: 'asc' | 'desc'): SettingGetOut =>
  ({
    code: 200,
    status: 'success',
    message: '',
    data: { Function: { HistoryOrder: order } },
  }) as unknown as SettingGetOut

async function mountLogic() {
  const { useHistoryLogic, timePresets } = await import('./useHistoryLogic')
  let logic!: Logic
  const view = testView(
    defineComponent(() => {
      logic = useHistoryLogic()
      return () => h('div')
    })
  )
  view.mount()
  return { logic, presets: timePresets as Presets, unmount: () => view.app.unmount() }
}

// 搜索成功后还会动态加载提示音模块，等几个宏任务让它走完
const flush = async () => {
  for (let i = 0; i < 5; i++) await new Promise(resolve => setTimeout(resolve, 0))
  await nextTick()
}

const shownTimes = (logic: Logic) =>
  logic.selectedRecords.value.map(record => record.time.slice(11, 16))

function selectOnlyUser(logic: Logic) {
  const group = logic.historyData.value[0]
  void logic.handleSelectUser(`${group.date}user`, group.users.user)
}

beforeEach(() => {
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => ({ info: vi.fn(), error: vi.fn() }) },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('history record order', () => {
  it('shows search results without waiting for a slow settings reply, then reorders in place', async () => {
    const settings = deferred<SettingGetOut>()
    vi.spyOn(GetService, 'getScriptsApiSettingGetPost').mockReturnValue(settings.promise)
    const week = deferred<HistorySearchOut>()
    const today = deferred<HistorySearchOut>()
    const search = vi
      .spyOn(Service, 'searchHistoryApiHistorySearchPost')
      .mockReturnValueOnce(week.promise)
      .mockReturnValueOnce(today.promise)

    const { logic, presets, unmount } = await mountLogic()

    // 默认的「最近一周」先回来：设置还没到，按默认的最新在前直接显示
    week.resolve(searchReply('2026-11-26', ['05:19', '05:21']))
    await flush()
    expect(logic.searchLoading.value).toBe(false)
    expect(logic.historyData.value.map(group => group.date)).toEqual(['2026-11-26'])
    selectOnlyUser(logic)
    expect(shownTimes(logic)).toEqual(['05:21', '05:19'])

    // 切到「今天」，今天的结果先回来
    logic.handleQuickTimeSelect(presets.find(preset => preset.key === 'today')!)
    today.resolve(searchReply('2026-11-27', ['17:18', '17:20']))
    await flush()
    expect(search).toHaveBeenCalledTimes(2)
    expect(logic.currentPreset.value).toBe('today')

    // 第一轮的设置这时才回来：只重排当前列表，不能把一周的结果写回
    selectOnlyUser(logic)
    await logic.handleSelectRecord(0, logic.selectedRecords.value[0])
    settings.resolve(settingsReply('asc'))
    await flush()
    expect(logic.historyData.value.map(group => group.date)).toEqual(['2026-11-27'])
    expect(shownTimes(logic)).toEqual(['17:18', '17:20'])
    // 选中的仍是同一条（17:20），只是位置跟着顺序变了
    expect(logic.selectedRecordIndex.value).toBe(1)

    unmount()
  })

  it('lets only the latest search update the list and finish loading', async () => {
    vi.spyOn(GetService, 'getScriptsApiSettingGetPost').mockResolvedValue(settingsReply('desc'))
    const week = deferred<HistorySearchOut>()
    const today = deferred<HistorySearchOut>()
    vi.spyOn(Service, 'searchHistoryApiHistorySearchPost')
      .mockReturnValueOnce(week.promise)
      .mockReturnValueOnce(today.promise)

    const { logic, presets, unmount } = await mountLogic()

    logic.handleQuickTimeSelect(presets.find(preset => preset.key === 'today')!)
    today.resolve(searchReply('2026-11-27', ['17:18', '17:20']))
    await flush()
    expect(logic.historyData.value.map(group => group.date)).toEqual(['2026-11-27'])
    expect(logic.searchLoading.value).toBe(false)

    // 先发的一周查询后回来，不能覆盖已经显示的今天
    week.resolve(searchReply('2026-11-26', ['05:19', '05:21']))
    await flush()
    expect(logic.historyData.value.map(group => group.date)).toEqual(['2026-11-27'])
    expect(logic.currentPreset.value).toBe('today')

    unmount()
  })

  it('falls back to newest first when settings cannot be read', async () => {
    vi.spyOn(GetService, 'getScriptsApiSettingGetPost').mockRejectedValue(new Error('offline'))
    vi.spyOn(Service, 'searchHistoryApiHistorySearchPost').mockResolvedValue(
      searchReply('2026-11-27', ['17:18', '17:20'])
    )

    const { logic, unmount } = await mountLogic()
    await flush()
    selectOnlyUser(logic)
    expect(shownTimes(logic)).toEqual(['17:20', '17:18'])

    unmount()
  })
})
