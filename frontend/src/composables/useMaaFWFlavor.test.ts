import { readFileSync, readdirSync } from 'node:fs'
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
  prepareMaaFWFlavorUserPage,
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
    expect(m9a.scriptTitleKey).toBe('edit.m9aFlavorScriptTitle')
    expect(maafw.scriptTitleKey).toBeNull()
    expect(m9a.queueHintKey).toBe('edit.m9aFlavorQueueHint')
    expect(maafw.queueHintKey).toBeNull()
    // 受管任务与后端 app/task/M9A/managed.py 的 MANAGED_ENTRIES 同一组；通用 MaaFW 没有
    expect([...m9a.managedTaskEntries].sort()).toEqual(['Close1999', 'StartUp', 'SwitchAccount'])
    expect(maafw.managedTaskEntries).toEqual([])
    expect(maafw.managedTaskWarningKey).toBeNull()
    // 两张表的字段集完全一致：组件只按同一组字段取值，没有任何 flavor 独有的键
    expect(Object.keys(m9a).sort()).toEqual(Object.keys(maafw).sort())
    for (const value of Object.values(m9a)) expect(typeof value === 'boolean').toBe(false)
  })

  it('表里引用的每个 i18n key 在中文词表里都存在（中文是源语言）', () => {
    for (const flavor of MAAFW_FLAVORS) {
      const entries = [
        ...Object.entries(flavor),
        ['createOption.titleKey', flavor.createOption.titleKey],
        ['createOption.descriptionKey', flavor.createOption.descriptionKey],
      ]
      for (const [field, value] of entries) {
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
    expect(lookup(m9a.accountPlaceholderKey)).toContain('切换账号')
    expect(lookup(m9a.queueHintKey!)).toContain('无需手动添加')
    expect(lookup(m9a.sourcePlaceholderKey)).toContain('interface.json')
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

  it('MaaFW 脚本页与用户页都按脚本当前类型取 flavor，不读路由 meta', () => {
    const scriptPage = readFileSync(
      new URL('../views/EditView/Script/MaaFWScriptEdit.vue', import.meta.url),
      'utf8'
    )
    const userPage = readFileSync(
      new URL('../views/EditView/User/MaaFWUserEdit.vue', import.meta.url),
      'utf8'
    )
    for (const source of [scriptPage, userPage]) {
      expect(source).toContain('useMaaFWFlavor(')
      expect(source).not.toContain('route.meta.scriptType')
    }
    // 导入 / 重新导入成功后要重新拉脚本类型：后端按项目内容原地换类型
    expect(scriptPage).toContain('refreshScriptType')
  })
})

describe('MaaFW 特调注册表', () => {
  it('三个类型各一个描述对象，身份字段与后端一一对应', () => {
    const identity = (flavor: MaaFWFlavor) => ({
      type: flavor.type,
      scriptConfigType: flavor.scriptConfigType,
      userConfigType: flavor.userConfigType,
      routeSuffix: flavor.routeSuffix,
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
    // 字段集完全一致：新特调漏写字段会在这里和 typecheck 两处报出来
    const keys = Object.keys(MAAFW_FLAVORS[0]).sort()
    for (const flavor of MAAFW_FLAVORS) expect(Object.keys(flavor).sort()).toEqual(keys)
    expect(MAAFW_SPECIAL_FLAVORS.map(flavor => flavor.type)).toEqual(['M9A', 'MSS'])
  })

  it('后端默认脚本名与配置类名照抄 app/models/config.py', () => {
    const source = readFileSync(new URL('../../../app/models/config.py', import.meta.url), 'utf8')
    for (const flavor of MAAFW_FLAVORS) {
      const block = (source.split(`class ${flavor.scriptConfigType}(`)[1] ?? '').split(
        '\nclass '
      )[0]
      expect([flavor.type, block.includes(`"${flavor.defaultScriptName}"`)]).toEqual([
        flavor.type,
        true,
      ])
    }
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
    expect(resolveMaaFWFlavorSlot(resolveMaaFWFlavor('MSS'), 'userBeforeTaskQueue')).toHaveLength(2)
    for (const type of ['MaaFW', 'M9A']) {
      expect(resolveMaaFWFlavorSlot(resolveMaaFWFlavor(type), 'userBeforeTaskQueue')).toEqual([])
      expect(resolveMaaFWFlavor(type).prepareUserPage).toBeNull()
    }
    expect(resolveMaaFWFlavor('MSS').prepareUserPage).toBeTypeOf('function')
  })

  it('用户页准备：预取插入点组件、调用 flavor 钩子，失败不往外抛', async () => {
    const load = vi.fn(async () => ({ default: {} }))
    const failingLoad = vi.fn(async () => {
      throw new Error('chunk 加载失败')
    })
    const prepareUserPage = vi.fn(async () => undefined)
    const flavor: MaaFWFlavor = {
      ...resolveMaaFWFlavor('MaaFW'),
      slots: {
        userBeforeTaskQueue: [
          { component: {}, load },
          { component: {}, load: failingLoad },
        ],
      },
      prepareUserPage,
    }
    await expect(prepareMaaFWFlavorUserPage(flavor)).resolves.toBeUndefined()
    expect(load).toHaveBeenCalledOnce()
    expect(failingLoad).toHaveBeenCalledOnce()
    expect(prepareUserPage).toHaveBeenCalledOnce()
    // 没有独有区块、没有钩子的 flavor 什么都不做
    await expect(prepareMaaFWFlavorUserPage(resolveMaaFWFlavor('M9A'))).resolves.toBeUndefined()
  })
})

describe('公共页面不按特调类型分支', () => {
  const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
  const sectionFiles = (dir: string) =>
    readdirSync(new URL(dir, import.meta.url))
      .filter(name => name.endsWith('.vue') || (name.endsWith('.ts') && !name.endsWith('.test.ts')))
      .map(name => `${dir}/${name}`)
  const PUBLIC_FILES = [
    '../views/EditView/Script/MaaFWScriptEdit.vue',
    '../views/EditView/User/MaaFWUserEdit.vue',
    ...sectionFiles('../views/EditView/Script/MaaFWScriptEdit'),
    ...sectionFiles('../views/EditView/User/MaaFWUserEdit'),
    '../components/ScriptTable.vue',
    '../views/Scripts.vue',
    '../views/scripts/components/scriptCreateFlow.ts',
    '../router/index.ts',
    './useScriptApi.ts',
  ]

  it.each(PUBLIC_FILES)('%s 不写特调类型字面量与 flavor.type 判断', path => {
    const source = read(path)
    expect(source).not.toMatch(/flavor(\.value)?\.type\s*[!=]==/)
    expect(source).not.toMatch(/['"`](M9A|MSS)['"`]/)
    expect(source).not.toMatch(/\b(M9A|MSS)(User)?Config\b/)
    expect(source).not.toMatch(/\/(m9a|mss)['"`]/)
  })
})
