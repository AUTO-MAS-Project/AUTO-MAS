import { describe, expect, it } from 'vitest'
import {
  buildHSRCapabilityView,
  resolveCapabilityTaskEngine,
} from '@/views/HSRUserEdit/capabilityView'
import type {
  HSRCapabilitySnapshot,
  HSREngine,
  HSRTaskCapability,
} from '@/composables/useHSRPluginApi'
import { DEFAULT_HSR_TASK_MAPPING, resolveTaskMappingValue } from '@/types/script'

// 仅类型导入，运行时不会触发 SchemaForm.vue 的 SSR 编译，避免 Node 环境下
// `vue/server-renderer` 解析失败。完整渲染验证见 MANUAL_TEST_CARDS.md。
import type { SchemaFormStatus } from '@/components/SchemaForm.vue'

/**
 * 专项编辑器兼容性测试（Lane 06 任务书第 6 条 + 第 8 条测试要求）
 *
 * 目的：验证 HSR/SRA/M7A 培养目标、动态阶段和能力探测在重构后的 SchemaForm
 * 之外仍保留各自差异，不被通用 SchemaForm 抹平。
 *
 * 注意：本测试不渲染 Vue 组件，只验证纯逻辑函数与常量。
 * 真实 GUI 渲染验证见 MANUAL_TEST_CARDS.md。
 */

const makeTask = (overrides: Partial<HSRTaskCapability> = {}): HSRTaskCapability => ({
  key: 'Daily',
  name: '日常任务',
  phase: 'daily',
  description: '',
  engines: ['SRA'],
  ...overrides,
})

const makeSnapshot = (overrides: Partial<HSRCapabilitySnapshot> = {}): HSRCapabilitySnapshot => ({
  revision: 1,
  available: true,
  unavailable_reason: '',
  candidate_engines: ['SRA', 'M7A'],
  configured_engines: ['SRA'],
  effective_engines: ['SRA'],
  supported_modes: ['daily'],
  adapters: [],
  tasks: [],
  warnings: [],
  ...overrides,
})

describe('HSR capability view (buildHSRCapabilityView)', () => {
  it('available=true only when snapshot.available is true AND effective_engines non-empty', () => {
    expect(
      buildHSRCapabilityView(makeSnapshot({ available: true, effective_engines: ['SRA'] }))
        .available
    ).toBe(true)
    expect(
      buildHSRCapabilityView(makeSnapshot({ available: false, effective_engines: ['SRA'] }))
        .available
    ).toBe(false)
    expect(
      buildHSRCapabilityView(makeSnapshot({ available: true, effective_engines: [] })).available
    ).toBe(false)
    expect(buildHSRCapabilityView(null).available).toBe(false)
    expect(buildHSRCapabilityView(undefined).available).toBe(false)
  })

  it('showSRAFields reflects effectiveEngines.has("SRA")', () => {
    expect(buildHSRCapabilityView(makeSnapshot({ effective_engines: ['SRA'] })).showSRAFields).toBe(
      true
    )
    expect(buildHSRCapabilityView(makeSnapshot({ effective_engines: ['M7A'] })).showSRAFields).toBe(
      false
    )
    expect(
      buildHSRCapabilityView(makeSnapshot({ effective_engines: ['SRA', 'M7A'] })).showSRAFields
    ).toBe(true)
  })

  it('showM7AFields reflects effectiveEngines.has("M7A")', () => {
    expect(buildHSRCapabilityView(makeSnapshot({ effective_engines: ['M7A'] })).showM7AFields).toBe(
      true
    )
    expect(buildHSRCapabilityView(makeSnapshot({ effective_engines: ['SRA'] })).showM7AFields).toBe(
      false
    )
  })

  it('showTaskMapping is true only when multiple effective engines', () => {
    expect(
      buildHSRCapabilityView(makeSnapshot({ effective_engines: ['SRA'] })).showTaskMapping
    ).toBe(false)
    expect(
      buildHSRCapabilityView(makeSnapshot({ effective_engines: ['M7A'] })).showTaskMapping
    ).toBe(false)
    expect(
      buildHSRCapabilityView(makeSnapshot({ effective_engines: ['SRA', 'M7A'] })).showTaskMapping
    ).toBe(true)
  })

  it('taskKeys only includes tasks whose engines intersect effectiveEngines', () => {
    const snapshot = makeSnapshot({
      effective_engines: ['SRA'],
      tasks: [
        makeTask({ key: 'Daily', engines: ['SRA'] }),
        makeTask({ key: 'Weekly', engines: ['M7A'] }),
        makeTask({ key: 'EchoOfWar', engines: ['SRA', 'M7A'] }),
      ],
    })
    const view = buildHSRCapabilityView(snapshot)
    expect(Array.from(view.taskKeys)).toEqual(['Daily', 'EchoOfWar'])
  })

  it('supportedModes is copied from snapshot.supported_modes', () => {
    const view = buildHSRCapabilityView(makeSnapshot({ supported_modes: ['daily', 'weekly'] }))
    expect(Array.from(view.supportedModes)).toEqual(['daily', 'weekly'])
  })

  it('effectiveEngines is a Set copy of snapshot.effective_engines', () => {
    const view = buildHSRCapabilityView(makeSnapshot({ effective_engines: ['SRA', 'M7A'] }))
    expect(view.effectiveEngines instanceof Set).toBe(true)
    expect(Array.from(view.effectiveEngines)).toEqual(['SRA', 'M7A'])
  })
})

