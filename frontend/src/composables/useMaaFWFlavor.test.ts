import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import {
  MAAFW_FLAVORS,
  MAAFW_SPECIAL_FLAVORS,
  isMaaFWFamily,
  maafwDefaultScriptNames,
  maafwRouteSuffix,
  maafwScriptTypeByConfigType,
  maafwUserConfigTypes,
  prepareMaaFWFlavorPage,
  resolveMaaFWFlavor,
  resolveMaaFWFlavorSlot,
  useMaaFWFlavor,
} from './useMaaFWFlavor'
import type { MaaFWFlavor } from './maafwFlavorTypes'
import zhCN from '@/i18n/locales/zh-CN'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

const lookup = (key: string): unknown =>
  key.split('.').reduce<unknown>((node, part) => {
    return node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined
  }, zhCN)

// 描述对象里这些键的值是各特调自己的表（整页、分节、插入点、受管切号任务），键集本来就因特调而异，当叶子看
const LEAF_FIELDS = new Set(['page', 'sections', 'slots', 'accountTask'])

/** 描述对象展开成「点分路径 → 叶子值」：分组对象往下走，数组、null、函数与上面几项是叶子 */
const fieldEntries = (node: object, prefix = ''): Array<[string, unknown]> =>
  Object.entries(node).flatMap(([key, value]): Array<[string, unknown]> => {
    const path = prefix ? `${prefix}.${key}` : key
    const isGroup =
      value !== null && typeof value === 'object' && !Array.isArray(value) && !LEAF_FIELDS.has(key)
    return isGroup ? fieldEntries(value as object, path) : [[path, value]]
  })

const fieldPaths = (flavor: MaaFWFlavor) =>
  fieldEntries(flavor)
    .map(([path]) => path)
    .sort()

describe('MaaFW flavor 文案表', () => {
  it('M9A 取特调表，其余类型都落到通用 MaaFW', () => {
    expect(resolveMaaFWFlavor('M9A').type).toBe('M9A')
    for (const type of ['MaaFW', 'MAA', 'General', '', null, undefined]) {
      expect(resolveMaaFWFlavor(type).type).toBe('MaaFW')
    }
  })

  it('M9A 的每一处差异都落在文案与身份上，没有行为开关', () => {
    const m9a = resolveMaaFWFlavor('M9A')
    const maafw = resolveMaaFWFlavor('MaaFW')
    expect(m9a.docUrl).toBe(MAS_DOC_URLS.scriptTypes.M9A)
    expect(maafw.docUrl).toBe(MAS_DOC_URLS.scripts)
    expect(m9a.scriptPage.text.titleKey).toBe('edit.m9aFlavorScriptTitle')
    expect(maafw.scriptPage.text.titleKey).toBeNull()
    expect(m9a.userPage.text.queueHintKey).toBe('edit.m9aFlavorQueueHint')
    expect(maafw.userPage.text.queueHintKey).toBeNull()
    // 受管任务与后端 app/task/M9A/managed.py 的 MANAGED_ENTRIES 同一组；通用 MaaFW 没有
    expect([...m9a.userPage.managed.entries].sort()).toEqual([
      'Close1999',
      'StartUp',
      'SwitchAccount',
    ])
    expect(maafw.userPage.managed.entries).toEqual([])
    expect(maafw.userPage.managed.warningKey).toBeNull()
    // 每张表每一层的字段集都完全一致：组件只按同一组字段取值，没有任何 flavor 独有的键
    for (const flavor of MAAFW_FLAVORS) {
      expect([flavor.type, fieldPaths(flavor)]).toEqual([flavor.type, fieldPaths(maafw)])
      for (const [path, value] of fieldEntries(flavor)) {
        expect([flavor.type, path, typeof value === 'boolean']).toEqual([flavor.type, path, false])
      }
    }
  })

  it('表里引用的每个 i18n key 在中文词表里都存在（中文是源语言）', () => {
    for (const flavor of MAAFW_FLAVORS) {
      for (const [field, value] of fieldEntries(flavor)) {
        if (!field.endsWith('Key') || value === null) continue
        expect([flavor.type, field, value, typeof lookup(value as string)]).toEqual([
          flavor.type,
          field,
          value,
          'string',
        ])
      }
    }
  })

  it('M9A 文案说清了账号绑定与自动加入的首尾任务', () => {
    const m9a = resolveMaaFWFlavor('M9A')
    expect(lookup(m9a.userPage.text.accountPlaceholderKey)).toContain('切换账号')
    expect(lookup(m9a.userPage.text.queueHintKey!)).toContain('无需手动添加')
    expect(lookup(m9a.scriptPage.text.sourcePlaceholderKey)).toContain('interface.json')
    // 密码字段不跟着 flavor 走，两种 flavor 都是「仅本地记录」
    expect(lookup('edit.localNoteOnly')).toContain('本地记录')
  })

  it('响应式版本跟着脚本类型变（导入后后端会原地换类型）', () => {
    const type = ref<string>('MaaFW')
    const flavor = useMaaFWFlavor(type)
    expect(flavor.value.type).toBe('MaaFW')
    type.value = 'M9A'
    expect(flavor.value.type).toBe('M9A')
  })
})

