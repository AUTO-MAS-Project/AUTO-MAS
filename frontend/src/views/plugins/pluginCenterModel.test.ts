import { describe, expect, it } from 'vite-plus/test'
import type { PluginCatalogGetOut, PluginRegistryGetOut } from '@/api'
import { SCRIPT_PLUGIN_BINDINGS } from '@/plugins/scriptAdapters'
import {
  PLUGIN_ICON_TONES,
  actionVisible,
  detailFieldKeys,
  groupInstalled,
  joinSegments,
  lifecycleDecision,
  marketAction,
  marketColumnCount,
  matchesInstalledFilter,
  matchesMarketFilter,
  matchesSearch,
  pluginSettingsGroups,
  pluginStatus,
  pluginUsage,
  toggleState,
  toInstalledViews,
  toMarketViews,
  updatableEntries,
  updateActionLabel,
  usageSegments,
  usageSourceState,
  usesInlineToggle,
  type PluginModelContext,
  type PluginUsageSource,
} from './pluginCenterModel'

const MAA = {
  pluginId: 'maa_adapter',
  scriptType: 'MAA',
  logo: 'maa.png',
  planConfigType: 'MaaPlanConfig',
}
const context = (texts: Record<string, string> = {}): PluginModelContext => ({
  bindings: [MAA],
  appIcon: 'app.ico',
  texts: {
    text: (id, field) => texts[`${id}.${field}`],
    tags: () => undefined,
  },
})
const registry = (records: Record<string, object>): PluginRegistryGetOut => ({
  order: Object.keys(records).map(uid => ({ uid, type: 'PluginRecord' })),
  data: Object.fromEntries(
    Object.entries(records).map(([uid, value]) => [uid, { uid, ui: {}, ...value }])
  ),
})
const catalog = (records: Record<string, object>): PluginCatalogGetOut => ({
  order: Object.keys(records).map(uid => ({ uid, type: 'PluginMeta' })),
  data: Object.fromEntries(
    Object.entries(records).map(([uid, info]) => [uid, { uid, ui: {}, info }])
  ),
})
const installedOne = (info: object, extra: object = {}, ctx = context()) =>
  toInstalledViews(registry({ r1: { info, ...extra } }), [], ctx)[0]