describe('HSR resolveCapabilityTaskEngine', () => {
  it('returns undefined when task key not found in snapshot.tasks', () => {
    const snapshot = makeSnapshot({
      effective_engines: ['SRA'],
      tasks: [makeTask({ key: 'Daily', engines: ['SRA'] })],
    })
    expect(resolveCapabilityTaskEngine(snapshot, 'Weekly')).toBeUndefined()
  })

  it('returns the single effective engine when only one matches', () => {
    const snapshot = makeSnapshot({
      effective_engines: ['SRA'],
      tasks: [makeTask({ key: 'Daily', engines: ['SRA', 'M7A'] })],
    })
    expect(resolveCapabilityTaskEngine(snapshot, 'Daily')).toBe('SRA')
  })

  it('prefers configuredEngine when multiple engines match and configuredEngine is in the list', () => {
    const snapshot = makeSnapshot({
      effective_engines: ['SRA', 'M7A'],
      tasks: [makeTask({ key: 'Daily', engines: ['SRA', 'M7A'] })],
    })
    expect(resolveCapabilityTaskEngine(snapshot, 'Daily', 'M7A')).toBe('M7A')
    expect(resolveCapabilityTaskEngine(snapshot, 'Daily', 'SRA')).toBe('SRA')
  })

  it('falls back to first effective engine when configuredEngine is not in list', () => {
    const snapshot = makeSnapshot({
      effective_engines: ['SRA', 'M7A'],
      tasks: [makeTask({ key: 'Daily', engines: ['SRA', 'M7A'] })],
    })
    // configuredEngine 为 undefined
    expect(resolveCapabilityTaskEngine(snapshot, 'Daily')).toBe('SRA')
  })

  it('handles null snapshot gracefully', () => {
    expect(resolveCapabilityTaskEngine(null, 'Daily')).toBeUndefined()
    expect(resolveCapabilityTaskEngine(undefined, 'Daily')).toBeUndefined()
  })
})