describe('MaaFW 特调注册表', () => {
  it('三个类型各一个描述对象，身份字段与后端一一对应', () => {
    const identity = (flavor: MaaFWFlavor) => ({
      type: flavor.type,
      scriptConfigType: flavor.scriptConfigType,
      userConfigType: flavor.userConfigType,
      routeSuffix: flavor.routes.suffix,
      defaultScriptName: flavor.defaultScriptName,
      typeTagLabel: flavor.typeTagLabel,
      typeTagColor: flavor.typeTagColor,
      logo: flavor.logo,
    })
    expect(MAAFW_FLAVORS.map(identity)).toEqual([
      {
        type: 'MaaFW',
        scriptConfigType: 'MaaFWConfig',
        userConfigType: 'MaaFWUserConfig',
        routeSuffix: 'maafw',
        defaultScriptName: '新 MFW 脚本',
        typeTagLabel: 'MFW',
        typeTagColor: 'geekblue',
        logo: SCRIPT_LOGOS.MaaFW,
      },
      {
        type: 'M9A',
        scriptConfigType: 'M9AConfig',
        userConfigType: 'M9AUserConfig',
        routeSuffix: 'm9a',
        defaultScriptName: '新 M9A 脚本',
        typeTagLabel: 'M9A',
        typeTagColor: 'cyan',
        logo: SCRIPT_LOGOS.M9A,
      },
      {
        type: 'MSS',
        scriptConfigType: 'MSSConfig',
        userConfigType: 'MSSUserConfig',
        routeSuffix: 'mss',
        defaultScriptName: '新 MSS 脚本',
        typeTagLabel: 'MSS',
        typeTagColor: 'orange',
        logo: SCRIPT_LOGOS.MSS,
      },
    ])
    // 每一层字段集完全一致：defineMaaFWFlavor 补齐了特调没写的字段
    const paths = fieldPaths(MAAFW_FLAVORS[0])
    for (const flavor of MAAFW_FLAVORS) expect(fieldPaths(flavor)).toEqual(paths)
    expect(MAAFW_SPECIAL_FLAVORS.map(flavor => flavor.type)).toEqual(['M9A', 'MSS'])
  })

  it('isMaaFWFamily / 路由后缀 / 用户类型 / 默认名 / 配置类名都从注册表来', () => {
    for (const type of ['MaaFW', 'M9A', 'MSS']) expect(isMaaFWFamily(type)).toBe(true)
    for (const type of ['MAA', 'MaaEnd', 'General', '', null, undefined]) {
      expect(isMaaFWFamily(type)).toBe(false)
    }
    expect(['MaaFW', 'M9A', 'MSS', 'MAA', null].map(maafwRouteSuffix)).toEqual([
      'maafw',
      'm9a',
      'mss',
      'maafw',
      'maafw',
    ])
    expect([...maafwUserConfigTypes()].sort()).toEqual([
      'M9AUserConfig',
      'MSSUserConfig',
      'MaaFWUserConfig',
    ])
    expect(maafwUserConfigTypes().has('MaaUserConfig')).toBe(false)
    expect([...maafwDefaultScriptNames()].sort()).toEqual([
      '新 M9A 脚本',
      '新 MFW 脚本',
      '新 MSS 脚本',
    ])
    expect(maafwScriptTypeByConfigType()).toEqual({
      MaaFWConfig: 'MaaFW',
      M9AConfig: 'M9A',
      MSSConfig: 'MSS',
    })
  })

  it('只有 MSS 在用户页队列上方有独有区块，MaaFW / M9A 什么都不插', () => {
    expect(
      resolveMaaFWFlavorSlot(resolveMaaFWFlavor('MSS'), 'userPage', 'beforeTaskQueue')
    ).toHaveLength(3)
    for (const type of ['MaaFW', 'M9A']) {
      expect(
        resolveMaaFWFlavorSlot(resolveMaaFWFlavor(type), 'userPage', 'beforeTaskQueue')
      ).toEqual([])
      expect(resolveMaaFWFlavor(type).userPage.prepare).toBeNull()
    }
    expect(resolveMaaFWFlavor('MSS').userPage.prepare).toBeTypeOf('function')
    // 脚本页：M9A 在包名旁挂游戏更新下拉，MSS 在控制方式前挂提示，三个都没有钩子；两页都没有
    // 替换分节，也没有整页替换；新建流程什么都不换不插
    const scriptSlotNames: Record<string, string[]> = {
      MaaFW: [],
      M9A: ['besidePackageName'],
      MSS: ['beforeControl'],
    }
    for (const flavor of MAAFW_FLAVORS) {
      expect([
        flavor.type,
        Object.keys(flavor.scriptPage.slots),
        flavor.scriptPage.prepare,
        flavor.scriptPage.sections,
        flavor.userPage.sections,
        flavor.scriptPage.page,
        flavor.userPage.page,
        flavor.create.sections,
        flavor.create.slots,
      ]).toEqual([flavor.type, scriptSlotNames[flavor.type], null, {}, {}, null, null, {}, {}])
    }
  })

  it('页面准备：只预取这一页的整页、替换分节与插入点组件、调用这一页的钩子，失败不往外抛', async () => {
    const calls: string[] = []
    const lazy = (name: string, fail: 'reject' | 'throw' | null = null) => ({
      component: {},
      load: vi.fn(() => {
        calls.push(name)
        if (fail === 'throw') throw new Error(`同步抛出 ${name}`)
        return fail === 'reject'
          ? Promise.reject(new Error(`chunk 加载失败 ${name}`))
          : Promise.resolve({ default: {} })
      }),
    })
    const scriptPrepare = vi.fn(() => {
      calls.push('scriptPrepare')
      throw new Error('钩子同步抛出')
    })
    const userPrepare = vi.fn(async () => {
      calls.push('userPrepare')
    })
    const base = resolveMaaFWFlavor('MaaFW')
    const flavor = {
      ...base,
      scriptPage: {
        ...base.scriptPage,
        sections: { control: { ...lazy('control', 'reject'), part: 'scriptPage', key: 'control' } },
        prepare: scriptPrepare,
      },
      userPage: {
        ...base.userPage,
        page: lazy('userPage'),
        sections: { taskQueue: { ...lazy('taskQueue'), part: 'userPage', key: 'taskQueue' } },
        slots: { beforeTaskQueue: [lazy('slotA'), lazy('slotB', 'throw')] },
        prepare: userPrepare,
      },
      create: {
        ...base.create,
        sections: { source: { ...lazy('source', 'throw'), part: 'create', key: 'source' } },
        slots: { afterSourceStep: [lazy('createSlot')] },
      },
    } as unknown as MaaFWFlavor

    await expect(prepareMaaFWFlavorPage(flavor, 'userPage')).resolves.toBeUndefined()
    // 整页 → 分节 → 插入点 → 钩子，同一轮里依次发起
    expect(calls).toEqual(['userPage', 'taskQueue', 'slotA', 'slotB', 'userPrepare'])
    calls.length = 0
    await expect(prepareMaaFWFlavorPage(flavor, 'scriptPage')).resolves.toBeUndefined()
    expect(calls).toEqual(['control', 'scriptPrepare'])
    expect(userPrepare).toHaveBeenCalledOnce()
    // 新建流程没有整页与钩子：只预取分节与插入点
    calls.length = 0
    await expect(prepareMaaFWFlavorPage(flavor, 'create')).resolves.toBeUndefined()
    expect(calls).toEqual(['source', 'createSlot'])
    // 没有替换分节、插入点、钩子的 flavor 什么都不做
    for (const type of ['MaaFW', 'M9A']) {
      for (const part of ['scriptPage', 'userPage', 'create'] as const) {
        await expect(
          prepareMaaFWFlavorPage(resolveMaaFWFlavor(type), part)
        ).resolves.toBeUndefined()
      }
    }
  })

  it('页面准备：钩子与 chunk 同一轮里发起，不等前一个', () => {
    const load = vi.fn(() => new Promise(() => undefined))
    const prepare = vi.fn(() => new Promise<void>(() => undefined))
    const base = resolveMaaFWFlavor('MaaFW')
    void prepareMaaFWFlavorPage(
      {
        ...base,
        userPage: {
          ...base.userPage,
          slots: { beforeTaskQueue: [{ component: {}, load }] },
          prepare,
        },
      },
      'userPage'
    )
    expect(load).toHaveBeenCalledOnce()
    expect(prepare).toHaveBeenCalledOnce()
  })
})