describe('插件中心缺声明回落', () => {
  it('目录和注册表回读不同步时，不把旧说明挂到新版本或本地源码', () => {
    const info = {
      plugin_name: 'demo',
      package_name: 'auto-mas-demo',
      version: '2.0',
      installed_version: '1.0',
      changelog: [{ version: '1.0', body: 'old' }],
      changelog_versions: { installed: '1.0', target: '2.0', updates: [] },
    }
    const market = toMarketViews(catalog({ m1: info }), null, context())
    const notes = (version: string, source: string) =>
      toInstalledViews(
        registry({ r1: { info: { ...info, version, source } } }),
        market,
        context()
      )[0].releaseNotes
    expect(notes('1.0', 'installed')).toEqual(info.changelog)
    expect(notes('2.0', 'installed')).toEqual([])
    expect(notes('1.0', 'local')).toEqual([])
  })

  it('名称依次取插件词条、注册表显示名、插件标识、条目 uid', () => {
    const ctx = context({ 'demo.display_name': '词条名' })
    expect(installedOne({ plugin_name: 'demo', display_name: '注册名' }, {}, ctx).name).toBe(
      '词条名'
    )
    expect(installedOne({ plugin_name: 'demo', display_name: '注册名' }).name).toBe('注册名')
    expect(installedOne({ plugin_name: 'demo', display_name: '  ' }).name).toBe('demo')
    expect(installedOne({}).name).toBe('r1')
  })

  it('装着的版本没声明显示名时，取市场目录里同一插件的名称', () => {
    const market = toMarketViews(
      catalog({ m1: { plugin_name: 'demo', display_name: '目录名' }, m2: { plugin_name: 'bare' } }),
      null,
      context()
    )
    const name = (info: object) =>
      toInstalledViews(registry({ r1: { info } }), market, context())[0].name
    // 后端在没声明时拿插件标识当显示名，这种不算声明。
    expect(name({ plugin_name: 'demo', display_name: 'demo' })).toBe('目录名')
    expect(name({ plugin_name: 'demo' })).toBe('目录名')
    expect(name({ plugin_name: 'demo', display_name: '注册名' })).toBe('注册名')
    // 目录条目自己也没有名称时仍回落到插件标识。
    expect(name({ plugin_name: 'bare' })).toBe('bare')
  })

  it('图标依次取专项 logo、核心应用图标、首字母色块、通用图标', () => {
    expect(installedOne({ plugin_name: 'maa_adapter', is_core: true }).icon).toEqual({
      kind: 'image',
      src: 'maa.png',
    })
    expect(installedOne({ plugin_name: 'auto_mas_core', is_core: true }).icon).toEqual({
      kind: 'image',
      src: 'app.ico',
    })
    expect(installedOne({ plugin_name: 'x', display_name: 'fast download' }).icon).toMatchObject({
      kind: 'initial',
      text: 'F',
    })
    expect(installedOne({ plugin_name: 'x', display_name: '下载加速' }).icon).toMatchObject({
      text: '下',
    })
    expect(installedOne({ plugin_name: 'my_adapter' }).icon).toMatchObject({ text: 'M' })
    expect(installedOne({}).icon.kind).toBe('generic')
  })

  it('色块颜色按插件标识稳定映射到固定色组', () => {
    const tones = ['A', 'B'].map(name => {
      const icon = installedOne({ plugin_name: 'fast_download', display_name: name }).icon
      return icon.kind === 'initial' ? icon.tone : null
    })
    expect(tones[0]).not.toBeNull()
    expect(tones[1]).toBe(tones[0])
    expect(PLUGIN_ICON_TONES).toContain(tones[0])
  })

  it('缺哪项不显示哪项：没有占位、副标题不出现多余分隔符、非 http 链接当作没有', () => {
    const bare = installedOne({ plugin_name: 'bare', source: 'installed' })
    expect(bare.description).toBeNull()
    expect(bare.author).toBeNull()
    expect(bare.version).toBeNull()
    expect(bare.tags).toEqual([])
    expect(bare.links).toEqual([])
    expect(detailFieldKeys(bare)).toEqual(['publisher', 'source'])
    expect(joinSegments([null, '作者', '', undefined, '  ', '标签'])).toBe('作者 · 标签')
    expect(joinSegments([null, ''])).toBe('')
    const links = installedOne({
      docs_url: 'javascript:alert(1)',
      homepage: 'https://example.org/home',
      repository: 'not a url',
    }).links
    expect(links).toEqual([{ kind: 'homepage', href: 'https://example.org/home' }])
  })

  it('市场条目缺内容时给空值，由卡片保留高度', () => {
    const [entry] = toMarketViews(catalog({ m1: {} }), null, context())
    expect(entry).toMatchObject({ name: 'm1', description: null, tags: [], version: null })
  })

  it('类别判不出来归扩展；来源为空不判官方也不显示来源', () => {
    const view = installedOne({ plugin_name: 'x', package_name: 'auto-mas-maa-adapter' })
    expect(view.category).toBe('extension')
    expect(view.official).toBe(false)
    expect(view.publisher).toBeNull()
    expect(detailFieldKeys(view)).not.toContain('source')
    // 来源为空时包名单列，不随来源一起消失。
    expect(detailFieldKeys(view)).toContain('packageName')
    expect(
      installedOne({ plugin_name: 'x', package_name: 'auto-mas-maa-adapter', source: 'installed' })
        .official
    ).toBe(false)
    expect(
      installedOne({ plugin_name: 'x', is_local: true, package_name: 'auto-mas-maa-adapter' })
    ).toMatchObject({ official: false, local: true, category: 'local' })
  })

  it('市场头像和官方身份来自目录，本机图标来自注册表', () => {
    const [entry] = toMarketViews(
      catalog({
        m1: {
          plugin_name: 'maa_adapter',
          icon_png: 'marketPNG',
          publisher_organization: 'auto-mas',
        },
      }),
      null,
      context()
    )
    expect(entry).toMatchObject({
      official: true,
      icon: { kind: 'image', src: 'data:image/png;base64,marketPNG' },
    })
    expect(
      installedOne({ plugin_name: 'maa_adapter', source: 'installed' }, { iconPng: 'installedPNG' })
    ).toMatchObject({
      official: false,
      icon: { kind: 'image', src: 'data:image/png;base64,installedPNG' },
    })
  })

  it('不认识的状态显示原值、用中性颜色', () => {
    expect(pluginStatus('hibernating')).toEqual({
      labelKey: null,
      raw: 'hibernating',
      tone: 'default',
    })
    expect(pluginStatus('enabled').tone).toBe('success')
    expect(pluginStatus(undefined).raw).toBe('unloaded')
  })
})