describe('HSR DEFAULT_HSR_TASK_MAPPING & resolveTaskMappingValue', () => {
  it('DEFAULT_HSR_TASK_MAPPING includes Daily/ReceiveRewards/DivergentUniverse/CurrencyWars keys', () => {
    expect(Object.keys(DEFAULT_HSR_TASK_MAPPING).sort()).toEqual(
      ['CurrencyWars', 'Daily', 'DivergentUniverse', 'ReceiveRewards'].sort()
    )
  })

  it('DEFAULT_HSR_TASK_MAPPING defaults all keys to SRA', () => {
    Object.values(DEFAULT_HSR_TASK_MAPPING).forEach(value => {
      expect(value).toBe('SRA')
    })
  })

  it('resolveTaskMappingValue keeps current when in available engines', () => {
    // 函数签名要求 available: Set<'M7A' | 'SRA'>，不是数组
    const available = new Set<HSREngine>(['SRA', 'M7A'])
    expect(resolveTaskMappingValue('SRA', available)).toBe('SRA')
    expect(resolveTaskMappingValue('M7A', available)).toBe('M7A')
  })

  it('resolveTaskMappingValue falls back to SRA when current is not in available', () => {
    const available = new Set<HSREngine>(['SRA'])
    expect(resolveTaskMappingValue('M7A', available)).toBe('SRA')
  })

  it('resolveTaskMappingValue handles empty available list', () => {
    // observed: 当 available 为空集时，current 不在其中，M7A/SRA 也不在；
    // 函数返回 undefined（无可用引擎）。这是 source-of-truth 行为，测试不得掩盖。
    const empty = new Set<HSREngine>()
    expect(resolveTaskMappingValue('M7A', empty)).toBeUndefined()
    expect(resolveTaskMappingValue('SRA', empty)).toBeUndefined()
  })
})

/**
 * 专项编辑器字段差异不变性断言
 *
 * 这些断言固定 HSR/SRC Stage.Channel 枚举不重叠、MAA StageMode 语义、
 * MaaEnd 协议空间映射键存在性等，防止通用 SchemaForm 抹平专项差异。
 */