describe('插件中心用量与操作确认', () => {
  const source = (state: PluginUsageSource['state']): PluginUsageSource => ({
    state,
    scripts: [
      { uid: 's1', name: '官服', scriptType: 'MAA', accounts: 3 },
      { uid: 's2', name: '其他', scriptType: 'General', accounts: 1 },
    ],
    planCounts: { MaaPlanConfig: 1 },
  })
  const maa = installedOne({ plugin_name: 'maa_adapter' }, { disableImpact: ['scripts'] })

  it('有托管、账号和计划表时仍可确认停用或卸载', () => {
    const usage = pluginUsage(maa, source('ready'))
    expect(usage).toMatchObject({ kind: 'counted', scriptCount: 1, accountCount: 3, planCount: 1 })
    for (const action of ['disable', 'uninstall'] as const)
      expect(lifecycleDecision(action, maa)).toMatchObject({ kind: 'confirm', scopes: ['scripts'] })
  })

  it('用量未知时隐藏数量，操作仍按后端给的影响范围确认', () => {
    expect(usageSourceState({ failed: false, current: false })).toBe('loading')
    expect(usageSourceState({ failed: false, current: true })).toBe('ready')
    expect(usageSourceState({ failed: true, current: true })).toBe('error')
    const thirdParty = installedOne({ plugin_name: 'ld_adapter' }, { disableImpact: ['games'] })
    const usage = pluginUsage(thirdParty, source('error'))
    expect(usage).toEqual({ kind: 'impactOnly', scopes: ['games'] })
    expect(usageSegments(usage)).toEqual([])
    expect(lifecycleDecision('disable', thirdParty)).toMatchObject({
      kind: 'confirm',
      scopes: ['games'],
    })
    const plain = installedOne({ plugin_name: 'fast_download' })
    expect(lifecycleDecision('disable', plain)).toEqual({ kind: 'direct' })
    expect(lifecycleDecision('uninstall', plain)).toMatchObject({ kind: 'confirm' })
  })

  it('没有托管影响时也确认连带停用，只列出对应操作的下游插件', () => {
    const runner = installedOne(
      { plugin_name: 'maafw_runner' },
      {
        disableCascade: ['mss_adapter'],
        uninstallCascade: ['mss_adapter', 'm9a_adapter'],
      }
    )
    expect(lifecycleDecision('disable', runner)).toEqual({
      kind: 'confirm',
      scopes: [],
      cascade: ['mss_adapter'],
    })
    expect(lifecycleDecision('uninstall', runner)).toEqual({
      kind: 'confirm',
      scopes: [],
      cascade: ['mss_adapter', 'm9a_adapter'],
    })
  })

  it('按适配条目统计 MaaFW 家族的托管与 MSS 计划表', () => {
    for (const type of ['MaaFW', 'M9A', 'MSS']) {
      const view = installedOne(
        { plugin_name: `${type.toLowerCase()}_adapter` },
        {},
        { ...context(), bindings: SCRIPT_PLUGIN_BINDINGS }
      )
      expect(
        pluginUsage(view, {
          state: 'ready',
          scripts: [{ uid: type, name: type, scriptType: type, accounts: 1 }],
          planCounts: { MSSPlanConfig: 2 },
        })
      ).toMatchObject({ kind: 'counted', scriptCount: 1, planCount: type === 'MSS' ? 2 : null })
    }
  })

  it('数量拿不到或为 0 的段不显示', () => {
    const partial = { ...source('ready'), planCounts: null }
    partial.scripts = [{ uid: 's1', name: '官服', scriptType: 'MAA', accounts: null }]
    expect(usageSegments(pluginUsage(maa, partial))).toEqual([
      { key: 'core.plugins.usage.scripts', count: 1 },
    ])
  })
})