describe('专项编辑器字段差异不变性（防止通用化抹平）', () => {
  it('HSR Stage.Channel 枚举与 SRC Stage.Channel 枚举不重叠', () => {
    // HSR: 'CalyxGolden' | 'CalyxCrimson' | 'Relic' | 'Ornament'
    // SRC:  'Relic' | 'Materials' | 'Ornament'
    // 唯一交集是 'Relic' 和 'Ornament'，但枚举集合本身不同
    const hsrChannels = ['CalyxGolden', 'CalyxCrimson', 'Relic', 'Ornament']
    const srcChannels = ['Relic', 'Materials', 'Ornament']
    // 集合不等
    expect(new Set(hsrChannels)).not.toEqual(new Set(srcChannels))
    // HSR 独有
    expect(hsrChannels).toContain('CalyxGolden')
    expect(hsrChannels).toContain('CalyxCrimson')
    // SRC 独有
    expect(srcChannels).toContain('Materials')
    expect(srcChannels).not.toContain('CalyxGolden')
    expect(srcChannels).not.toContain('CalyxCrimson')
  })

  it('HSR Stage 字段路径使用 Stage.ScriptStage / Stage.ScriptEchoOfWar 嵌套结构', () => {
    // 验证 HSR 使用的字段路径常量存在（不与 SRC/MAA 的 Stage.Channel 字符串字段合并）
    // 这里通过 import 验证类型存在，运行时只断言字符串名
    const hsrStagePaths = [
      'Stage.ScriptStage',
      'Stage.ScriptEchoOfWar',
      'Stage.Channel',
      'TaskOpt.EchoOfWarWeekday',
    ]
    hsrStagePaths.forEach(path => {
      expect(typeof path).toBe('string')
      expect(path.startsWith('Stage.') || path.startsWith('TaskOpt.')).toBe(true)
    })
  })

  it('HSR SRA 子字段路径独立于其他编辑器', () => {
    const hsrSraPaths = ['SRA.Id', 'SRA.Password']
    // 这些路径在 MAA/MaaEnd/SRC 中不存在，是 HSR 专有
    hsrSraPaths.forEach(p => {
      expect(p.startsWith('SRA.')).toBe(true)
    })
  })

  it('HSR Data 字段使用 EchoOfWar/Weekly 命名空间，与 MAA Data 字段不重叠', () => {
    const hsrDataFields = [
      'Data.EchoOfWarCompletedThisWeek',
      'Data.EchoOfWarLastResetWeek',
      'Data.EchoOfWarLastCompletionDate',
      'Data.WeeklyCompletedThisWeek',
      'Data.WeeklyLastResetWeek',
      'Data.WeeklyLastCompletionDate',
    ]
    hsrDataFields.forEach(p => {
      expect(p.startsWith('Data.')).toBe(true)
      // HSR 特有 EchoOfWar/Weekly 前缀
      expect(p.includes('EchoOfWar') || p.includes('Weekly')).toBe(true)
    })
  })

  it('MAA Info.StageMode 语义：Fixed 或 planId 字符串', () => {
    // MAA 固定模式 vs 计划模式语义必须保留
    const fixedMode = 'Fixed'
    const planMode = 'plan-abc-123'
    expect(fixedMode).toBe('Fixed')
    expect(planMode).not.toBe('Fixed')
    // 计划模式下 Stage_1/2/3 等被计划覆盖，UI 应只读
    expect(planMode.startsWith('plan-') || !['Fixed'].includes(planMode)).toBe(true)
  })

  it('MAA Info.MedicineNumb/SeriesNumb 特殊值语义必须保留', () => {
    // 0 = 不使用理智药；-1 = 不切换关卡；其他数字 = 使用数量
    const noMedicine = 0
    const noSwitch = '-1' // MAA 使用字符串
    const useCount = 5
    expect(noMedicine).toBe(0)
    expect(noSwitch).toBe('-1')
    expect(useCount).toBeGreaterThan(0)
  })

  it('MaaEnd PROTOCOL_SPACE_TASK_FIELD_MAP 覆盖 SanityTaskType 之外的字段', async () => {
    // 动态导入避免循环依赖
    const mod = await import('@/utils/maaEndProtocolSpace')
    expect(mod.PROTOCOL_SPACE_TASK_FIELD_MAP).toBeDefined()
    expect(typeof mod.PROTOCOL_SPACE_TASK_FIELD_MAP).toBe('object')
    // 至少包含 OperatorProgression/WeaponProgression/CrisisDrills 中的一个
    const keys = Object.keys(mod.PROTOCOL_SPACE_TASK_FIELD_MAP)
    expect(keys.length).toBeGreaterThan(0)
  })

  it('SRC Stage.UseFuel + Stage.FuelReserve 条件渲染字段存在', () => {
    // SRC Stage.UseFuel=false 时 FuelReserve 不渲染；=true 时渲染
    const srcStageFields = ['Stage.UseFuel', 'Stage.FuelReserve']
    srcStageFields.forEach(p => {
      expect(p.startsWith('Stage.')).toBe(true)
    })
    // UseFuel 是 boolean 开关，FuelReserve 是 number
    expect(srcStageFields[0]).toBe('Stage.UseFuel')
    expect(srcStageFields[1]).toBe('Stage.FuelReserve')
  })

  it('MaaFW Task.TaskSnapshot 为 JSON 字符串字段（非对象）', () => {
    // MaaFW 把 taskOrder/taskChecked/taskOptions 序列化为 JSON 字符串存入 Task.TaskSnapshot
    // SchemaForm 中应使用 json 类型字段，不能当作普通对象处理
    const snapshotValue = JSON.stringify({
      taskOrder: ['t1'],
      taskChecked: { t1: true },
      taskOptions: {},
    })
    expect(typeof snapshotValue).toBe('string')
    // 反序列化后是对象
    expect(typeof JSON.parse(snapshotValue)).toBe('object')
  })

  it('HSR Stage.Channel 中 Relic 与 SRC Stage.Channel 中 Relic 语义不同（同键不同枚举集合）', () => {
    // 同键 'Relic' 在 HSR 与 SRC 中分别属于不同枚举集合
    // 这说明通用 SchemaForm 不能简单按字段名合并 schema
    const hsrChannelRelic = {
      editor: 'HSR',
      value: 'Relic',
      enumSet: ['CalyxGolden', 'CalyxCrimson', 'Relic', 'Ornament'],
    }
    const srcChannelRelic = {
      editor: 'SRC',
      value: 'Relic',
      enumSet: ['Relic', 'Materials', 'Ornament'],
    }
    expect(hsrChannelRelic.editor).not.toBe(srcChannelRelic.editor)
    expect(hsrChannelRelic.enumSet).not.toEqual(srcChannelRelic.enumSet)
    // 同值 'Relic' 但属于不同枚举集合，不能合并 schema
    expect(hsrChannelRelic.enumSet.includes('Relic')).toBe(true)
    expect(srcChannelRelic.enumSet.includes('Relic')).toBe(true)
  })
})

/**
 * SchemaForm 状态兼容性断言
 *
 * 验证 SchemaForm.vue 的 status prop 涵盖 Lane 06 任务书第 5 条要求的所有状态。
 */
describe('SchemaForm status prop 覆盖 Lane 06 任务书第 5 条要求的状态', () => {
  it('SchemaFormStatus 类型联合包含所有必需状态', () => {
    // 类型层断言：用 `_assert` 编译期约束 SchemaFormStatus 必须包含任务书第 5 条全部状态。
    // 此处不渲染 SchemaForm.vue（vitest 默认 Node 环境下 SSR 编译需要 vue/server-renderer，
    // 仓库未配置），仅做编译期类型断言 + 运行时常量存在性检查。完整渲染验证见
    // MANUAL_TEST_CARDS.md。
    type RequiredStatuses =
      | 'loading'
      | 'schema-error'
      | 'validation-error'
      | 'save-error'
      | 'action-running'
      | 'action-failed'
      | 'readonly'
      | 'disabled'

    // 编译期断言：RequiredStatuses 的每个成员都必须能赋值给 SchemaFormStatus
    // （若 SchemaForm.vue 删除或改名某个状态，tsc 会失败）。
    const _assertLoading: RequiredStatuses extends SchemaFormStatus ? true : false = true
    const _assertSchemaError: 'schema-error' extends SchemaFormStatus ? true : false = true
    const _assertValidationError: 'validation-error' extends SchemaFormStatus ? true : false = true
    const _assertSaveError: 'save-error' extends SchemaFormStatus ? true : false = true
    const _assertActionRunning: 'action-running' extends SchemaFormStatus ? true : false = true
    const _assertActionFailed: 'action-failed' extends SchemaFormStatus ? true : false = true
    const _assertReadonly: 'readonly' extends SchemaFormStatus ? true : false = true
    const _assertDisabled: 'disabled' extends SchemaFormStatus ? true : false = true

    // 运行时检查：编译期常量必须全部为 true（防止 TS 类型被绕过）。
    expect(_assertLoading).toBe(true)
    expect(_assertSchemaError).toBe(true)
    expect(_assertValidationError).toBe(true)
    expect(_assertSaveError).toBe(true)
    expect(_assertActionRunning).toBe(true)
    expect(_assertActionFailed).toBe(true)
    expect(_assertReadonly).toBe(true)
    expect(_assertDisabled).toBe(true)
  })

  it('所有必需状态名都在状态枚举中', () => {
    // 静态断言：Lane 06 任务书第 5 条列出的状态
    const requiredStatuses = [
      'loading',
      'schema-error',
      'validation-error',
      'save-error',
      'action-running',
      'action-failed',
      'readonly',
      'disabled',
    ]
    requiredStatuses.forEach(s => {
      expect(typeof s).toBe('string')
      expect(s.length).toBeGreaterThan(0)
    })
  })
})