describe('插件中心版本与更新', () => {
  it('已安装版本缺失按未安装，是否可更新只看 update_available', () => {
    const market = toMarketViews(
      catalog({
        a: { plugin_name: 'a', version: '2.0' },
        b: { plugin_name: 'b', version: '2.0', installed_version: '1.0' },
        c: { plugin_name: 'c', version: '2.0', installed_version: '1.0', update_available: true },
      }),
      null,
      context()
    )
    expect(market.map(entry => [entry.installed, entry.updateAvailable])).toEqual([
      [false, false],
      [true, false],
      [true, true],
    ])
    expect(updatableEntries(market, []).map(item => [item.entry.uid, item.fromVersion])).toEqual([
      ['c', '1.0'],
    ])
  })
})

describe('插件中心布局与设置入口', () => {
  it('市场列数取能放下的最大列数，末行只剩一张时减一列', () => {
    expect(marketColumnCount(1022, 6)).toBe(3)
    expect(marketColumnCount(1022, 4)).toBe(2)
    expect(marketColumnCount(1022, 1)).toBe(3)
    expect(marketColumnCount(200, 5)).toBe(1)
    expect(marketColumnCount(1338, 6)).toBe(4)
    expect(marketColumnCount(1338, 9)).toBe(3)
    expect(marketColumnCount(1338, 5)).toBe(3)
    // 减列只减到不少于 2 列；减不掉单张就保持最大列数，不退成单列。
    expect(marketColumnCount(1022, 7)).toBe(3)
    expect(marketColumnCount(1338, 13)).toBe(4)
    for (const count of [3, 5, 7]) expect(marketColumnCount(616, count)).toBe(2)
    expect(marketColumnCount(616, 4)).toBe(2)
    expect(marketColumnCount(Number.NaN, 3)).toBe(1)
  })

  it('设置入口只认有提示项的分组', () => {
    expect(pluginSettingsGroups({ ui: { hints: { a: [], b: [{ field: 'x' }] } } })).toEqual([
      { name: 'b', hints: [{ field: 'x' }] },
    ])
    expect(pluginSettingsGroups(null)).toEqual([])
    expect(pluginSettingsGroups({ ui: {} })).toEqual([])
  })
})