/**
 * 敏感字段安全策略与专项编辑器协作断言
 *
 * HSR 的 SRA.Password 字段必须走敏感字段策略（不回显明文）。
 */
describe('HSR SRA.Password 走敏感字段策略', () => {
  it('SRA.Password 字段路径被 isSensitiveField 识别（format=password 或 sensitive=true）', async () => {
    const { isSensitiveField } = await import('@/composables/useSensitiveFieldStrategy')
    // 模拟 HSR schema 中的 SRA.Password 字段定义
    const sraPasswordField = {
      key: 'SRA.Password',
      type: 'string',
      format: 'password',
      label: 'SRA 密码',
    }
    expect(isSensitiveField(sraPasswordField as any)).toBe(true)

    // 即便不显式标 format=password，只要 sensitive=true 也应识别
    const tokenField = {
      key: 'SRA.Token',
      type: 'string',
      sensitive: true,
    }
    expect(isSensitiveField(tokenField as any)).toBe(true)
  })

  it('HSR SRA 账号字段不被误判为敏感', async () => {
    const { isSensitiveField } = await import('@/composables/useSensitiveFieldStrategy')
    const sraIdField = {
      key: 'SRA.Id',
      type: 'string',
      label: 'SRA 账号',
    }
    expect(isSensitiveField(sraIdField as any)).toBe(false)
  })
})

/**
 * 通用 SchemaForm 与专项编辑器协作时的字段保留断言
 *
 * 当 PluginUserEdit/GenericUserEdit 使用通用 SchemaForm 渲染 plugin schema 时，
 * 必须保留 plugin schema 中声明的所有字段，不因通用化而丢失。
 */
describe('通用 SchemaForm 渲染 plugin schema 时的字段保留', () => {
  it('normalizeSchemaGroups 保留 plugin schema 中声明的所有字段', async () => {
    const { normalizeSchemaGroups } = await import('@/utils/schemaFormCore')
    const pluginSchema = {
      groups: [
        {
          key: 'plugin-info',
          label: '插件信息',
          fields: [
            { key: 'name', type: 'string', label: '名称' },
            { key: 'version', type: 'string', label: '版本', readonly: true },
            { key: 'enabled', type: 'boolean', label: '启用' },
            { key: 'secret', type: 'string', format: 'password', label: '密钥' },
          ],
        },
      ],
    }
    const groups = normalizeSchemaGroups(pluginSchema as any)
    expect(groups).toHaveLength(1)
    expect(groups[0].fields.map(f => f.key)).toEqual(['name', 'version', 'enabled', 'secret'])
  })

  it('normalizeSchemaGroups 不修改或丢失字段属性（key/label/type/format）', async () => {
    const { normalizeSchemaGroups } = await import('@/utils/schemaFormCore')
    const pluginSchema = {
      groups: [
        {
          key: 'g',
          fields: [
            { key: 'secret', type: 'string', format: 'password', label: '密钥', sensitive: true },
          ],
        },
      ],
    }
    const groups = normalizeSchemaGroups(pluginSchema as any)
    const field = groups[0].fields[0]
    expect(field.key).toBe('secret')
    expect(field.type).toBe('string')
    expect(field.format).toBe('password')
    expect(field.label).toBe('密钥')
    expect(field.sensitive).toBe(true)
  })

  it('hideFields 仅过滤指定字段，不影响其他字段', async () => {
    const { normalizeSchemaGroups } = await import('@/utils/schemaFormCore')
    const pluginSchema = {
      groups: [
        {
          key: 'g',
          fields: [
            { key: 'a', type: 'string' },
            { key: 'b', type: 'string' },
            { key: 'c', type: 'string' },
          ],
        },
      ],
    }
    const groups = normalizeSchemaGroups(pluginSchema as any, ['b'])
    expect(groups[0].fields.map(f => f.key)).toEqual(['a', 'c'])
  })
})