describe('插件中心分组、搜索与筛选', () => {
  const views = toInstalledViews(
    registry({
      ext: {
        info: { plugin_name: 'fast_download', display_name: 'Fast Download', source: 'installed' },
      },
      loc: { info: { plugin_name: 'dev_tool', is_local: true } },
      maa: {
        info: {
          plugin_name: 'maa_adapter',
          author: 'AUTO-MAS',
          package_name: 'auto-mas-maa-adapter',
          source: 'installed',
          state: 'fault_load',
        },
      },
      core: { info: { plugin_name: 'auto_mas_core', is_core: true, tags: ['系统'] } },
      ext2: { info: { plugin_name: 'theme_pack' } },
    }),
    toMarketViews(
      catalog({
        m1: { plugin_name: 'theme_pack', version: '2.0', update_available: true },
        m2: {
          plugin_name: 'maa_adapter',
          package_name: 'auto-mas-maa-adapter',
          publisher_organization: 'auto-mas',
        },
      }),
      null,
      context()
    ),
    context()
  )

  it('按核心、专项、扩展、本地分组，组内保持注册表顺序，空组不出现', () => {
    expect(
      groupInstalled(views).map(group => [group.category, group.views.map(v => v.uid)])
    ).toEqual([
      ['core', ['core']],
      ['specialized', ['maa']],
      ['extension', ['ext', 'ext2']],
      ['local', ['loc']],
    ])
    expect(groupInstalled(views.filter(view => view.uid === 'ext')).map(g => g.category)).toEqual([
      'extension',
    ])
  })

  it('搜索不区分大小写，覆盖名称、标识、包名、作者与标签；空查询全部通过', () => {
    const hits = (query: string) => views.filter(view => matchesSearch(view, query)).map(v => v.uid)
    expect(hits('  ')).toHaveLength(views.length)
    expect(hits('FAST')).toEqual(['ext'])
    expect(hits('auto-mas-maa')).toEqual(['maa'])
    expect(hits('auto-mas')).toEqual(['maa'])
    expect(hits('系统')).toEqual(['core'])
    expect(hits('不存在')).toEqual([])
  })

  it('筛选官方、有更新、异常，各自只看对应判据', () => {
    const pick = (filter: 'all' | 'official' | 'update' | 'fault') =>
      views.filter(view => matchesInstalledFilter(view, filter)).map(view => view.uid)
    expect(pick('all')).toHaveLength(views.length)
    expect(pick('official')).toEqual(['maa', 'core'])
    expect(pick('update')).toEqual(['ext2'])
    expect(pick('fault')).toEqual(['maa'])
  })

  it('市场筛选专项与扩展互补', () => {
    const market = toMarketViews(
      catalog({ a: { plugin_name: 'maa_adapter' }, b: { plugin_name: 'theme_pack' } }),
      registry({ r: { info: { plugin_name: 'ld_adapter' }, disableImpact: ['games'] } }),
      context()
    )
    expect(
      market.filter(entry => matchesMarketFilter(entry, 'specialized')).map(e => e.uid)
    ).toEqual(['a'])
    expect(market.filter(entry => matchesMarketFilter(entry, 'extension')).map(e => e.uid)).toEqual(
      ['b']
    )
    expect(market.filter(entry => matchesMarketFilter(entry, 'all'))).toHaveLength(2)
  })
})

describe('插件中心按钮只读界面提示', () => {
  const hints = (...items: Array<[string, boolean]>) => ({
    ui: { hints: { info: items.map(([field, editable]) => ({ field, editable })) } },
  })

  it('启停开关的显隐、勾选与可点只看界面提示，不按运行状态推断', () => {
    const running = installedOne({ plugin_name: 'x', enabled: true, state: 'enabled' })
    expect(toggleState(running).visible).toBe(false)
    const disableable = installedOne({ plugin_name: 'x', enabled: false }, hints(['disable', true]))
    expect(toggleState(disableable)).toEqual({
      visible: true,
      checked: true,
      action: 'disable',
      editable: true,
    })
    const busy = installedOne({ plugin_name: 'x', enabled: true }, hints(['disable', false]))
    expect(toggleState(busy)).toMatchObject({ visible: true, checked: true, editable: false })
    expect(actionVisible(busy, 'uninstall')).toBe(false)
  })

  it('带数据的专项不用行内开关，普通插件用', () => {
    expect(usesInlineToggle(installedOne({ plugin_name: 'theme_pack' }))).toBe(true)
    expect(usesInlineToggle(installedOne({ plugin_name: 'maa_adapter' }))).toBe(false)
    expect(usesInlineToggle(installedOne({ plugin_name: 'y' }, { disableImpact: ['games'] }))).toBe(
      false
    )
  })

  it('市场按钮与「更新至」文案：可更新优先，版本缺失回落为升级', () => {
    expect(marketAction({ installed: true, updateAvailable: true })).toBe('update')
    expect(marketAction({ installed: true, updateAvailable: false })).toBe('installed')
    expect(marketAction({ installed: false, updateAvailable: false })).toBe('install')
    expect(updateActionLabel('2.0')).toEqual({
      key: 'core.plugins.updateTo',
      params: { version: '2.0' },
    })
    expect(updateActionLabel(null)).toEqual({ key: 'core.plugins.upgrade', params: {} })
  })
})
